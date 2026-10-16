"""Call-Up Service - business logic for managing player call-up requests."""

from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from app.extensions import db
from app.models.callup_request import CallUpRequest
from app.models.player import PlayerSeason, Player, PlayerEvaluation
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.org_season import OrgSeason
from app.models.league import League
from app.models.user import User
from app.services.notification_service import GmailService
from sqlalchemy.orm import joinedload


@dataclass
class CallUpStats:
    """Statistics for the call-ups dashboard."""
    pending: int = 0
    accepted: int = 0
    declined: int = 0
    no_response: int = 0
    total: int = 0


@dataclass
class ConflictInfo:
    """Details about a scheduling conflict."""
    game: Game
    conflict_type: str  # 'game', 'practice', 'scrimmage'
    time: str  # Formatted time string
    field: str  # Field name


@dataclass
class EligiblePlayer:
    """Player eligible for call-up with evaluation and history data."""
    player_season: PlayerSeason
    player: Player
    team: TeamSeason
    eval_score: Optional[float]
    callup_count: int  # Accepted call-ups this season
    pending_count: int  # Pending requests
    has_conflict: bool  # Has another game/practice at same time
    conflict_info: Optional[ConflictInfo]  # Details of the conflict, if any


class CallUpService:
    """Service for managing player call-up requests."""

    @staticmethod
    def create_request(
        player_season_id: int,
        game_id: int,
        target_team_id: int,
        requested_by_id: int,
        contact_email: str,
        send_email: bool = True,
        email_subject: str = None,
        email_body: str = None,
        notes: str = None
    ) -> CallUpRequest:
        """
        Create a new call-up request.

        Args:
            player_season_id: ID of the player's season record
            game_id: ID of the game they're being asked to sub for
            target_team_id: ID of the team needing the sub
            requested_by_id: ID of the user making the request
            contact_email: Parent email to contact
            send_email: Whether to send the email immediately
            email_subject: Custom email subject
            email_body: Custom email body (plain text)
            notes: Optional notes (e.g., "Called parent, they said yes")

        Returns:
            The created CallUpRequest

        Raises:
            ValueError: If validation fails
        """
        # Validate player season exists
        player_season = PlayerSeason.query.get(player_season_id)
        if not player_season:
            raise ValueError(f"Player season {player_season_id} not found")

        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        # Validate team exists
        team = TeamSeason.query.get(target_team_id)
        if not team:
            raise ValueError(f"Team {target_team_id} not found")

        # Create the request
        request = CallUpRequest(
            player_season_id=player_season_id,
            game_id=game_id,
            target_team_id=target_team_id,
            requested_by=requested_by_id,
            contact_email=contact_email,
            requested_at=datetime.utcnow(),
            status='pending',
            notes=notes
        )
        db.session.add(request)
        db.session.commit()

        # Send email if requested
        if send_email and email_subject and email_body:
            try:
                CallUpService.send_callup_email(
                    to_email=contact_email,
                    subject=email_subject,
                    body_text=email_body
                )
            except Exception as e:
                # Log but don't fail - request is still created
                print(f"Warning: Failed to send call-up email: {e}")

        return request

    @staticmethod
    def update_status(
        request_id: int,
        status: str,
        notes: str = None
    ) -> CallUpRequest:
        """
        Update the status of a call-up request.

        Args:
            request_id: ID of the request to update
            status: New status (accepted, declined, no_response, cancelled)
            notes: Optional notes about the status change

        Returns:
            The updated CallUpRequest

        Raises:
            ValueError: If request not found or invalid status
        """
        request = CallUpRequest.query.get(request_id)
        if not request:
            raise ValueError(f"Call-up request {request_id} not found")

        if status not in CallUpRequest.STATUSES:
            raise ValueError(f"Invalid status: {status}")

        request.status = status
        request.responded_at = datetime.utcnow()
        if notes:
            request.notes = notes

        db.session.commit()
        return request

    @staticmethod
    def get_active_requests(org_season_id: int, filters: Dict[str, Any] = None) -> List[CallUpRequest]:
        """
        Get call-up requests for a season with optional filters.

        Args:
            org_season_id: The org season to get requests for
            filters: Optional dict with keys:
                - status: Filter by status
                - league_id: Filter by target league
                - date_from: Filter games on or after this date
                - date_to: Filter games on or before this date

        Returns:
            List of CallUpRequest objects with relationships loaded
        """
        filters = filters or {}

        query = CallUpRequest.query.join(
            PlayerSeason, CallUpRequest.player_season_id == PlayerSeason.id
        ).filter(
            PlayerSeason.org_season_id == org_season_id
        ).options(
            joinedload(CallUpRequest.player_season).joinedload(PlayerSeason.player),
            joinedload(CallUpRequest.player_season).joinedload(PlayerSeason.placed_league),
            joinedload(CallUpRequest.game),
            joinedload(CallUpRequest.target_team),
            joinedload(CallUpRequest.requester)
        )

        # Apply status filter
        if filters.get('status'):
            query = query.filter(CallUpRequest.status == filters['status'])

        # Apply league filter
        if filters.get('league_id'):
            query = query.filter(CallUpRequest.target_team.has(league_id=filters['league_id']))

        # Apply date filters
        if filters.get('date_from'):
            query = query.filter(CallUpRequest.game.has(Game.game_date >= filters['date_from']))
        if filters.get('date_to'):
            query = query.filter(CallUpRequest.game.has(Game.game_date <= filters['date_to']))

        return query.order_by(CallUpRequest.requested_at.desc()).all()

    @staticmethod
    def get_player_callup_count(player_season_id: int) -> Dict[str, int]:
        """
        Get call-up counts for a player.

        Returns:
            Dict with 'total', 'accepted', 'pending' counts
        """
        total = CallUpRequest.count_for_player(player_season_id)
        accepted = CallUpRequest.count_for_player(player_season_id, status='accepted')
        pending = CallUpRequest.count_for_player(player_season_id, status='pending')

        return {
            'total': total,
            'accepted': accepted,
            'pending': pending
        }

    @staticmethod
    def get_dashboard_stats(org_season_id: int) -> CallUpStats:
        """
        Get statistics for the call-ups dashboard.

        Args:
            org_season_id: The org season to get stats for

        Returns:
            CallUpStats dataclass with counts by status
        """
        from sqlalchemy import func

        # Single query to get all counts
        results = db.session.query(
            CallUpRequest.status,
            func.count(CallUpRequest.id)
        ).join(
            PlayerSeason, CallUpRequest.player_season_id == PlayerSeason.id
        ).filter(
            PlayerSeason.org_season_id == org_season_id
        ).group_by(
            CallUpRequest.status
        ).all()

        stats = CallUpStats()
        for status, count in results:
            if status == 'pending':
                stats.pending = count
            elif status == 'accepted':
                stats.accepted = count
            elif status == 'declined':
                stats.declined = count
            elif status == 'no_response':
                stats.no_response = count
            stats.total += count

        return stats

    @staticmethod
    def get_upcoming_games_for_callup(org_season_id: int) -> List[Game]:
        """
        Get upcoming ACTUAL GAMES (not practices, not scrimmages) suitable for call-up requests.

        Only returns games for leagues that have active teams in the current season.
        For example, BB Majors doesn't exist in Fall, so those games won't be shown.

        Args:
            org_season_id: Season to get games for

        Returns:
            List of upcoming Game objects (regular and playoff only)
        """
        org_season = OrgSeason.query.get(org_season_id)
        if not org_season:
            return []

        # Get league IDs that have active teams in this season
        active_league_ids = db.session.query(TeamSeason.league_id).filter(
            TeamSeason.year == org_season.year,
            TeamSeason.is_spring == org_season.is_spring,
            TeamSeason.league_id.isnot(None)
        ).distinct().all()
        active_league_ids = [lid[0] for lid in active_league_ids if lid[0]]

        if not active_league_ids:
            return []

        query = Game.query.filter(
            Game.year == org_season.year,
            Game.is_spring == org_season.is_spring,
            Game.game_date > datetime.utcnow(),
            Game.active == 1,
            Game.status == 'scheduled',
            # Only actual games - no practices or scrimmages
            Game.game_type.in_(['regular', 'playoff']),
            Game.is_scrimmage == 0,
            # Only leagues with active teams this season
            Game.league_id.in_(active_league_ids)
        ).options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel),
            joinedload(Game.league_rel)
        )

        return query.order_by(Game.game_date).all()

    @staticmethod
    def get_feeder_league(target_league_id: int, org_season_id: int = None) -> Optional[League]:
        """
        Get the league one age_rank below the target league (same sport) that has active teams.

        The "feeder league" is where we pull call-up candidates from.
        For example, if the target game is in AA, we pull from A.

        IMPORTANT: In Fall, some leagues (like BB Majors) don't exist. So if Intermediate
        (age_rank=7) needs a sub, we skip Majors (age_rank=6) and go to AAA/Grapefruit (age_rank=5).

        Args:
            target_league_id: The league ID of the game needing a sub
            org_season_id: The org season (used to check which leagues have teams)

        Returns:
            The League with the next lower age_rank that has teams, or None if no lower league exists
        """
        target_league = League.query.get(target_league_id)
        if not target_league or not target_league.age_rank:
            return None

        # If we have org_season_id, find leagues that have teams in this season
        if org_season_id:
            org_season = OrgSeason.query.get(org_season_id)
            if org_season:
                # Get league IDs with teams in this season
                active_league_ids = db.session.query(TeamSeason.league_id).filter(
                    TeamSeason.year == org_season.year,
                    TeamSeason.is_spring == org_season.is_spring,
                    TeamSeason.league_id.isnot(None)
                ).distinct().all()
                active_league_ids = [lid[0] for lid in active_league_ids if lid[0]]

                # Find the league with the highest age_rank that is:
                # 1. Less than target league's age_rank (younger players)
                # 2. Same sport
                # 3. Has teams in this season
                feeder = League.query.filter(
                    League.active == 1,
                    League.sport == target_league.sport,
                    League.age_rank < target_league.age_rank,
                    League.ID.in_(active_league_ids)
                ).order_by(League.age_rank.desc()).first()  # Get highest age_rank below target

                return feeder

        # Fallback: just use age_rank - 1 (original logic)
        feeder = League.query.filter(
            League.active == 1,
            League.sport == target_league.sport,
            League.age_rank == target_league.age_rank - 1
        ).first()

        return feeder

    @staticmethod
    def get_eligible_players_for_callup(
        org_season_id: int,
        game: Game,
        include_conflicts: bool = False
    ) -> List[EligiblePlayer]:
        """
        Get players eligible for call-up for a specific game.

        Eligibility criteria:
        1. In the feeder league (one age_rank below the game's league)
        2. Same sport as the game
        3. Assigned to a team (has team_id)
        4. Optionally filter out players with game conflicts

        Returns players sorted by:
        1. Eval score (descending) - best players first
        2. Call-up count (ascending) - equity: players with fewer call-ups first

        Args:
            org_season_id: The org season
            game: The game needing a call-up
            include_conflicts: If True, include players with conflicts (marked)

        Returns:
            List of EligiblePlayer objects with all relevant data
        """
        if not game or not game.league_id:
            return []

        # Find the feeder league (pass org_season_id to handle inactive leagues in Fall)
        feeder_league = CallUpService.get_feeder_league(game.league_id, org_season_id)
        if not feeder_league:
            return []

        # Get players in the feeder league who are assigned to teams
        player_seasons = PlayerSeason.query.filter(
            PlayerSeason.org_season_id == org_season_id,
            PlayerSeason.team_id.isnot(None),  # Must be on a team
            PlayerSeason.status != 'withdrawn'
        ).options(
            joinedload(PlayerSeason.player),
            joinedload(PlayerSeason.team).joinedload(TeamSeason.league_rel),
            joinedload(PlayerSeason.placed_league)
        ).all()

        # Filter to only players in the feeder league
        # A player is in the feeder league if their team's league_id matches
        feeder_players = []
        for ps in player_seasons:
            if ps.team and ps.team.league_id == feeder_league.ID:
                feeder_players.append(ps)

        if not feeder_players:
            return []

        # Get evaluations for these players (latest per player)
        player_ids = [ps.player_id for ps in feeder_players]
        evaluations = PlayerEvaluation.query.filter(
            PlayerEvaluation.player_id.in_(player_ids),
            PlayerEvaluation.org_season_id == org_season_id
        ).all()

        # Build eval lookup: player_id -> overall_score
        eval_lookup = {}
        for ev in evaluations:
            # Keep the most recent (highest ID) evaluation
            if ev.player_id not in eval_lookup or ev.id > eval_lookup[ev.player_id][0]:
                eval_lookup[ev.player_id] = (ev.id, float(ev.overall_score) if ev.overall_score else None)

        # Get call-up counts for these players
        from sqlalchemy import func
        callup_counts = db.session.query(
            CallUpRequest.player_season_id,
            CallUpRequest.status,
            func.count(CallUpRequest.id)
        ).filter(
            CallUpRequest.player_season_id.in_([ps.id for ps in feeder_players])
        ).group_by(
            CallUpRequest.player_season_id,
            CallUpRequest.status
        ).all()

        # Build count lookup
        count_lookup = {}  # player_season_id -> {'accepted': N, 'pending': M}
        for ps_id, status, count in callup_counts:
            if ps_id not in count_lookup:
                count_lookup[ps_id] = {'accepted': 0, 'pending': 0}
            if status == 'accepted':
                count_lookup[ps_id]['accepted'] = count
            elif status == 'pending':
                count_lookup[ps_id]['pending'] = count

        # Check for conflicts (games AND practices)
        # Get all events for the same date within 3 hours of the target game
        game_date = game.game_date
        if game_date:
            conflict_window_start = game_date - timedelta(hours=3)
            conflict_window_end = game_date + timedelta(hours=3)

            # Get team IDs of feeder players
            team_ids = list(set(ps.team_id for ps in feeder_players if ps.team_id))

            # Find games/practices where feeder teams are playing
            # Include all game_types: regular, playoff, practice, scrimmage
            conflicting_events = Game.query.filter(
                Game.active == 1,
                Game.status.in_(['scheduled', 'completed']),
                Game.game_date >= conflict_window_start,
                Game.game_date <= conflict_window_end,
                Game.ID != game.ID,  # Not the same game
                db.or_(
                    Game.home_ID.in_(team_ids),
                    Game.away_ID.in_(team_ids)
                )
            ).options(
                joinedload(Game.field_rel)  # Load field for display
            ).all()

            # Build conflict lookup: team_id -> ConflictInfo
            conflict_lookup = {}
            for cg in conflicting_events:
                # Determine conflict type
                if cg.game_type == 'practice' or (cg.home_ID and not cg.away_ID):
                    conflict_type = 'practice'
                elif cg.is_scrimmage:
                    conflict_type = 'scrimmage'
                else:
                    conflict_type = 'game'

                # Format time
                time_str = cg.game_date.strftime('%I:%M %p').lstrip('0') if cg.game_date else 'TBD'

                # Get field name
                field_str = cg.field_name or 'TBD'

                conflict_info = ConflictInfo(
                    game=cg,
                    conflict_type=conflict_type,
                    time=time_str,
                    field=field_str
                )

                if cg.home_ID in team_ids:
                    conflict_lookup[cg.home_ID] = conflict_info
                if cg.away_ID in team_ids:
                    conflict_lookup[cg.away_ID] = conflict_info
        else:
            conflict_lookup = {}

        # Build result list
        results = []
        for ps in feeder_players:
            eval_data = eval_lookup.get(ps.player_id)
            eval_score = eval_data[1] if eval_data else None

            counts = count_lookup.get(ps.id, {'accepted': 0, 'pending': 0})

            conflict_info = conflict_lookup.get(ps.team_id)
            has_conflict = conflict_info is not None

            # Skip if has conflict and not including conflicts
            if has_conflict and not include_conflicts:
                continue

            results.append(EligiblePlayer(
                player_season=ps,
                player=ps.player,
                team=ps.team,
                eval_score=eval_score,
                callup_count=counts['accepted'],
                pending_count=counts['pending'],
                has_conflict=has_conflict,
                conflict_info=conflict_info
            ))

        # Sort by eval score (desc) then call-up count (asc) for equity
        results.sort(key=lambda x: (
            -(x.eval_score or 0),  # Higher scores first
            x.callup_count,  # Fewer call-ups first (equity)
            x.player.last_name or ''  # Then alphabetical
        ))

        return results

    @staticmethod
    def send_callup_email(
        to_email: str,
        subject: str,
        body_text: str,
        reply_to: str = None
    ) -> bool:
        """
        Send a call-up request email.

        Args:
            to_email: Parent email address
            subject: Email subject
            body_text: Plain text email body
            reply_to: Optional reply-to address

        Returns:
            True if sent successfully
        """
        gmail = GmailService()

        # Convert plain text to simple HTML for rich email clients
        import html
        body_html = '<p>' + html.escape(body_text).replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'

        return gmail.send_email(
            to=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            reply_to=reply_to
        )

    @staticmethod
    def build_callup_email_template(
        player: Player,
        game: Game,
        target_team: TeamSeason
    ) -> Dict[str, str]:
        """
        Build a default email template for a call-up request.

        Args:
            player: The player being asked to sub
            game: The game they're being asked to play in
            target_team: The team needing the sub

        Returns:
            Dict with 'subject' and 'body' keys (plain text)
        """
        # Format game date/time
        game_date = game.game_date.strftime('%A, %B %d') if game.game_date else 'TBD'
        game_time = game.game_date.strftime('%I:%M %p').lstrip('0') if game.game_date else 'TBD'

        subject = f"{player.first_name} - Sub request for {game_date} game"

        body = f"""Hi,

We have a game coming up that needs an extra player, and we'd like to invite {player.first_name} to sub up!

Game Details:
- Date: {game_date}
- Time: {game_time}
- Field: {game.field_name or 'TBD'}
- Team: {target_team.league_display_name} {target_team.scheduler_display_name}

Please reply to let us know if {player.first_name} is available to play.

Thanks!
SDLL Player Agent"""
        return {
            'subject': subject,
            'body': body
        }

    @staticmethod
    def get_player_callup_history(player_season_id: int) -> List[CallUpRequest]:
        """
        Get full call-up history for a player.

        Args:
            player_season_id: The player's season record ID

        Returns:
            List of CallUpRequest objects with relationships loaded
        """
        return CallUpRequest.query.filter_by(
            player_season_id=player_season_id
        ).options(
            joinedload(CallUpRequest.game),
            joinedload(CallUpRequest.target_team),
            joinedload(CallUpRequest.requester)
        ).order_by(
            CallUpRequest.requested_at.desc()
        ).all()
