"""Roster Service - manages player-team assignments and draft/roster operations."""

import csv
import io
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.player import Player, PlayerSeason
from app.models.team import TeamSeason
from app.models.league import League
from app.models.org_season import OrgSeason


@dataclass
class ExpectedColumn:
    """Definition of an expected CSV column with aliases."""
    name: str  # Internal field name
    display_name: str  # Human-readable name
    required: bool = True
    aliases: Tuple[str, ...] = ()  # Alternative names that match this column


# Expected columns for roster CSV import
EXPECTED_ROSTER_COLUMNS: List[ExpectedColumn] = [
    ExpectedColumn(
        name='Player Code',
        display_name='Player Code/ID',
        required=True,
        aliases=('player_code', 'playercode', 'player id', 'playerid', 'player_id')
    ),
    ExpectedColumn(
        name='Coach Name',
        display_name='Coach/Team Name',
        required=True,
        aliases=('coach', 'coach_name', 'team', 'team_name', 'teamname', 'head_coach')
    ),
    ExpectedColumn(
        name='Player First Name',
        display_name='Player First Name',
        required=False,
        aliases=('first_name', 'firstname', 'first', 'player first')
    ),
    ExpectedColumn(
        name='Player Last Name',
        display_name='Player Last Name',
        required=False,
        aliases=('last_name', 'lastname', 'last', 'player last')
    ),
]


@dataclass
class RosterImportRow:
    """A single row from the roster import CSV with match status."""
    row_num: int
    player_code: str
    coach_name: str
    player_first_name: Optional[str] = None
    player_last_name: Optional[str] = None
    # Match results
    player_id: Optional[int] = None
    player_season_id: Optional[int] = None
    player_display_name: Optional[str] = None
    team_id: Optional[int] = None
    team_display_name: Optional[str] = None
    # Status
    match_status: str = 'pending'  # 'matched', 'player_not_found', 'team_not_found', 'already_assigned', 'error'
    error_message: Optional[str] = None


@dataclass
class RosterImportPreview:
    """Preview of a roster import showing matches and errors."""
    rows: List[RosterImportRow] = field(default_factory=list)
    total_rows: int = 0
    matched_count: int = 0
    error_count: int = 0
    already_assigned_count: int = 0
    csv_headers: List[str] = field(default_factory=list)
    column_mapping: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class PoolStats:
    """Statistics for a player pool."""
    total: int
    unassigned: int
    by_league: Dict[str, int]
    by_status: Dict[str, int]


class RosterService:
    """Service for managing player-team roster assignments."""

    @staticmethod
    def get_player_pool(
        org_season_id: int,
        league_id: Optional[int] = None,
        status: Optional[str] = None,
        sport: Optional[str] = None
    ) -> List[PlayerSeason]:
        """Get players in the pool for a season with eager loading.

        Args:
            org_season_id: The OrgSeason ID to get players for
            league_id: Optional filter by placed_league_id
            status: Optional filter by status
            sport: Optional filter by program ('baseball' or 'softball')

        Returns:
            List of PlayerSeason objects with player and team relationships loaded
        """
        query = PlayerSeason.query.filter_by(org_season_id=org_season_id)

        # Apply filters
        if league_id:
            query = query.filter_by(placed_league_id=league_id)
        if status:
            query = query.filter_by(status=status)

        # Eager load relationships
        query = query.options(
            joinedload(PlayerSeason.player),
            joinedload(PlayerSeason.team),
            joinedload(PlayerSeason.placed_league)
        )

        # Get all results first
        results = query.all()

        # Filter by sport if specified (requires accessing player relationship)
        if sport:
            results = [ps for ps in results if ps.player and ps.player.program == sport]

        # Sort by player name
        results.sort(key=lambda ps: (
            ps.player.last_name.lower() if ps.player and ps.player.last_name else '',
            ps.player.first_name.lower() if ps.player and ps.player.first_name else ''
        ))

        return results

    @staticmethod
    def get_pool_stats(org_season_id: int, sport: Optional[str] = None) -> PoolStats:
        """Get statistics about the player pool.

        Args:
            org_season_id: The OrgSeason ID
            sport: Optional filter by program

        Returns:
            PoolStats with counts
        """
        query = PlayerSeason.query.filter_by(org_season_id=org_season_id)

        if sport:
            query = query.join(Player).filter(Player.program == sport)

        players = query.options(joinedload(PlayerSeason.placed_league)).all()

        total = len(players)
        unassigned = sum(1 for p in players if not p.team_id)

        # Count by league
        by_league = {}
        for p in players:
            league_name = p.placed_league.display_name if p.placed_league else 'Unplaced'
            by_league[league_name] = by_league.get(league_name, 0) + 1

        # Count by status
        by_status = {}
        for p in players:
            status = p.status or 'registered'
            by_status[status] = by_status.get(status, 0) + 1

        return PoolStats(
            total=total,
            unassigned=unassigned,
            by_league=by_league,
            by_status=by_status
        )

    @staticmethod
    def get_team_roster(team_id: int) -> List[PlayerSeason]:
        """Get all players assigned to a team.

        Args:
            team_id: The TeamSeason team_ID

        Returns:
            List of PlayerSeason objects with player relationships loaded
        """
        return PlayerSeason.query.filter_by(team_id=team_id).options(
            joinedload(PlayerSeason.player)
        ).all()

    @staticmethod
    def get_team_with_roster(team_id: int) -> Optional[TeamSeason]:
        """Get a team with its roster eager loaded.

        Args:
            team_id: The TeamSeason team_ID

        Returns:
            TeamSeason object with players loaded, or None
        """
        return TeamSeason.query.filter_by(team_ID=team_id).options(
            joinedload(TeamSeason.players).joinedload(PlayerSeason.player),
            joinedload(TeamSeason.league_rel)
        ).first()

    @staticmethod
    def assign_player(player_season_id: int, team_id: int) -> PlayerSeason:
        """Assign a player to a team.

        Args:
            player_season_id: The PlayerSeason ID
            team_id: The TeamSeason team_ID

        Returns:
            Updated PlayerSeason object

        Raises:
            ValueError: If player or team not found
        """
        player_season = PlayerSeason.query.get(player_season_id)
        if not player_season:
            raise ValueError(f"PlayerSeason {player_season_id} not found")

        team = TeamSeason.query.get(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found")

        # Verify they're in the same season
        org_season = OrgSeason.query.get(player_season.org_season_id)
        if org_season and (org_season.year != team.year or org_season.is_spring != team.is_spring):
            raise ValueError("Player and team must be in the same season")

        player_season.team_id = team_id
        player_season.status = 'drafted'
        db.session.commit()

        return player_season

    @staticmethod
    def unassign_player(player_season_id: int) -> PlayerSeason:
        """Remove a player from their team.

        Args:
            player_season_id: The PlayerSeason ID

        Returns:
            Updated PlayerSeason object

        Raises:
            ValueError: If player not found
        """
        player_season = PlayerSeason.query.get(player_season_id)
        if not player_season:
            raise ValueError(f"PlayerSeason {player_season_id} not found")

        player_season.team_id = None
        # Revert status - if they were drafted, go back to placed (or evaluated if no placement)
        if player_season.status == 'drafted':
            if player_season.placed_league_id:
                player_season.status = 'placed'
            else:
                player_season.status = 'evaluated'
        db.session.commit()

        return player_season

    @staticmethod
    def get_available_teams(
        org_season_id: int,
        league_id: Optional[int] = None
    ) -> List[TeamSeason]:
        """Get teams available for assignment.

        Args:
            org_season_id: The OrgSeason ID
            league_id: Optional filter by league_id

        Returns:
            List of TeamSeason objects
        """
        org_season = OrgSeason.query.get(org_season_id)
        if not org_season:
            return []

        query = TeamSeason.query.filter_by(
            year=org_season.year,
            is_spring=org_season.is_spring,
            active=1,
            is_placeholder=0
        ).options(
            joinedload(TeamSeason.league_rel)
        )

        if league_id:
            query = query.filter_by(league_id=league_id)

        return query.order_by(TeamSeason.league_id, TeamSeason.display_name).all()

    @staticmethod
    def get_leagues_for_season(org_season_id: int, sport: Optional[str] = None) -> List[League]:
        """Get leagues that have teams in a season.

        Args:
            org_season_id: The OrgSeason ID
            sport: Optional filter by sport

        Returns:
            List of League objects
        """
        org_season = OrgSeason.query.get(org_season_id)
        if not org_season:
            return []

        # Get league IDs from teams in this season
        team_query = db.session.query(TeamSeason.league_id).filter(
            TeamSeason.year == org_season.year,
            TeamSeason.is_spring == org_season.is_spring,
            TeamSeason.active == 1,
            TeamSeason.league_id.isnot(None)
        ).distinct()

        league_ids = [row[0] for row in team_query.all()]

        if not league_ids:
            return []

        query = League.query.filter(
            League.ID.in_(league_ids),
            League.active == 1
        )

        if sport:
            query = query.filter_by(sport=sport)

        return query.order_by(League.sort_order, League.display_name).all()

    @staticmethod
    def bulk_assign_players(assignments: List[Dict[str, int]]) -> Dict[str, Any]:
        """Bulk assign multiple players to teams.

        Args:
            assignments: List of dicts with 'player_season_id' and 'team_id'

        Returns:
            Dict with 'success_count', 'error_count', 'errors'
        """
        success_count = 0
        error_count = 0
        errors = []

        for assignment in assignments:
            try:
                RosterService.assign_player(
                    assignment['player_season_id'],
                    assignment['team_id']
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"Player {assignment.get('player_season_id')}: {str(e)}")

        return {
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors
        }

    # =========================================================================
    # CSV Import Methods
    # =========================================================================

    @staticmethod
    def auto_map_columns(csv_headers: List[str]) -> Dict[str, Optional[str]]:
        """Automatically map CSV headers to expected columns.

        Args:
            csv_headers: List of column headers from the CSV

        Returns:
            Dict mapping internal field names to CSV header names
        """
        mapping = {}
        csv_headers_lower = {h.lower().strip(): h for h in csv_headers}

        for expected in EXPECTED_ROSTER_COLUMNS:
            # Try exact match first (case-insensitive)
            if expected.name.lower() in csv_headers_lower:
                mapping[expected.name] = csv_headers_lower[expected.name.lower()]
                continue

            # Try aliases
            matched = False
            for alias in expected.aliases:
                if alias.lower() in csv_headers_lower:
                    mapping[expected.name] = csv_headers_lower[alias.lower()]
                    matched = True
                    break

            if not matched:
                mapping[expected.name] = None

        return mapping

    @staticmethod
    def all_required_columns_mapped(column_mapping: Dict[str, Optional[str]]) -> bool:
        """Check if all required columns are mapped."""
        for expected in EXPECTED_ROSTER_COLUMNS:
            if expected.required and not column_mapping.get(expected.name):
                return False
        return True

    @staticmethod
    def parse_roster_csv(
        csv_content: str,
        org_season_id: int,
        column_mapping: Optional[Dict[str, Optional[str]]] = None
    ) -> RosterImportPreview:
        """Parse roster CSV and preview matches.

        Args:
            csv_content: CSV file content as string
            org_season_id: The OrgSeason ID for the import
            column_mapping: Optional custom column mapping

        Returns:
            RosterImportPreview with match results
        """
        preview = RosterImportPreview()

        # Parse CSV
        stream = io.StringIO(csv_content)
        reader = csv.DictReader(stream)
        preview.csv_headers = reader.fieldnames or []

        # Auto-map columns if not provided
        if column_mapping is None:
            column_mapping = RosterService.auto_map_columns(preview.csv_headers)
        preview.column_mapping = column_mapping

        # Get org_season
        org_season = OrgSeason.query.get(org_season_id)
        if not org_season:
            return preview

        # Pre-load players and teams for fast lookup
        player_cache = {}  # player_code -> (player_id, first_name, last_name)
        players = Player.query.all()
        for p in players:
            if p.player_code:
                player_cache[p.player_code.lower()] = (p.id, p.first_name, p.last_name)

        # Build player_season lookup
        season_cache = {}  # player_id -> PlayerSeason
        player_seasons = PlayerSeason.query.filter_by(
            org_season_id=org_season_id
        ).options(joinedload(PlayerSeason.team)).all()
        for ps in player_seasons:
            season_cache[ps.player_id] = ps

        # Build team lookup by coach name
        team_cache = {}  # normalized coach name -> TeamSeason
        teams = TeamSeason.query.filter_by(
            year=org_season.year,
            is_spring=org_season.is_spring,
            active=1,
            is_placeholder=0
        ).options(joinedload(TeamSeason.league_rel)).all()

        for t in teams:
            if t.coach_name:
                # Normalize: lowercase, remove extra spaces
                normalized = t.coach_name.lower().strip()
                team_cache[normalized] = t
                # Also add last name only
                parts = normalized.split()
                if parts:
                    team_cache[parts[-1]] = t  # Last name only

        # Helper to get field value
        def get_field(row, field_name):
            csv_col = column_mapping.get(field_name)
            if csv_col:
                return row.get(csv_col, '').strip()
            return ''

        # Process rows
        rows = list(reader)
        preview.total_rows = len(rows)

        for i, row in enumerate(rows, start=2):
            player_code = get_field(row, 'Player Code')
            coach_name = get_field(row, 'Coach Name')
            first_name = get_field(row, 'Player First Name')
            last_name = get_field(row, 'Player Last Name')

            import_row = RosterImportRow(
                row_num=i,
                player_code=player_code,
                coach_name=coach_name,
                player_first_name=first_name,
                player_last_name=last_name
            )

            # Skip empty rows
            if not player_code and not coach_name:
                continue

            # Find player by code
            player_data = player_cache.get(player_code.lower()) if player_code else None

            if player_data:
                import_row.player_id = player_data[0]
                import_row.player_display_name = f"{player_data[2]}, {player_data[1]}"

                # Find player season
                player_season = season_cache.get(player_data[0])
                if player_season:
                    import_row.player_season_id = player_season.id

                    # Check if already assigned
                    if player_season.team_id:
                        import_row.match_status = 'already_assigned'
                        import_row.team_id = player_season.team_id
                        if player_season.team:
                            import_row.team_display_name = f"{player_season.team.league_display_name} {player_season.team.scheduler_display_name}"
                        preview.already_assigned_count += 1
                        preview.rows.append(import_row)
                        continue
                else:
                    import_row.match_status = 'player_not_found'
                    import_row.error_message = f"Player {player_code} not registered for this season"
                    preview.error_count += 1
                    preview.rows.append(import_row)
                    continue
            else:
                import_row.match_status = 'player_not_found'
                import_row.error_message = f"Player code '{player_code}' not found"
                preview.error_count += 1
                preview.rows.append(import_row)
                continue

            # Find team by coach name
            if coach_name:
                normalized_coach = coach_name.lower().strip()
                team = team_cache.get(normalized_coach)

                # Try last name only if full match failed
                if not team:
                    parts = normalized_coach.split()
                    if parts:
                        team = team_cache.get(parts[-1])

                if team:
                    import_row.team_id = team.team_ID
                    import_row.team_display_name = f"{team.league_display_name} {team.scheduler_display_name}"
                    import_row.match_status = 'matched'
                    preview.matched_count += 1
                else:
                    import_row.match_status = 'team_not_found'
                    import_row.error_message = f"Coach '{coach_name}' not found"
                    preview.error_count += 1
            else:
                import_row.match_status = 'team_not_found'
                import_row.error_message = "No coach name provided"
                preview.error_count += 1

            preview.rows.append(import_row)

        return preview

    @staticmethod
    def execute_roster_import(preview: RosterImportPreview) -> Dict[str, Any]:
        """Execute roster import from preview.

        Args:
            preview: RosterImportPreview with matched rows

        Returns:
            Dict with success_count, error_count, errors
        """
        success_count = 0
        error_count = 0
        errors = []

        for row in preview.rows:
            if row.match_status != 'matched':
                continue

            if not row.player_season_id or not row.team_id:
                error_count += 1
                errors.append(f"Row {row.row_num}: Missing player or team ID")
                continue

            try:
                player_season = PlayerSeason.query.get(row.player_season_id)
                if player_season:
                    player_season.team_id = row.team_id
                    player_season.status = 'drafted'
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"Row {row.row_num}: PlayerSeason not found")
            except Exception as e:
                error_count += 1
                errors.append(f"Row {row.row_num}: {str(e)}")

        db.session.commit()

        return {
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors
        }
