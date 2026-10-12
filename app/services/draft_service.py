"""Draft Service - manages draft sessions and picks."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.draft import DraftSession, DraftPick, DraftOrder, DraftProtection
from app.models.player import Player, PlayerSeason
from app.models.team import TeamSeason
from app.models.league import League
from app.models.org_season import OrgSeason


@dataclass
class DraftBoardPlayer:
    """Player info for draft board display."""
    player_id: int
    player_season_id: int
    name: str
    age: Optional[int]
    player_code: str
    status: str
    is_available: bool = True


class DraftService:
    """Service for managing drafts."""

    @staticmethod
    def get_sessions_for_season(org_season_id: int) -> List[DraftSession]:
        """Get all draft sessions for a season."""
        return DraftSession.query.filter_by(
            org_season_id=org_season_id
        ).options(
            joinedload(DraftSession.league),
            joinedload(DraftSession.org_season)
        ).order_by(DraftSession.created_at.desc()).all()

    @staticmethod
    def get_session(session_id: int) -> Optional[DraftSession]:
        """Get a draft session by ID with relationships loaded."""
        return DraftSession.query.filter_by(id=session_id).options(
            joinedload(DraftSession.league),
            joinedload(DraftSession.org_season),
            joinedload(DraftSession.current_team)
        ).first()

    @staticmethod
    def create_session(
        org_season_id: int,
        league_id: int,
        name: str,
        draft_order_type: str = 'snake',
        rounds: int = 12,
        created_by: int = None
    ) -> DraftSession:
        """Create a new draft session.

        Args:
            org_season_id: The OrgSeason ID
            league_id: The League ID
            name: Name for the draft session
            draft_order_type: 'snake' or 'linear'
            rounds: Number of rounds
            created_by: User ID who created this

        Returns:
            Created DraftSession
        """
        session = DraftSession(
            org_season_id=org_season_id,
            league_id=league_id,
            name=name,
            draft_order_type=draft_order_type,
            rounds=rounds,
            status=DraftSession.STATUS_PENDING,
            created_by=created_by
        )
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def get_teams_for_draft(org_season_id: int, league_id: int) -> List[TeamSeason]:
        """Get teams available for a draft."""
        org_season = OrgSeason.query.get(org_season_id)
        if not org_season:
            return []

        return TeamSeason.query.filter_by(
            year=org_season.year,
            is_spring=org_season.is_spring,
            league_id=league_id,
            active=1,
            is_placeholder=0
        ).order_by(TeamSeason.display_name).all()

    @staticmethod
    def set_draft_order(session_id: int, team_ids: List[int]) -> None:
        """Set the draft order for a session.

        Args:
            session_id: The DraftSession ID
            team_ids: List of team IDs in draft order
        """
        # Remove existing order
        DraftOrder.query.filter_by(session_id=session_id).delete()

        # Add new order
        for position, team_id in enumerate(team_ids, start=1):
            order = DraftOrder(
                session_id=session_id,
                position=position,
                team_id=team_id
            )
            db.session.add(order)

        db.session.commit()

    @staticmethod
    def get_draft_order(session_id: int) -> List[DraftOrder]:
        """Get draft order for a session."""
        return DraftOrder.query.filter_by(
            session_id=session_id
        ).options(
            joinedload(DraftOrder.team)
        ).order_by(DraftOrder.position).all()

    @staticmethod
    def generate_picks(session: DraftSession) -> int:
        """Generate all pick slots for a draft session.

        Creates empty pick records based on draft order and rounds.

        Args:
            session: The DraftSession

        Returns:
            Number of picks generated
        """
        order = DraftService.get_draft_order(session.id)
        if not order:
            raise ValueError("Draft order must be set before generating picks")

        num_teams = len(order)
        total_picks = num_teams * session.rounds

        # Remove any existing picks
        DraftPick.query.filter_by(session_id=session.id).delete()

        pick_number = 1
        for round_num in range(1, session.rounds + 1):
            # Snake draft: reverse order on even rounds
            team_order = list(order)
            if session.draft_order_type == DraftSession.ORDER_SNAKE and round_num % 2 == 0:
                team_order.reverse()

            for draft_order in team_order:
                pick = DraftPick(
                    session_id=session.id,
                    pick_number=pick_number,
                    round_number=round_num,
                    team_id=draft_order.team_id
                )
                db.session.add(pick)
                pick_number += 1

        # Set current team to first picker
        if order:
            session.current_team_id = order[0].team_id
            session.current_round = 1
            session.current_pick_number = 1

        db.session.commit()
        return total_picks

    @staticmethod
    def start_draft(session_id: int) -> DraftSession:
        """Start a draft session."""
        session = DraftSession.query.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Verify picks are generated
        if session.picks.count() == 0:
            raise ValueError("Picks must be generated before starting")

        session.start()
        return session

    @staticmethod
    def get_available_players(session: DraftSession) -> List[DraftBoardPlayer]:
        """Get players available to be drafted.

        Args:
            session: The DraftSession

        Returns:
            List of DraftBoardPlayer for display
        """
        # Get all players in the league for this season
        player_seasons = PlayerSeason.query.filter_by(
            org_season_id=session.org_season_id,
            placed_league_id=session.league_id
        ).options(
            joinedload(PlayerSeason.player)
        ).all()

        # Get already drafted player IDs
        drafted_player_ids = set()
        for pick in session.picks:
            if pick.player_id:
                drafted_player_ids.add(pick.player_id)

        # Also exclude players already assigned to teams (outside draft)
        assigned_ids = set(ps.player_id for ps in player_seasons if ps.team_id)

        result = []
        for ps in player_seasons:
            if ps.player:
                player = ps.player
                is_available = (
                    player.id not in drafted_player_ids and
                    player.id not in assigned_ids
                )

                # Calculate age
                age = None
                if player.birth_date and session.org_season:
                    age = player.league_age(session.org_season)

                result.append(DraftBoardPlayer(
                    player_id=player.id,
                    player_season_id=ps.id,
                    name=f"{player.last_name}, {player.first_name}",
                    age=age,
                    player_code=player.player_code or '',
                    status=ps.status or 'registered',
                    is_available=is_available
                ))

        # Sort by name
        result.sort(key=lambda p: p.name.lower())
        return result

    @staticmethod
    def get_current_pick(session_id: int) -> Optional[DraftPick]:
        """Get the current pick in a draft."""
        session = DraftSession.query.get(session_id)
        if not session or not session.can_make_picks:
            return None

        return DraftPick.query.filter_by(
            session_id=session_id,
            pick_number=session.current_pick_number
        ).options(
            joinedload(DraftPick.team)
        ).first()

    @staticmethod
    def make_pick(session_id: int, player_id: int) -> DraftPick:
        """Make a draft pick.

        Args:
            session_id: The DraftSession ID
            player_id: The Player ID being picked

        Returns:
            The updated DraftPick

        Raises:
            ValueError: If pick cannot be made
        """
        session = DraftSession.query.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if not session.can_make_picks:
            raise ValueError(f"Draft is not active (status: {session.status})")

        # Get current pick
        current_pick = DraftService.get_current_pick(session_id)
        if not current_pick:
            raise ValueError("No current pick found")

        if current_pick.player_id is not None:
            raise ValueError("Pick already made")

        # Verify player is available
        already_picked = DraftPick.query.filter_by(
            session_id=session_id,
            player_id=player_id
        ).first()
        if already_picked:
            raise ValueError("Player already drafted")

        # Make the pick
        current_pick.player_id = player_id
        current_pick.picked_at = datetime.utcnow()

        # Update player season status
        player_season = PlayerSeason.query.filter_by(
            org_season_id=session.org_season_id,
            player_id=player_id
        ).first()
        if player_season:
            player_season.team_id = current_pick.team_id
            player_season.status = 'drafted'

        # Advance to next pick
        next_pick = DraftPick.query.filter_by(
            session_id=session_id,
            pick_number=session.current_pick_number + 1
        ).first()

        if next_pick:
            session.current_pick_number += 1
            session.current_round = next_pick.round_number
            session.current_team_id = next_pick.team_id
        else:
            # Draft complete
            session.complete()

        db.session.commit()
        return current_pick

    @staticmethod
    def get_draft_results(session_id: int) -> List[DraftPick]:
        """Get all picks for a draft, ordered by pick number."""
        return DraftPick.query.filter_by(
            session_id=session_id
        ).options(
            joinedload(DraftPick.team),
            joinedload(DraftPick.player)
        ).order_by(DraftPick.pick_number).all()

    @staticmethod
    def get_team_picks(session_id: int, team_id: int) -> List[DraftPick]:
        """Get all picks for a specific team."""
        return DraftPick.query.filter_by(
            session_id=session_id,
            team_id=team_id
        ).options(
            joinedload(DraftPick.player)
        ).order_by(DraftPick.pick_number).all()

    # =========================================================================
    # Protected Picks (Coach's Children)
    # =========================================================================

    @staticmethod
    def add_protection(
        session_id: int,
        team_id: int,
        player_id: int,
        round_number: int,
        reason: str = "Coach's child"
    ) -> DraftProtection:
        """Add a protected pick for a player.

        Args:
            session_id: The DraftSession ID
            team_id: The team that must draft this player
            player_id: The player to be protected
            round_number: The round this player must be drafted
            reason: Reason for protection (default: "Coach's child")

        Returns:
            Created DraftProtection

        Raises:
            ValueError: If protection cannot be added
        """
        session = DraftSession.query.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.status not in (DraftSession.STATUS_PENDING, DraftSession.STATUS_PAUSED):
            raise ValueError("Can only add protections before or during a paused draft")

        if round_number < 1 or round_number > session.rounds:
            raise ValueError(f"Round must be between 1 and {session.rounds}")

        # Check if player already has a protection
        existing = DraftProtection.query.filter_by(
            session_id=session_id,
            player_id=player_id
        ).first()
        if existing:
            raise ValueError("Player already has a protected pick")

        protection = DraftProtection(
            session_id=session_id,
            team_id=team_id,
            player_id=player_id,
            round_number=round_number,
            reason=reason
        )
        db.session.add(protection)
        db.session.commit()
        return protection

    @staticmethod
    def remove_protection(protection_id: int) -> None:
        """Remove a draft protection."""
        protection = DraftProtection.query.get(protection_id)
        if protection:
            db.session.delete(protection)
            db.session.commit()

    @staticmethod
    def get_protections(session_id: int) -> List[DraftProtection]:
        """Get all protections for a draft session."""
        return DraftProtection.query.filter_by(
            session_id=session_id
        ).options(
            joinedload(DraftProtection.team),
            joinedload(DraftProtection.player)
        ).order_by(DraftProtection.round_number, DraftProtection.team_id).all()

    @staticmethod
    def get_protection_for_pick(session_id: int, team_id: int, round_number: int) -> Optional[DraftProtection]:
        """Check if a team has a protected pick for a specific round.

        Args:
            session_id: The DraftSession ID
            team_id: The team ID
            round_number: The round number

        Returns:
            DraftProtection if one exists, None otherwise
        """
        return DraftProtection.query.filter_by(
            session_id=session_id,
            team_id=team_id,
            round_number=round_number
        ).options(
            joinedload(DraftProtection.player)
        ).first()

    @staticmethod
    def get_protections_by_team(session_id: int) -> Dict[int, List[DraftProtection]]:
        """Get protections grouped by team.

        Returns:
            Dict mapping team_id to list of protections
        """
        protections = DraftService.get_protections(session_id)
        result: Dict[int, List[DraftProtection]] = {}
        for p in protections:
            if p.team_id not in result:
                result[p.team_id] = []
            result[p.team_id].append(p)
        return result

    @staticmethod
    def get_players_for_protection(session: DraftSession) -> List[DraftBoardPlayer]:
        """Get players available for protection (not yet protected).

        Args:
            session: The DraftSession

        Returns:
            List of DraftBoardPlayer for display
        """
        # Get all players in the league for this season
        player_seasons = PlayerSeason.query.filter_by(
            org_season_id=session.org_season_id,
            placed_league_id=session.league_id
        ).options(
            joinedload(PlayerSeason.player)
        ).all()

        # Get already protected player IDs
        protected_ids = set(p.player_id for p in session.protections)

        result = []
        for ps in player_seasons:
            if ps.player and ps.player.id not in protected_ids:
                player = ps.player
                age = None
                if player.birth_date and session.org_season:
                    age = player.league_age(session.org_season)

                result.append(DraftBoardPlayer(
                    player_id=player.id,
                    player_season_id=ps.id,
                    name=f"{player.last_name}, {player.first_name}",
                    age=age,
                    player_code=player.player_code or '',
                    status=ps.status or 'registered',
                    is_available=True
                ))

        result.sort(key=lambda p: p.name.lower())
        return result
