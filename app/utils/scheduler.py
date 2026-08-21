"""Schedule generator and validator for SDLL games, practices, and scrimmages.

Time-based scheduling (defaults, can be overridden per league):
- Regular games: 2 hours (120 minutes) - Tee Ball: 75 minutes
- No-time-limit games: 3 hours (180 minutes)
- Practices: 90 minutes - Tee Ball: 75 minutes

A field slot's capacity is determined by both:
1. The slot duration (end_time - start_time)
2. The field's practice_capacity setting (for shared practices)
3. The league's game/practice duration settings
"""

from datetime import date, datetime, time, timedelta
from collections import defaultdict
import random

# Default activity durations in minutes (leagues can override via game_duration_minutes/practice_duration_minutes)
GAME_DURATION_MINUTES = 120  # 2 hours for regular games (default)
GAME_NO_LIMIT_DURATION_MINUTES = 180  # 3 hours for no-time-limit games
PRACTICE_DURATION_MINUTES = 90  # 90 minutes for practices (default)
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.field import Field
from app.models.field_slot import FieldSlot
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.extensions import db


class ScheduleViolation:
    """Represents a rule violation in the schedule."""

    HARD = 'hard'  # Cannot be violated
    SOFT = 'soft'  # Preferably not violated

    def __init__(self, rule_code, rule_name, severity, message, games=None, teams=None):
        self.rule_code = rule_code
        self.rule_name = rule_name
        self.severity = severity
        self.message = message
        self.games = games or []
        self.teams = teams or []  # List of {'id': team_id, 'name': team_name}

    def to_dict(self):
        def get_game_id(g):
            # Handle database Game objects (uppercase ID)
            if hasattr(g, 'ID'):
                return g.ID
            # Handle ProposedGame objects (lowercase id)
            if hasattr(g, 'id'):
                return g.id
            # Handle dict (from serialized data)
            if isinstance(g, dict):
                return g.get('id')
            return None

        return {
            'rule_code': self.rule_code,
            'rule_name': self.rule_name,
            'severity': self.severity,
            'message': self.message,
            'game_ids': [get_game_id(g) for g in self.games],
            'teams': self.teams  # List of {'id': team_id, 'name': team_name}
        }


class ProposedGame:
    """Represents a proposed game/practice/scrimmage before it's saved."""

    def __init__(self, game_type, league, year, is_spring,
                 home_team=None, away_team=None,
                 field=None, game_date=None,
                 is_scrimmage=False):
        self.id = None  # Assigned when added to proposal
        self.game_type = game_type  # 'regular', 'playoff', 'practice', 'scrimmage'
        self.league = league
        self.year = year
        self.is_spring = is_spring
        self.home_team = home_team  # TeamSeason object or None
        self.away_team = away_team  # TeamSeason object or None (None for practice)
        self.field = field  # Field object or None
        self.game_date = game_date  # datetime or None
        self.is_scrimmage = is_scrimmage
        self.slot = None  # FieldSlot if assigned

    def to_dict(self):
        return {
            'id': self.id,
            'game_type': self.game_type,
            'league': self.league,
            'year': self.year,
            'is_spring': self.is_spring,
            'home_team_id': self.home_team.team_ID if self.home_team else None,
            'home_team_name': self.home_team.scheduler_display_name if self.home_team else None,
            'away_team_id': self.away_team.team_ID if self.away_team else None,
            'away_team_name': self.away_team.scheduler_display_name if self.away_team else None,
            'field_id': self.field.ID if self.field else None,
            'field_name': self.field.location_title if self.field else None,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'is_scrimmage': self.is_scrimmage,
            'slot_id': self.slot.slot_ID if self.slot else None
        }


class ScheduleValidator:
    """Validates schedules against hard and soft rules."""

    def __init__(self, year, is_spring, fields_cache=None, field_blackouts_cache=None, league_cache=None):
        self.year = year
        self.is_spring = is_spring
        self.violations = []
        self._team_names = {}  # Cache: team_id -> team_name
        self._league_configs = {}  # Cache: league_name -> LeagueSeason config
        # Accept pre-loaded caches to avoid DB queries
        self._fields_cache = fields_cache or {}
        self._field_blackouts_cache = field_blackouts_cache or {}
        self._league_cache = league_cache or {}
        # Load practice pairings for violation exemptions
        from app.models.practice_pairing import PracticePairing
        self._paired_team_pairs = PracticePairing.get_pairing_pairs(year, is_spring)

    def _get_team_name(self, team_id):
        """Get team name from ID (with caching)."""
        if team_id is None:
            return None
        if team_id not in self._team_names:
            # Try to look up from database
            from app.models.team import TeamSeason
            team = TeamSeason.query.filter_by(team_ID=team_id).first()
            if team:
                self._team_names[team_id] = team.scheduler_display_name or team.display_name or str(team_id)
            else:
                self._team_names[team_id] = str(team_id)
        return self._team_names[team_id]

    def _build_team_info(self, team_id):
        """Build team info dict for violation."""
        return {'id': team_id, 'name': self._get_team_name(team_id)}

    def _is_field_available_on_date(self, field_id, check_date):
        """Check if field is available on date using cached data (no DB queries)."""
        # Convert datetime to date if needed
        if hasattr(check_date, 'date'):
            check_date = check_date.date()

        # Get field from cache
        field = self._fields_cache.get(field_id)
        if not field:
            return True  # If not in cache, assume available

        # Check start date
        if field.start_date and check_date < field.start_date:
            return False

        # Check field-specific blackouts from cache
        blackout_dates = self._field_blackouts_cache.get(field_id, [])
        if check_date in blackout_dates:
            return False

        return True

    def validate(self, games):
        """Validate a list of games/proposed games.

        Args:
            games: List of Game or ProposedGame objects

        Returns:
            List of ScheduleViolation objects
        """
        self.violations = []
        self._team_names = {}  # Reset cache
        self._league_configs = {}  # Reset league config cache
        self._all_games = games  # Store for cross-reference in f2 validation

        # Load league configurations for minimum games requirement
        league_configs = LeagueSeason.get_by_season(self.year, self.is_spring)
        for config in league_configs:
            self._league_configs[config.league] = config

        # Pre-cache team names from game objects
        for g in games:
            if hasattr(g, 'home_team') and g.home_team:
                team = g.home_team
                team_id = team.team_ID if hasattr(team, 'team_ID') else None
                if team_id:
                    name = getattr(team, 'scheduler_display_name', None) or getattr(team, 'display_name', None) or str(team_id)
                    self._team_names[team_id] = name
            if hasattr(g, 'away_team') and g.away_team:
                team = g.away_team
                team_id = team.team_ID if hasattr(team, 'team_ID') else None
                if team_id:
                    name = getattr(team, 'scheduler_display_name', None) or getattr(team, 'display_name', None) or str(team_id)
                    self._team_names[team_id] = name

        # Group games by league
        games_by_league = defaultdict(list)
        for g in games:
            if hasattr(g, 'league') and g.league:
                games_by_league[g.league].append(g)

        for league, league_games in games_by_league.items():
            self._validate_league(league, league_games)

        # Cross-league validation: Check for field double-booking
        self._check_field_conflicts(games)

        # Cross-league validation: Check practice field capacity
        self._check_practice_field_capacity(games)

        # Cross-league validation: Check season blackout dates (HARD)
        self._check_season_blackouts(games)

        # Cross-league validation: Check field availability (start dates and field blackouts) (HARD)
        self._check_field_availability(games)

        return self.violations

    def _validate_league(self, league, games):
        """Validate games for a single league."""
        # Get only actual games (not practices)
        actual_games = [g for g in games if self._is_actual_game(g)]

        if not actual_games:
            return

        # Get teams
        teams = set()
        for g in actual_games:
            if self._get_home_team(g):
                teams.add(self._get_home_team(g))
            if self._get_away_team(g):
                teams.add(self._get_away_team(g))

        teams = list(teams)
        if len(teams) < 2:
            return

        # Rule a1: Play everyone at least once, no more than 1 game difference
        self._check_matchup_balance(league, actual_games, teams)

        # Rule b1: Balance home/away per team
        self._check_home_away_balance(league, actual_games, teams)

        # Rule a2: No team is home twice against same opponent
        self._check_home_away_vs_opponent(league, actual_games, teams)

        # Rule b2: Balance early (4-6pm) vs late (6pm+) games per team
        self._check_time_balance(league, actual_games, teams)

        # Rule c2: Balance practice fields
        practices = [g for g in games if self._is_practice(g)]
        if practices:
            self._check_practice_field_balance(league, practices, teams)
            # Rule c3: Balance solo practices
            self._check_solo_practice_balance(league, practices, teams)
            # Rule c4: Practice count balance - no team should have 2+ more practices than others
            self._check_practice_count_balance(league, practices, teams)
            # Rule f2: Unnecessary field sharing - flag sharing when empty fields available
            self._check_unnecessary_sharing(league, practices, teams)

        # Rule c5: Expected practice count - each team should have the expected number of practices
        # Note: Called regardless of whether there are scheduled practices, since division practices count
        self._check_expected_practice_count(league, practices, teams)

        # Check no back-to-back against same team
        self._check_same_team_gap(league, actual_games, teams)

        # Rule d1: One game/practice per team per day
        self._check_one_activity_per_day(league, games, teams)

        # Rule e1: Minimum games per team (HARD)
        # Only count regular and playoff games - scrimmages don't count
        counting_games = [g for g in games if self._is_counting_game(g)]
        self._check_minimum_games(league, counting_games, teams)

        # Rule e2: All teams play on same game days (SOFT)
        # Also only check counting games (regular + playoff)
        self._check_game_day_balance(league, counting_games, teams)

        # Rule f1: Day-of-week game balance for P/G leagues
        # No team should have 2+ more games on a given day of week than another team
        self._check_day_of_week_game_balance(league, counting_games, teams)

        # Rule g1: Time restrictions (HARD)
        # No games/practices can start after league's latest_start_time or before earliest_start_time
        self._check_time_restrictions(league, games)

    def _is_actual_game(self, game):
        """Check if this is an actual game (not practice).

        Includes regular, playoff, and scrimmage games.
        """
        if hasattr(game, 'game_type'):
            return game.game_type in ('regular', 'playoff', 'scrimmage')
        return game.away_ID is not None

    def _is_counting_game(self, game):
        """Check if this game counts toward minimum games requirement.

        Only regular season and playoff games count.
        Scrimmages do NOT count toward minimum games.
        """
        if hasattr(game, 'game_type'):
            return game.game_type in ('regular', 'playoff')
        # For database Game objects, check is_scrimmage flag
        if hasattr(game, 'is_scrimmage') and game.is_scrimmage:
            return False
        return game.away_ID is not None

    def _is_practice(self, game):
        """Check if this is a practice."""
        if hasattr(game, 'game_type'):
            return game.game_type == 'practice'
        return game.away_ID is None

    def _get_home_team(self, game):
        """Get home team ID."""
        if hasattr(game, 'home_team') and game.home_team:
            return game.home_team.team_ID if hasattr(game.home_team, 'team_ID') else game.home_team
        if hasattr(game, 'home_ID'):
            return game.home_ID
        return None

    def _get_away_team(self, game):
        """Get away team ID."""
        if hasattr(game, 'away_team') and game.away_team:
            return game.away_team.team_ID if hasattr(game.away_team, 'team_ID') else game.away_team
        if hasattr(game, 'away_ID'):
            return game.away_ID
        return None

    def _get_game_date(self, game):
        """Get game date."""
        if hasattr(game, 'game_date'):
            return game.game_date
        return None

    def _get_start_time(self, game):
        """Get game start time as hour (e.g., 17.5 for 5:30 PM)."""
        game_date = self._get_game_date(game)
        if game_date:
            return game_date.hour + game_date.minute / 60
        return None

    def _get_league(self, game):
        """Get league name from game."""
        if hasattr(game, 'league'):
            return game.league
        return None

    def _check_matchup_balance(self, league, games, teams):
        """Rule a1: Play everyone at least once, max 1 game difference.

        Note: If total games < total pairs, it's mathematically impossible
        for all pairs to play. In that case, unplayed pairs are reported
        as SOFT (unavoidable) rather than HARD (fixable).
        """
        matchup_counts = defaultdict(int)

        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home and away:
                key = tuple(sorted([home, away]))
                matchup_counts[key] += 1

        # Calculate mathematical limits
        n = len(teams)
        total_games = len(games)
        total_pairs = n * (n - 1) // 2
        all_pairs_possible = total_games >= total_pairs

        # Check each pair of teams
        min_games = float('inf')
        max_games = 0
        unplayed_pairs = []

        for i, t1 in enumerate(teams):
            for t2 in teams[i+1:]:
                key = tuple(sorted([t1, t2]))
                count = matchup_counts.get(key, 0)
                if count == 0:
                    unplayed_pairs.append((t1, t2))
                min_games = min(min_games, count)
                max_games = max(max_games, count)

        if unplayed_pairs:
            # Only HARD violation if mathematically possible to have all pairs play
            severity = ScheduleViolation.HARD if all_pairs_possible else ScheduleViolation.SOFT
            note = "" if all_pairs_possible else f" (only {total_games} games for {total_pairs} pairs)"
            self.violations.append(ScheduleViolation(
                'a1', 'Play everyone at least once',
                severity,
                f'{league}: {len(unplayed_pairs)} team pairs have not played each other{note}'
            ))

        # Check matchup imbalance (max gap > 1)
        # For cases where total_games < total_pairs, min_games will be 0, max_games 1,
        # and gap = 1 is acceptable (unavoidable)
        if max_games - min_games > 1:
            self.violations.append(ScheduleViolation(
                'a1', 'Matchup balance',
                ScheduleViolation.HARD,
                f'{league}: Matchup imbalance - some pairs played {max_games}x while others only {min_games}x'
            ))

    def _check_home_away_balance(self, league, games, teams):
        """Rule b1: Balance home/away per team."""
        home_counts = defaultdict(int)
        away_counts = defaultdict(int)

        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home:
                home_counts[home] += 1
            if away:
                away_counts[away] += 1

        for team_id in teams:
            home = home_counts.get(team_id, 0)
            away = away_counts.get(team_id, 0)
            diff = abs(home - away)
            if diff > 1:
                team_name = self._get_team_name(team_id)
                self.violations.append(ScheduleViolation(
                    'b1', 'Home/away balance',
                    ScheduleViolation.HARD,
                    f'{league}: Team {team_name} has {home} home games and {away} away games (diff: {diff})',
                    teams=[self._build_team_info(team_id)]
                ))

    def _check_home_away_vs_opponent(self, league, games, teams):
        """Rule a2: No team home twice vs same opponent."""
        home_vs_opponent = defaultdict(lambda: defaultdict(int))

        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home and away:
                home_vs_opponent[home][away] += 1

        for team_id, opponents in home_vs_opponent.items():
            for opponent_id, home_count in opponents.items():
                away_count = home_vs_opponent.get(opponent_id, {}).get(team_id, 0)
                if home_count >= 2 and away_count == 0:
                    team_name = self._get_team_name(team_id)
                    opponent_name = self._get_team_name(opponent_id)
                    self.violations.append(ScheduleViolation(
                        'a2', 'Home/away vs opponent',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team_name} is home {home_count}x vs {opponent_name} but never away',
                        teams=[self._build_team_info(team_id), self._build_team_info(opponent_id)]
                    ))

    def _check_time_balance(self, league, games, teams):
        """Rule b2: Balance late game counts BETWEEN teams.

        All teams in a league should have roughly the same number of late games.
        Late games = 6:00 PM or later.

        If a league has NO late games at all (no late slots available), skip this
        check since there's nothing to balance.
        """
        late_counts = defaultdict(int)   # 6:00 PM or later

        for g in games:
            start_time = self._get_start_time(g)
            if start_time is None:
                continue

            # Only count late games (6pm or later)
            if start_time >= 18:
                home = self._get_home_team(g)
                away = self._get_away_team(g)
                if home:
                    late_counts[home] += 1
                if away:
                    late_counts[away] += 1

        # If there are NO late games in this league at all, skip the check
        total_late = sum(late_counts.values())
        if total_late == 0:
            return

        # Check balance BETWEEN teams - all should have similar late game counts
        team_late_counts = [late_counts.get(team_id, 0) for team_id in teams]
        if not team_late_counts:
            return

        min_late = min(team_late_counts)
        max_late = max(team_late_counts)

        # Allow difference of up to 2 late games between teams
        if max_late - min_late > 2:
            # Find teams that are outliers
            for team_id in teams:
                team_late = late_counts.get(team_id, 0)
                # Flag teams with significantly more or fewer late games than average
                if team_late == max_late and max_late - min_late > 2:
                    team_name = self._get_team_name(team_id)
                    self.violations.append(ScheduleViolation(
                        'b2', 'Late game balance between teams',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team_name} has {team_late} late games (league range: {min_late}-{max_late})',
                        teams=[self._build_team_info(team_id)]
                    ))
                elif team_late == min_late and max_late - min_late > 2:
                    team_name = self._get_team_name(team_id)
                    self.violations.append(ScheduleViolation(
                        'b2', 'Late game balance between teams',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team_name} has {team_late} late games (league range: {min_late}-{max_late})',
                        teams=[self._build_team_info(team_id)]
                    ))

    def _check_practice_field_balance(self, league, practices, teams):
        """Rule c2: Balance practice field usage."""
        field_counts = defaultdict(lambda: defaultdict(int))

        for p in practices:
            team = self._get_home_team(p)
            field = None
            if hasattr(p, 'field') and p.field:
                field = p.field.ID if hasattr(p.field, 'ID') else p.field
            elif hasattr(p, 'location'):
                field = p.location

            if team and field:
                field_counts[team][field] += 1

        # Check each team's field distribution
        for team_id in teams:
            counts = field_counts.get(team_id, {})
            if len(counts) > 1:
                values = list(counts.values())
                if max(values) - min(values) > 2:
                    team_name = self._get_team_name(team_id)
                    self.violations.append(ScheduleViolation(
                        'c2', 'Practice field balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team_name} has uneven practice field distribution',
                        teams=[self._build_team_info(team_id)]
                    ))

    def _check_solo_practice_balance(self, league, practices, teams):
        """Rule c3: Balance solo practice opportunities.

        A solo practice is when a team has the field to themselves (no other teams
        practicing at the same field at the same time).
        """
        # Group practices by (field, date, time)
        practices_by_slot = defaultdict(list)
        for p in practices:
            game_date = self._get_game_date(p)
            if not game_date:
                continue

            field = None
            if hasattr(p, 'field') and p.field:
                field = p.field.ID if hasattr(p.field, 'ID') else p.field
            elif hasattr(p, 'location'):
                field = p.location

            if field:
                key = (field, game_date.date(), game_date.hour)
                practices_by_slot[key].append(p)

        # Count solo practices per team
        solo_counts = defaultdict(int)
        for key, slot_practices in practices_by_slot.items():
            if len(slot_practices) == 1:
                # This is a solo practice
                team = self._get_home_team(slot_practices[0])
                if team:
                    solo_counts[team] += 1

        # Check balance across teams
        if solo_counts:
            counts = [solo_counts.get(t, 0) for t in teams]
            if counts:
                min_solo = min(counts)
                max_solo = max(counts)
                if max_solo - min_solo > 1:
                    self.violations.append(ScheduleViolation(
                        'c3', 'Solo practice balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Solo practice imbalance - some teams have {max_solo} solo practices while others have {min_solo}'
                    ))

    def _check_practice_count_balance(self, league, practices, teams):
        """Rule c4: No team should have 2+ more practices than any other team.

        This ensures fair practice opportunities across all teams in a league.
        """
        # Count practices per team
        practice_counts = defaultdict(int)
        for p in practices:
            team = self._get_home_team(p)
            if team:
                practice_counts[team] += 1

        # Check balance across teams
        if practice_counts:
            counts = [practice_counts.get(t, 0) for t in teams]
            if counts:
                min_count = min(counts)
                max_count = max(counts)
                if max_count - min_count >= 2:
                    # Find which teams are affected
                    min_teams = [t for t in teams if practice_counts.get(t, 0) == min_count]
                    max_teams = [t for t in teams if practice_counts.get(t, 0) == max_count]

                    self.violations.append(ScheduleViolation(
                        'c4', 'Practice count balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Practice count imbalance of {max_count - min_count}. '
                        f'{", ".join(self._get_team_name(t) for t in max_teams)} have {max_count} practices, '
                        f'{", ".join(self._get_team_name(t) for t in min_teams)} have {min_count}.',
                        teams=[self._build_team_info(t) for t in min_teams + max_teams]
                    ))

    def _check_expected_practice_count(self, league, practices, teams):
        """Rule c5: Each team should have the expected number of practices.

        For non-P/G leagues:
            Expected = A + B where:
            - A = practice days from first_practice to regular_season_end (excluding blackouts)
            - B = game days before opening_day (pre-season practices)

        For P/G leagues (where practice and game days overlap):
            Expected = A + B where:
            - A = weeks from opening_day to regular_season_end (1 practice per week)
            - B = all activity days before opening_day (pre-season practices)

        Note: If a team has specific practice days configured, those are used instead of
        the league's practice days to avoid overcounting.

        Actual practices = division practices (is_league_practice) + scheduled practices
        """
        from app.models.season_blackout import SeasonBlackout
        from datetime import timedelta

        config = self._league_configs.get(league)
        if not config:
            return

        first_practice = config.first_practice_date
        opening_day = config.opening_day_date
        regular_season_end = config.regular_season_end_date

        if not first_practice or not opening_day or not regular_season_end:
            return

        # Get blackout dates
        blackout_dates = SeasonBlackout.get_blackout_dates_set(self.year, self.is_spring)

        # Check if this is a P/G league
        is_pg_league = config.has_pg_days

        # Get game day numbers from league config (0=Monday, 1=Tuesday, etc.)
        game_day_nums = set(config.game_days)  # Days marked as game (or both)
        practice_day_nums_league = set(config.practice_days)  # Days marked as practice (or both)
        all_activity_days = game_day_nums | practice_day_nums_league

        # Get teams for this league to access team-specific practice days
        from app.models.team import TeamSeason
        league_teams = TeamSeason.query.filter_by(
            league=league, year=self.year, is_spring=self.is_spring, active=True
        ).all()
        team_objects = {t.team_ID: t for t in league_teams}

        # Count actual practices per team
        # Division practices (is_league_practice=True) count for ALL teams
        # Regular practices count only for the assigned team
        practice_counts = defaultdict(int)
        division_practice_count = 0

        for p in practices:
            is_division = getattr(p, 'is_league_practice', False)
            if is_division:
                division_practice_count += 1
            else:
                team = self._get_home_team(p)
                if team:
                    practice_counts[team] += 1

        # Calculate expected practices per team (team-specific practice days may differ)
        for team_id in teams:
            team_obj = team_objects.get(team_id)

            # Get practice days for this specific team (uses team's days if set, else league's)
            if team_obj:
                practice_day_nums = set(team_obj.get_practice_days(config))
            else:
                practice_day_nums = set(config.practice_days)

            # Check if team has specific practice days configured
            team_has_specific_days = team_obj and team_obj.practice_days

            # Calculate pre-opening practices
            # Count only practice days (league's or team's specific days)
            # The scheduler only schedules practices on practice days, not game days
            pre_opening_practice_count = 0
            current_date = first_practice
            while current_date < opening_day:
                if current_date not in blackout_dates:
                    day_of_week = current_date.weekday()
                    # Always use practice_day_nums (team's specific days or league's practice days)
                    if day_of_week in practice_day_nums:
                        pre_opening_practice_count += 1
                current_date += timedelta(days=1)

            # Calculate post-opening expected practices
            if is_pg_league:
                # P/G leagues: 1 practice per week after opening day
                post_opening_weeks = (regular_season_end - opening_day).days // 7 + 1
                post_opening_practice_count = post_opening_weeks
            else:
                # Non-P/G leagues: count actual practice days
                post_opening_practice_count = 0
                current_date = opening_day
                while current_date <= regular_season_end:
                    if current_date not in blackout_dates:
                        day_of_week = current_date.weekday()
                        if day_of_week in practice_day_nums:
                            post_opening_practice_count += 1
                    current_date += timedelta(days=1)

            expected_practices = pre_opening_practice_count + post_opening_practice_count

            if expected_practices == 0:
                continue

            # Each team's total = individual practices + division practices
            actual = practice_counts.get(team_id, 0) + division_practice_count
            if actual < expected_practices:
                shortfall = expected_practices - actual
                team_name = self._get_team_name(team_id)
                if is_pg_league:
                    detail = f'Pre-opening: {pre_opening_practice_count}, Post-opening weeks: {post_opening_practice_count}'
                else:
                    detail = f'Pre-opening: {pre_opening_practice_count}, Post-opening days: {post_opening_practice_count}'
                self.violations.append(ScheduleViolation(
                    'c5', 'Expected practice count',
                    ScheduleViolation.HARD,
                    f'{league}: {team_name} has {actual} practices but expected {expected_practices} '
                    f'(shortfall: {shortfall}). {detail}, Division practices: {division_practice_count}.',
                    teams=[self._build_team_info(team_id)]
                ))

    def _check_unnecessary_sharing(self, league, practices, teams):
        """Rule f2: Unnecessary field sharing.

        Teams should not share a practice field when another eligible practice field
        for that league is empty at the same time. Coaches prefer being alone at a
        non-preferred field over sharing their preferred field with another team.

        Note: Only considers fields that have slots at the SAME TIME (hour:minute)
        across any date in the season. Also considers practice duration - a field
        must be empty for the entire practice duration to be considered available.
        """
        if not practices:
            return

        # Get practice duration for this league
        league_obj = self._league_cache.get(league) if hasattr(self, '_league_cache') else None
        if not league_obj:
            league_obj = League.get_by_name(league)
        practice_duration = league_obj.get_practice_duration() if league_obj else 90

        # Build set of fields actually used for this league's practices
        fields_with_slots = set()
        for p in practices:
            field = None
            if hasattr(p, 'field') and p.field:
                field = p.field.ID if hasattr(p.field, 'ID') else p.field
            elif hasattr(p, 'location'):
                field = p.location
            if field:
                fields_with_slots.add(field)

        if len(fields_with_slots) < 2:
            # Need at least 2 fields to have a sharing violation
            return

        # Build map of which fields have slots at which (day_of_week, hour, minute) combinations
        # across ALL dates. This tells us which fields have time slots on specific days at specific times.
        # Key is (day_of_week, hour, minute) to match the assignment logic's day-based slot filtering.
        fields_by_dow_time_slot = defaultdict(set)  # (day_of_week, hour, minute) -> set of field_ids
        for p in practices:
            game_date = self._get_game_date(p)
            if not game_date:
                continue
            field = None
            if hasattr(p, 'field') and p.field:
                field = p.field.ID if hasattr(p.field, 'ID') else p.field
            elif hasattr(p, 'location'):
                field = p.location
            if field:
                time_key = (game_date.weekday(), game_date.hour, game_date.minute)
                fields_by_dow_time_slot[time_key].add(field)

        # Group practices by (date, hour, minute) - slot level
        practices_by_datetime = defaultdict(list)
        for p in practices:
            game_date = self._get_game_date(p)
            if not game_date:
                continue
            field = None
            if hasattr(p, 'field') and p.field:
                field = p.field.ID if hasattr(p.field, 'ID') else p.field
            elif hasattr(p, 'location'):
                field = p.location
            if field:
                key = (game_date.date(), game_date.hour, game_date.minute)
                practices_by_datetime[key].append({
                    'practice': p,
                    'field_id': field,
                    'datetime': game_date
                })

        # Build a lookup of ALL activities by (field_id, date) for overlap checking
        # Uses self._all_games to check against ALL leagues' activities, not just this league
        all_activities_by_field_date = defaultdict(list)
        for activity in getattr(self, '_all_games', practices):
            game_date = self._get_game_date(activity)
            if not game_date:
                continue
            field = None
            if hasattr(activity, 'field') and activity.field:
                field = activity.field.ID if hasattr(activity.field, 'ID') else activity.field
            elif hasattr(activity, 'location'):
                field = activity.location
            if field:
                # Store tuple of (start_time, duration) for accurate overlap checking
                # Use game duration for games, practice duration for practices
                is_practice = self._is_practice(activity)
                activity_league = getattr(activity, 'league', league)
                league_obj = self._league_cache.get(activity_league) if hasattr(self, '_league_cache') else None
                if not league_obj:
                    league_obj = League.get_by_name(activity_league)
                if is_practice:
                    duration = league_obj.get_practice_duration() if league_obj else 90
                else:
                    duration = league_obj.get_game_duration() if league_obj else 120
                all_activities_by_field_date[(field, game_date.date())].append((game_date, duration))

        # Check each time slot for unnecessary sharing
        violations_found = []
        for (pdate, hour, minute), slot_practices in practices_by_datetime.items():
            # Get fields being used at this specific time slot
            fields_used_now = set(p['field_id'] for p in slot_practices)

            # Check if any field has multiple teams (sharing)
            field_counts = defaultdict(int)
            field_teams = defaultdict(list)  # field_id -> list of team_ids
            for p in slot_practices:
                field_counts[p['field_id']] += 1
                # Get team ID from practice
                practice_obj = p['practice']
                team_id = None
                if hasattr(practice_obj, 'home_team') and practice_obj.home_team:
                    team_id = practice_obj.home_team.team_ID if hasattr(practice_obj.home_team, 'team_ID') else None
                elif hasattr(practice_obj, 'home_ID'):
                    team_id = practice_obj.home_ID
                if team_id:
                    field_teams[p['field_id']].append(team_id)

            shared_fields = [f for f, count in field_counts.items() if count > 1]
            if not shared_fields:
                continue  # No sharing at this time slot

            # Filter out paired teams from shared_fields (intentional sharing)
            # If all teams sharing a field are paired together, it's not a violation
            non_paired_shared_fields = []
            for field_id in shared_fields:
                teams_on_field = field_teams[field_id]
                # Check if all pairs of teams on this field are in paired relationships
                all_paired = True
                if len(teams_on_field) == 2:
                    if (teams_on_field[0], teams_on_field[1]) not in self._paired_team_pairs:
                        all_paired = False
                else:
                    # More than 2 teams - check all combinations
                    for i in range(len(teams_on_field)):
                        for j in range(i + 1, len(teams_on_field)):
                            if (teams_on_field[i], teams_on_field[j]) not in self._paired_team_pairs:
                                all_paired = False
                                break
                        if not all_paired:
                            break
                if not all_paired:
                    non_paired_shared_fields.append(field_id)

            shared_fields = non_paired_shared_fields
            if not shared_fields:
                continue  # All sharing is intentional via pairings

            # Get fields that have slots at this DAY OF WEEK and TIME across any date
            # Only consider fields that have practices on the SAME day of week at the same time
            # This matches the assignment logic which uses day-of-week specific slots
            day_of_week = pdate.weekday()
            fields_available_at_this_time = fields_by_dow_time_slot.get((day_of_week, hour, minute), set())

            # Potentially empty = fields that have this time slot but aren't being used now
            potentially_empty = fields_available_at_this_time - fields_used_now

            if not potentially_empty:
                continue  # No alternative fields have slots at this time

            # Check if these fields are TRULY empty considering practice duration
            start_dt = datetime.combine(pdate, time(hour, minute))
            end_dt = start_dt + timedelta(minutes=practice_duration)

            actually_empty = []
            for field_id in potentially_empty:
                # First check if field is available on this specific date (start date, blackouts)
                if not self._is_field_available_on_date(field_id, pdate):
                    continue  # Field not available on this date

                is_empty = True
                # Check if this field has any activity that overlaps with our time window
                for existing_start, existing_duration in all_activities_by_field_date.get((field_id, pdate), []):
                    existing_end = existing_start + timedelta(minutes=existing_duration)
                    if start_dt < existing_end and end_dt > existing_start:
                        is_empty = False
                        break
                if is_empty:
                    actually_empty.append(field_id)

            if actually_empty:
                # Sharing occurred when other fields were truly empty - violation!
                for shared_field in shared_fields:
                    shared_count = field_counts[shared_field]
                    field_obj = self._fields_cache.get(shared_field)
                    field_name = field_obj.location_title if field_obj else f'Field {shared_field}'

                    violations_found.append({
                        'date': pdate,
                        'time': f'{hour:02d}:{minute:02d}',
                        'field': field_name,
                        'teams_sharing': shared_count,
                        'empty_fields': len(actually_empty)
                    })

        if violations_found:
            # Group violations for cleaner message
            total_violations = len(violations_found)
            sample = violations_found[:3]
            sample_msgs = [f"{v['field']} on {v['date']} at {v['time']} ({v['teams_sharing']} teams sharing, {v['empty_fields']} empty fields available)"
                          for v in sample]

            msg = f'{league}: {total_violations} practice slot(s) with unnecessary sharing. '
            msg += '; '.join(sample_msgs)
            if total_violations > 3:
                msg += f' ... and {total_violations - 3} more'

            self.violations.append(ScheduleViolation(
                'f2', 'Unnecessary field sharing',
                ScheduleViolation.SOFT,
                msg
            ))

    def _check_same_team_gap(self, league, games, teams):
        """Check that same teams don't play back-to-back.

        Exception: With 2 teams, there's only 1 possible pair, so back-to-back
        is unavoidable and not flagged.
        """
        # Skip 2-team leagues - only 1 pair possible, back-to-back unavoidable
        if len(teams) <= 2:
            return

        # Sort games by date
        dated_games = [(g, self._get_game_date(g)) for g in games if self._get_game_date(g)]
        dated_games.sort(key=lambda x: x[1])

        # Track last game index for each matchup
        last_matchup = {}

        for i, (game, game_date) in enumerate(dated_games):
            home = self._get_home_team(game)
            away = self._get_away_team(game)
            if home and away:
                key = tuple(sorted([home, away]))
                if key in last_matchup:
                    last_idx = last_matchup[key]
                    # Check if this is the very next game for either team
                    # This is a simplified check - ideally we'd check game-by-game per team
                    if i - last_idx == 1:
                        home_name = self._get_team_name(home)
                        away_name = self._get_team_name(away)
                        self.violations.append(ScheduleViolation(
                            'gap', 'Same team gap',
                            ScheduleViolation.SOFT,
                            f'{league}: {home_name} vs {away_name} play back-to-back without a game gap',
                            teams=[self._build_team_info(home), self._build_team_info(away)]
                        ))
                last_matchup[key] = i

    def _get_activity_duration(self, game):
        """Get the duration in minutes for an activity based on its type and league."""
        league_name = game.league if hasattr(game, 'league') else None
        league_obj = self._league_cache.get(league_name) if league_name else None

        if self._is_practice(game):
            return league_obj.get_practice_duration() if league_obj else PRACTICE_DURATION_MINUTES
        else:
            # Check for no_time_limit games
            is_no_limit = getattr(game, 'no_time_limit', False) or (
                hasattr(game, 'no_time_limit') and game.no_time_limit == 1
            )
            return league_obj.get_game_duration(is_no_time_limit=is_no_limit) if league_obj else GAME_DURATION_MINUTES

    def _check_field_conflicts(self, games):
        """Check for games/practices that overlap on the same field.

        Rule slot: Each field can only have one game/scrimmage at a time.
        - No two games can overlap at the same field (even if start times differ)
        - No game and practice can overlap at the same field
        - Activities are considered to overlap if one starts before another ends

        Duration-based checking:
        - Games: default 120 min (2 hrs), configurable per league
        - Practices: default 90 min, configurable per league
        - No-time-limit games: 180 min (3 hrs)

        Example: A 5:30pm game (2hr) ends at 7:30pm, so a 7:00pm activity would overlap.

        Note: Multiple practices CAN share a slot (up to practice_capacity) - handled by rule f1.
        """
        # Build list of activities with start/end times
        activities = []  # List of (game, field, field_name, date, start_dt, end_dt, is_practice)

        for game in games:
            game_date = self._get_game_date(game)
            if not game_date:
                continue

            # Get field
            field = None
            field_name = None
            if hasattr(game, 'field') and game.field:
                field = game.field.ID if hasattr(game.field, 'ID') else game.field
                field_name = game.field.location_title if hasattr(game.field, 'location_title') else str(field)
            elif hasattr(game, 'location'):
                field = game.location
                field_name = str(field)

            if not field:
                continue

            # Calculate end time based on duration
            duration = self._get_activity_duration(game)
            end_dt = game_date + timedelta(minutes=duration)
            is_practice = self._is_practice(game)

            activities.append((game, field, field_name, game_date.date(), game_date, end_dt, is_practice))

        # Group by field and date
        by_field_date = defaultdict(list)
        for activity in activities:
            game, field, field_name, act_date, start_dt, end_dt, is_practice = activity
            key = (field, field_name, act_date)
            by_field_date[key].append(activity)

        # Check for overlaps within each field/date group
        for (field, field_name, act_date), field_activities in by_field_date.items():
            if len(field_activities) < 2:
                continue

            # Sort by start time
            field_activities.sort(key=lambda x: x[4])  # Sort by start_dt

            # Check each pair for overlaps
            for i in range(len(field_activities)):
                for j in range(i + 1, len(field_activities)):
                    game1, _, _, _, start1, end1, is_practice1 = field_activities[i]
                    game2, _, _, _, start2, end2, is_practice2 = field_activities[j]

                    # Check if activities overlap (activity2 starts before activity1 ends)
                    if start2 < end1:
                        # Both practices at same time are OK (handled by f1 rule for capacity)
                        if is_practice1 and is_practice2:
                            continue

                        # Calculate overlap duration for message
                        overlap_end = min(end1, end2)
                        overlap_minutes = int((overlap_end - start2).total_seconds() / 60)

                        # Determine activity types for message
                        if is_practice1 and not is_practice2:
                            conflict_type = 'practice and game'
                        elif not is_practice1 and is_practice2:
                            conflict_type = 'game and practice'
                        else:
                            conflict_type = '2 games'

                        time1_str = start1.strftime('%H:%M')
                        time2_str = start2.strftime('%H:%M')
                        end1_str = end1.strftime('%H:%M')

                        self.violations.append(ScheduleViolation(
                            'slot', 'Field double-booked (duration overlap)',
                            ScheduleViolation.HARD,
                            f'{field_name} on {act_date}: {conflict_type} overlap - '
                            f'activity at {time1_str} ends at {end1_str}, but another starts at {time2_str} '
                            f'({overlap_minutes} min overlap)',
                            games=[game1, game2]
                        ))

    def _check_practice_field_capacity(self, games):
        """Check practice field capacity limits and same-league sharing.

        Rule f1: Practice field capacity - enforces each field's practice_capacity
        setting from the database. If not set, defaults to 1.

        Rule f1c: Same-league sharing - teams can only share a practice field/time
        if they are in the same league.
        """
        # Group practices by (field_object, date, hour, minute)
        practices_by_slot = defaultdict(list)

        for game in games:
            # Only check practices
            if not self._is_practice(game):
                continue

            game_date = self._get_game_date(game)
            if not game_date:
                continue

            # Get field object (need full object for capacity check)
            field_obj = None
            field_id = None
            field_name = None
            if hasattr(game, 'field') and game.field:
                field_obj = game.field
                field_id = game.field.ID if hasattr(game.field, 'ID') else game.field
                field_name = game.field.location_title if hasattr(game.field, 'location_title') else str(field_id)
            elif hasattr(game, 'location'):
                field_id = game.location
                field_name = str(field_id)

            if not field_id:
                continue

            # Key includes field object for capacity lookup
            key = (field_id, field_name, field_obj, game_date.date(), game_date.hour, game_date.minute)
            practices_by_slot[key].append(game)

        # Check for capacity violations and cross-league sharing
        for key, practices_at_slot in practices_by_slot.items():
            field_id, field_name, field_obj, date, hour, minute = key
            time_str = f'{hour:02d}:{minute:02d}'

            # Get field's practice_capacity from DB (defaults to 1 if not set)
            if field_obj and hasattr(field_obj, 'get_practice_capacity'):
                is_late = hour >= 19
                field_capacity = field_obj.get_practice_capacity(is_late_slot=is_late)
            else:
                field_capacity = 1  # Default if no field object

            # Check capacity violation (f1)
            if len(practices_at_slot) > field_capacity:
                # Get team names for the violation message
                team_names = []
                for p in practices_at_slot:
                    home = self._get_home_team(p)
                    if home:
                        team_names.append(self._get_team_name(home))

                self.violations.append(ScheduleViolation(
                    'f1', 'Practice field capacity',
                    ScheduleViolation.HARD,
                    f'{field_name} has {len(practices_at_slot)} teams practicing at {date} {time_str} (field capacity: {field_capacity}). Teams: {", ".join(team_names[:5])}{"..." if len(team_names) > 5 else ""}',
                    games=practices_at_slot
                ))

            # Check cross-league sharing violation (f1c) - only if more than 1 team sharing
            if len(practices_at_slot) > 1:
                leagues_in_slot = set()
                team_ids_in_slot = []
                for p in practices_at_slot:
                    league = self._get_league(p)
                    if league:
                        leagues_in_slot.add(league)
                    home = self._get_home_team(p)
                    if home:
                        team_ids_in_slot.append(home)

                if len(leagues_in_slot) > 1:
                    # Multiple leagues sharing same practice slot - check if exempt via pairing
                    # If exactly 2 teams and they are paired, this is intentional sharing
                    is_paired_sharing = False
                    if len(team_ids_in_slot) == 2:
                        pair = (team_ids_in_slot[0], team_ids_in_slot[1])
                        if pair in self._paired_team_pairs:
                            is_paired_sharing = True

                    if not is_paired_sharing:
                        # Violation - multiple leagues sharing without a pairing
                        team_league_info = []
                        for p in practices_at_slot:
                            home = self._get_home_team(p)
                            league = self._get_league(p)
                            if home:
                                team_name = self._get_team_name(home)
                                team_league_info.append(f'{team_name} ({league})')

                        self.violations.append(ScheduleViolation(
                            'f1c', 'Cross-league practice sharing',
                            ScheduleViolation.HARD,
                            f'{field_name} at {date} {time_str} has teams from different leagues sharing practice: {", ".join(team_league_info[:5])}{"..." if len(team_league_info) > 5 else ""}',
                            games=practices_at_slot
                        ))

    def _check_season_blackouts(self, games):
        """Rule h1: No games or practices on season blackout dates.

        Season blackouts are dates when no activities should be scheduled
        (e.g., Labor Day weekend, holidays).
        """
        from app.models.season_blackout import SeasonBlackout

        # Get blackout dates for this season
        blackout_dates = SeasonBlackout.get_blackout_dates_set(self.year, self.is_spring)

        if not blackout_dates:
            return

        violations_by_date = defaultdict(list)

        for game in games:
            game_date = self._get_game_date(game)
            if not game_date:
                continue

            check_date = game_date.date() if hasattr(game_date, 'date') else game_date
            if check_date in blackout_dates:
                violations_by_date[check_date].append(game)

        # Report violations grouped by date
        for date, games_on_date in violations_by_date.items():
            game_count = len([g for g in games_on_date if self._is_actual_game(g)])
            practice_count = len([g for g in games_on_date if self._is_practice(g)])

            activities = []
            if game_count > 0:
                activities.append(f'{game_count} game(s)')
            if practice_count > 0:
                activities.append(f'{practice_count} practice(s)')

            self.violations.append(ScheduleViolation(
                'h1', 'Season blackout violation',
                ScheduleViolation.HARD,
                f'{date}: {" and ".join(activities)} scheduled on blackout date',
                games=games_on_date
            ))

    def _check_field_availability(self, games):
        """Rule h2: No games or practices at unavailable fields.

        Checks:
        1. Field start_date - no activities before field is available
        2. Field blackout dates - no activities on field-specific blackout dates
        """
        from app.models.field import Field
        from app.models.field_blackout import FieldBlackout

        # Cache field info to avoid repeated queries
        field_cache = {}
        field_blackouts_cache = {}

        violations = []

        for game in games:
            game_date = self._get_game_date(game)
            if not game_date:
                continue

            check_date = game_date.date() if hasattr(game_date, 'date') else game_date

            # Get field info
            field_id = None
            field_name = None
            if hasattr(game, 'field') and game.field:
                field_id = game.field.ID if hasattr(game.field, 'ID') else None
                field_name = game.field.location_title if hasattr(game.field, 'location_title') else str(field_id)
            elif hasattr(game, 'location'):
                field_id = game.location
                field_name = str(field_id)

            if not field_id:
                continue

            # Get field from pre-loaded cache or local cache
            if field_id not in field_cache:
                field = self._fields_cache.get(field_id)
                if not field:
                    # Fallback to DB query if not in pre-loaded cache
                    field = Field.query.get(field_id)
                field_cache[field_id] = {
                    'start_date': field.start_date if field else None,
                    'name': field.location_title if field else str(field_id)
                }

            field_info = field_cache[field_id]
            field_name = field_info['name']

            # Check start_date violation
            if field_info['start_date'] and check_date < field_info['start_date']:
                game_type = 'practice' if self._is_practice(game) else 'game'
                violations.append({
                    'type': 'start_date',
                    'field_id': field_id,
                    'field_name': field_name,
                    'date': check_date,
                    'game': game,
                    'game_type': game_type,
                    'start_date': field_info['start_date']
                })
                continue

            # Get field blackouts from pre-loaded cache or local cache
            if field_id not in field_blackouts_cache:
                if field_id in self._field_blackouts_cache:
                    # Use pre-loaded cache (already a list of dates)
                    field_blackouts_cache[field_id] = set(self._field_blackouts_cache[field_id])
                else:
                    # Fallback to DB query
                    blackouts = FieldBlackout.query.filter_by(
                        field_ID=field_id, active=1
                    ).all()
                    field_blackouts_cache[field_id] = {b.blackout_date for b in blackouts}

            # Check field blackout violation
            if check_date in field_blackouts_cache[field_id]:
                game_type = 'practice' if self._is_practice(game) else 'game'
                violations.append({
                    'type': 'blackout',
                    'field_id': field_id,
                    'field_name': field_name,
                    'date': check_date,
                    'game': game,
                    'game_type': game_type
                })

        # Group violations by field and type for cleaner reporting
        start_date_violations = [v for v in violations if v['type'] == 'start_date']
        blackout_violations = [v for v in violations if v['type'] == 'blackout']

        # Report start_date violations grouped by field
        fields_with_start_violations = defaultdict(list)
        for v in start_date_violations:
            fields_with_start_violations[v['field_id']].append(v)

        for field_id, field_violations in fields_with_start_violations.items():
            field_name = field_violations[0]['field_name']
            start_date = field_violations[0]['start_date']
            game_count = len([v for v in field_violations if v['game_type'] != 'practice'])
            practice_count = len([v for v in field_violations if v['game_type'] == 'practice'])

            activities = []
            if game_count > 0:
                activities.append(f'{game_count} game(s)')
            if practice_count > 0:
                activities.append(f'{practice_count} practice(s)')

            affected_games = [v['game'] for v in field_violations]
            self.violations.append(ScheduleViolation(
                'h2', 'Field not yet available',
                ScheduleViolation.HARD,
                f'{field_name}: {" and ".join(activities)} scheduled before field start date ({start_date})',
                games=affected_games
            ))

        # Report blackout violations grouped by field and date
        for v in blackout_violations:
            self.violations.append(ScheduleViolation(
                'h2', 'Field blackout violation',
                ScheduleViolation.HARD,
                f'{v["field_name"]}: {v["game_type"]} scheduled on {v["date"]} (field blackout date)',
                games=[v['game']]
            ))

    def _check_one_activity_per_day(self, league, games, teams):
        """Rule d1: Each team can have at most one game or practice per day."""
        # Group activities by (team, date)
        team_day_activities = defaultdict(list)

        for g in games:
            game_date = self._get_game_date(g)
            if not game_date:
                continue

            date_str = game_date.date().isoformat() if hasattr(game_date, 'date') else str(game_date)[:10]

            home = self._get_home_team(g)
            away = self._get_away_team(g)

            if home:
                team_day_activities[(home, date_str)].append(g)
            if away:
                team_day_activities[(away, date_str)].append(g)

        # Check for violations
        for (team_id, date_str), activities in team_day_activities.items():
            if len(activities) > 1:
                team_name = self._get_team_name(team_id)
                activity_types = []
                for a in activities:
                    if self._is_practice(a):
                        activity_types.append('practice')
                    elif hasattr(a, 'is_scrimmage') and a.is_scrimmage:
                        activity_types.append('scrimmage')
                    else:
                        activity_types.append('game')

                self.violations.append(ScheduleViolation(
                    'd1', 'One activity per day',
                    ScheduleViolation.HARD,
                    f'{league}: Team {team_name} has {len(activities)} activities on {date_str} ({", ".join(activity_types)})',
                    games=activities,
                    teams=[self._build_team_info(team_id)]
                ))

    def _check_minimum_games(self, league, games, teams):
        """Rule e1: All teams must play the minimum required games (HARD).

        Each team must have at least the configured number of regular season games.
        """
        # Get minimum games from league config
        config = self._league_configs.get(league)
        min_games = config.regular_season_games if config else 10

        # Count games per team
        game_counts = defaultdict(int)
        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home:
                game_counts[home] += 1
            if away:
                game_counts[away] += 1

        # Check each team
        for team_id in teams:
            count = game_counts.get(team_id, 0)
            if count < min_games:
                team_name = self._get_team_name(team_id)
                self.violations.append(ScheduleViolation(
                    'e1', 'Minimum games',
                    ScheduleViolation.HARD,
                    f'{league}: Team {team_name} has only {count} games (minimum: {min_games})',
                    teams=[self._build_team_info(team_id)]
                ))

    def _check_game_day_balance(self, league, games, teams):
        """Rule e2: All teams should play on the same game days (SOFT).

        When games are scheduled on a particular date, all teams in the league
        should be playing on that date. No team should sit out while others play.

        Exception: With odd team counts, exactly 1 team sitting out is expected and
        is not flagged as a violation.
        """
        n_teams = len(teams)
        expected_sit_outs = 1 if n_teams % 2 == 1 else 0

        # Group games by date
        games_by_date = defaultdict(list)
        for g in games:
            game_date = self._get_game_date(g)
            if game_date:
                date_str = game_date.date().isoformat() if hasattr(game_date, 'date') else str(game_date)[:10]
                games_by_date[date_str].append(g)

        # For each game date, check which teams are playing
        for date_str, date_games in games_by_date.items():
            teams_playing = set()
            for g in date_games:
                home = self._get_home_team(g)
                away = self._get_away_team(g)
                if home:
                    teams_playing.add(home)
                if away:
                    teams_playing.add(away)

            # Check for teams not playing
            teams_sitting = set(teams) - teams_playing
            # Only flag if MORE teams are sitting than expected (due to odd count)
            # and some teams ARE playing (not an empty date)
            if len(teams_sitting) > expected_sit_outs and teams_playing:
                sitting_names = [self._get_team_name(t) for t in teams_sitting]
                self.violations.append(ScheduleViolation(
                    'e2', 'Game day balance',
                    ScheduleViolation.SOFT,
                    f'{league}: On {date_str}, {len(teams_sitting)} team(s) not playing: {", ".join(sitting_names)}',
                    teams=[self._build_team_info(t) for t in teams_sitting]
                ))

    def _check_day_of_week_game_balance(self, league, games, teams):
        """Rule f1: Day-of-week game balance for P/G leagues.

        For leagues with P/G days (days that can have either practices or games),
        ensure no team has significantly more games on a given day of week than others.

        - Soft violation (f1a): If any two teams differ by 2+ games on a day of week
        - Hard violation (f1b): If any two teams differ by 3+ games on a day of week
        """
        # Get league config to check for P/G days
        config = self._league_configs.get(league)
        if not config:
            return

        # Only apply this rule to leagues with P/G days
        if not config.has_pg_days:
            return

        pg_days = config.both_days  # Days that are P/G

        # Count games per team per day of week (only for P/G days)
        # day_of_week -> team_id -> game_count
        games_per_team_per_dow = defaultdict(lambda: defaultdict(int))

        for g in games:
            game_date = self._get_game_date(g)
            if not game_date:
                continue

            dow = game_date.weekday()
            if dow not in pg_days:
                continue  # Only check P/G days

            home = self._get_home_team(g)
            away = self._get_away_team(g)

            if home:
                games_per_team_per_dow[dow][home] += 1
            if away:
                games_per_team_per_dow[dow][away] += 1

        # Check each P/G day for imbalance
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for dow in pg_days:
            team_counts = games_per_team_per_dow[dow]

            if not team_counts:
                continue

            # Include teams with 0 games on this day
            for team_id in teams:
                if team_id not in team_counts:
                    team_counts[team_id] = 0

            counts = list(team_counts.values())
            if not counts:
                continue

            min_count = min(counts)
            max_count = max(counts)
            diff = max_count - min_count

            if diff >= 2:
                # Find the teams with max and min games
                max_teams = [t for t, c in team_counts.items() if c == max_count]
                min_teams = [t for t, c in team_counts.items() if c == min_count]

                max_names = [self._get_team_name(t) for t in max_teams]
                min_names = [self._get_team_name(t) for t in min_teams]

                day_name = day_names[dow]

                if diff >= 3:
                    # Hard violation
                    self.violations.append(ScheduleViolation(
                        'f1b', 'Day-of-week game balance (hard)',
                        ScheduleViolation.HARD,
                        f'{league}: {day_name} game imbalance of {diff}. '
                        f'{", ".join(max_names)} have {max_count} games, '
                        f'{", ".join(min_names)} have {min_count} games.',
                        teams=[self._build_team_info(t) for t in max_teams + min_teams]
                    ))
                else:
                    # Soft violation (diff == 2)
                    self.violations.append(ScheduleViolation(
                        'f1a', 'Day-of-week game balance (soft)',
                        ScheduleViolation.SOFT,
                        f'{league}: {day_name} game imbalance of {diff}. '
                        f'{", ".join(max_names)} have {max_count} games, '
                        f'{", ".join(min_names)} have {min_count} games.',
                        teams=[self._build_team_info(t) for t in max_teams + min_teams]
                    ))

    def _check_time_restrictions(self, league, games):
        """Rule g1: Time restrictions (HARD).

        No games or practices can start after league's latest_start_time
        or before league's earliest_start_time.

        Default behavior: If no latest_start_time is set for a league,
        all activities must start by 7:30pm (19:30).
        """
        from datetime import time as dt_time
        from app.models.league import League

        # Default latest start time if none is set
        DEFAULT_LATEST_START = dt_time(19, 30)  # 7:30pm

        # Get the league config to find time restrictions
        league_obj = League.get_by_name(league)
        if not league_obj:
            return

        earliest = league_obj.earliest_start_time
        latest = league_obj.latest_start_time

        # Apply default latest_start_time if not explicitly set
        if not latest:
            latest = DEFAULT_LATEST_START

        violations = []
        for g in games:
            game_date = self._get_game_date(g)
            if not game_date:
                continue

            game_time = game_date.time()
            team = self._get_home_team(g)
            game_type = g.game_type if hasattr(g, 'game_type') else 'game'

            if earliest and game_time < earliest:
                violations.append({
                    'team': team,
                    'type': game_type,
                    'time': game_time,
                    'issue': f'before earliest ({earliest.strftime("%H:%M")})'
                })
            elif latest and game_time > latest:
                violations.append({
                    'team': team,
                    'type': game_type,
                    'time': game_time,
                    'issue': f'after latest ({latest.strftime("%H:%M")})'
                })

        if violations:
            # Group by type
            game_violations = [v for v in violations if v['type'] != 'practice']
            practice_violations = [v for v in violations if v['type'] == 'practice']

            if game_violations:
                affected_teams = list(set(v['team'] for v in game_violations if v['team']))
                self.violations.append(ScheduleViolation(
                    'g1', 'Time restriction violation',
                    ScheduleViolation.HARD,
                    f'{league}: {len(game_violations)} game(s) scheduled outside allowed times '
                    f'(earliest: {earliest.strftime("%H:%M") if earliest else "any"}, '
                    f'latest: {latest.strftime("%H:%M") if latest else "any"})',
                    teams=[self._build_team_info(t) for t in affected_teams]
                ))

            if practice_violations:
                affected_teams = list(set(v['team'] for v in practice_violations if v['team']))
                self.violations.append(ScheduleViolation(
                    'g1', 'Time restriction violation',
                    ScheduleViolation.HARD,
                    f'{league}: {len(practice_violations)} practice(s) scheduled outside allowed times '
                    f'(earliest: {earliest.strftime("%H:%M") if earliest else "any"}, '
                    f'latest: {latest.strftime("%H:%M") if latest else "any"})',
                    teams=[self._build_team_info(t) for t in affected_teams]
                ))


class SlotDecision:
    """Records a single slot assignment decision for tracing."""

    def __init__(self, date_str, league, slot, decision, reason, game_info=None):
        self.date_str = date_str  # YYYY-MM-DD
        self.league = league
        self.slot_id = slot.slot_ID if slot else None
        self.field_name = slot.field.location_title if slot and slot.field else 'Unknown'
        self.start_time = slot.start_time.strftime('%I:%M %p') if slot and slot.start_time else 'Unknown'
        self.decision = decision  # 'assigned', 'skipped', 'rejected'
        self.reason = reason  # Why this decision was made
        self.game_info = game_info  # Details about what was assigned (if any)

    def to_dict(self):
        return {
            'date': self.date_str,
            'league': self.league,
            'slot_id': self.slot_id,
            'field': self.field_name,
            'time': self.start_time,
            'decision': self.decision,
            'reason': self.reason,
            'game_info': self.game_info
        }


class ScheduleGenerator:
    """Generates proposed schedules for a season.

    Three-phase workflow:
    - Phase 1 (Setup): Empty game slots created via Game.generate_game_slots()
    - Phase 2 (Draft): This class fills in matchups + dates + fields
    - Phase 3 (Locked): Schedule accepted, manual edits only
    """

    def __init__(self, year, is_spring):
        self.year = year
        self.is_spring = is_spring
        self.proposed_games = []
        self.violations = []
        self.warnings = []
        self._next_id = 1
        self._slot_assignments = {}  # Maps game_id to proposed assignment
        # Track field usage with time ranges for duration-based overlap detection
        # Key: (field_id, date_str) -> list of {'start': datetime, 'end': datetime, 'league': str, 'is_practice': bool}
        self._global_field_time_ranges = defaultdict(list)
        self._team_day_usage = set()  # Tracks (team_id, date_str) - one activity per team per day
        self._slot_decisions = []  # Detailed decision log for tracing
        self._practice_slot_counts = defaultdict(int)  # Tracks practice count per (field_id, datetime) - f1 rule
        self._practice_slot_leagues = {}  # Tracks which league is using each (field_id, datetime) - same-league sharing only
        self._team_practice_counts = defaultdict(int)  # Tracks total practice count per team for balance
        self._league_cache = {}  # Cache: league_name -> League object (avoids repeated DB queries)

        # Batch-loaded caches (populated in generate() to minimize DB round-trips)
        self._all_field_slots = None  # All FieldSlot objects for season
        self._teams_by_league = {}  # league_name -> list of TeamSeason
        self._games_by_league = {}  # league_name -> list of Game
        self._fields_cache = {}  # field_id -> Field object
        self._field_blackouts_cache = {}  # field_id -> list of blackout dates

        # Load season-wide blackout dates
        from app.models.season_blackout import SeasonBlackout
        self._season_blackout_dates = SeasonBlackout.get_blackout_dates_set(year, is_spring)

        # Load practice pairings (teams that always share on specific days)
        from app.models.practice_pairing import PracticePairing
        self._practice_pairings = PracticePairing.get_by_season(year, is_spring)
        self._paired_team_ids = PracticePairing.get_paired_team_ids(year, is_spring)
        self._paired_team_pairs = PracticePairing.get_pairing_pairs(year, is_spring)
        # Track which teams have been assigned paired practices for each date
        self._paired_practice_assigned = set()  # (team_id, date_str)

    def _is_blackout_date(self, check_date):
        """Check if a date is a season-wide blackout date."""
        # Convert datetime to date if needed
        if hasattr(check_date, 'date'):
            check_date = check_date.date()
        return check_date in self._season_blackout_dates

    def _is_field_available_on_date(self, field_id, check_date):
        """Check if field is available on date using cached data (no DB queries).

        Returns False if:
        - Field has start_date and check_date is before it
        - Field has a blackout for that date
        """
        # Convert datetime to date if needed
        if hasattr(check_date, 'date'):
            check_date = check_date.date()

        # Get field from cache
        field = self._fields_cache.get(field_id)
        if not field:
            return False

        # Check start date
        if field.start_date and check_date < field.start_date:
            return False

        # Check field-specific blackouts from cache
        blackout_dates = self._field_blackouts_cache.get(field_id, [])
        if check_date in blackout_dates:
            return False

        return True

    def _get_activity_duration_minutes(self, league, is_practice=False, is_no_time_limit=False):
        """Get the duration in minutes for an activity based on league settings."""
        # Use cached league object to avoid repeated DB queries
        if isinstance(league, str):
            league_obj = self._league_cache.get(league)
            if not league_obj:
                # Fallback to DB query if not in cache (shouldn't happen normally)
                league_obj = League.get_by_name(league)
        else:
            league_obj = league
        if is_practice:
            return league_obj.get_practice_duration() if league_obj else PRACTICE_DURATION_MINUTES
        return league_obj.get_game_duration(is_no_time_limit=is_no_time_limit) if league_obj else GAME_DURATION_MINUTES

    def _check_field_time_available(self, field_id, start_dt, duration_minutes, league, is_practice=False):
        """Check if a field/time slot is available considering activity duration.

        Returns True if the slot is available (no overlaps with existing activities).
        Returns False if the slot would overlap with an existing game or
        non-same-league activity.

        Practices can share with other practices from the same league
        (capacity is checked separately via f1 rule).

        Optimization: List is kept sorted by start time, so we use binary search
        to find only entries that could potentially overlap.
        """
        if not field_id or not start_dt:
            return True  # Can't check without field/time

        date_str = start_dt.date().isoformat() if hasattr(start_dt, 'date') else str(start_dt)[:10]
        key = (field_id, date_str)
        entries = self._global_field_time_ranges[key]

        if not entries:
            return True

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Binary search to find first entry that starts at or after end_dt
        # We only need to check entries with start < end_dt (those that start before we end)
        lo, hi = 0, len(entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if entries[mid]['start'] < end_dt:
                lo = mid + 1
            else:
                hi = mid
        # Now check entries 0..lo-1 (those that start before we end)

        for i in range(lo):
            existing = entries[i]
            existing_start = existing['start']
            existing_end = existing['end']

            # Check for time overlap: we start before they end AND we end after they start
            if start_dt < existing_end and end_dt > existing_start:
                # There's an overlap - check if it's allowed
                existing_is_practice = existing.get('is_practice', False)
                existing_league = existing.get('league')

                # Two practices from the same league can share (capacity checked elsewhere)
                if is_practice and existing_is_practice and league == existing_league:
                    continue  # Same-league practice sharing is allowed

                # Any other overlap (game+practice, game+game, cross-league practice) is not allowed
                return False

        return True

    def _add_field_time_usage(self, field_id, start_dt, duration_minutes, league, is_practice=False):
        """Record that a field is being used for an activity during a time range.

        Maintains the list sorted by start time for efficient overlap checking.
        """
        if not field_id or not start_dt:
            return

        date_str = start_dt.date().isoformat() if hasattr(start_dt, 'date') else str(start_dt)[:10]
        key = (field_id, date_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        entry = {
            'start': start_dt,
            'end': end_dt,
            'league': league,
            'is_practice': is_practice
        }

        # Insert in sorted order by start time using binary search
        entries = self._global_field_time_ranges[key]
        lo, hi = 0, len(entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if entries[mid]['start'] < start_dt:
                lo = mid + 1
            else:
                hi = mid
        entries.insert(lo, entry)

    def generate(self, start_fresh=False):
        """Generate a complete proposed schedule.

        This fills in existing game slots with matchups, dates, and fields.
        Does NOT create new game records - those should exist already.

        Args:
            start_fresh: If True, treats all slots as unassigned (ignores existing assignments)

        Returns:
            dict with 'games', 'violations', 'warnings', 'assignments'
        """
        import time as time_module

        gen_start = time_module.time()
        print(f"[SCHEDULER] Starting generation for {self.year}/{self.is_spring}", flush=True)

        self.proposed_games = []
        self.violations = []
        self.warnings = []
        self._slot_assignments = {}
        # Global tracker for field/time usage across all leagues with duration support
        # Key: (field_id, date_str) -> list of {'start': datetime, 'end': datetime, 'league': str, 'is_practice': bool}
        self._global_field_time_ranges = defaultdict(list)
        # Global tracker for team-day usage (one game/practice per team per day)
        # Key: (team_id, date_str) - prevents multiple activities on same day
        self._team_day_usage = set()
        # Weekly activity trackers for P/G leagues (2 games + 1 practice per week)
        # Key: (team_id, week_num) -> count
        self._team_week_practices = defaultdict(int)
        self._team_week_games = defaultdict(int)

        # Validate prerequisites
        t0 = time_module.time()
        if not self._validate_prerequisites():
            return self._build_result()
        print(f"[SCHEDULER] Prerequisites validated in {time_module.time() - t0:.2f}s", flush=True)

        # Get league configurations
        t0 = time_module.time()
        league_configs = LeagueSeason.get_by_season(self.year, self.is_spring)
        print(f"[SCHEDULER] Got {len(league_configs)} league configs in {time_module.time() - t0:.2f}s", flush=True)

        # =================================================================
        # BATCH LOAD ALL DATA UPFRONT (minimizes DB round-trips)
        # =================================================================
        t0 = time_module.time()

        # Pre-load all leagues into cache
        all_leagues = League.query.filter_by(active=1).all()
        self._league_cache = {lg.display_name: lg for lg in all_leagues}

        # Pre-load ALL field slots for the season (single query instead of N per league)
        self._all_field_slots = FieldSlot.get_by_season(self.year, self.is_spring)

        # Pre-load ALL teams for the season, grouped by league
        all_teams = TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            active=1,
            is_placeholder=0
        ).all()
        self._teams_by_league = defaultdict(list)
        for team in all_teams:
            self._teams_by_league[team.league].append(team)

        # Pre-load ALL games for the season, grouped by league
        all_games = Game.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            active=1
        ).all()
        self._games_by_league = defaultdict(list)
        for game in all_games:
            self._games_by_league[game.league].append(game)

        # Pre-load ALL fields
        all_fields = Field.query.filter_by(active=1).all()
        self._fields_cache = {f.ID: f for f in all_fields}

        # Pre-load ALL field blackouts for fields we care about
        field_ids = [f.ID for f in all_fields]
        if field_ids:
            from app.models.field_blackout import FieldBlackout
            all_blackouts = FieldBlackout.query.filter(
                FieldBlackout.field_ID.in_(field_ids),
                FieldBlackout.active == 1
            ).all()
            self._field_blackouts_cache = defaultdict(list)
            for bo in all_blackouts:
                self._field_blackouts_cache[bo.field_ID].append(bo.blackout_date)

        print(f"[SCHEDULER] Batch loaded: {len(all_leagues)} leagues, {len(self._all_field_slots)} slots, {len(all_teams)} teams, {len(all_games)} games, {len(all_fields)} fields in {time_module.time() - t0:.2f}s", flush=True)
        # =================================================================

        # Sort leagues to prioritize those with FEWER game day options
        # This ensures Saturday-only leagues (like Tee Ball) get first dibs on Saturday slots
        # before leagues with multiple game days take them
        league_configs = sorted(league_configs, key=lambda c: (len(c.game_days), c.league))

        # Check for locked schedules
        locked_leagues = [c.league for c in league_configs if c.schedule_locked]
        if locked_leagues:
            self.warnings.append({
                'type': 'schedule_locked',
                'message': f'The following leagues have locked schedules and will be skipped: {", ".join(locked_leagues)}'
            })
            # Filter out locked leagues
            league_configs = [c for c in league_configs if not c.schedule_locked]

        # Two-phase scheduling: games first (priority), then practices
        # This ensures games get first dibs on all field slots across all leagues

        # Phase 1: Schedule all games for all leagues
        t0 = time_module.time()
        phase1_game_count = 0
        for config in league_configs:
            t1 = time_module.time()
            before = len(self.proposed_games)
            self._generate_games_only(config, start_fresh)
            after = len(self.proposed_games)
            games_added = after - before
            phase1_game_count += games_added
            print(f"[SCHEDULER] Phase1 {config.league}: +{games_added} games in {time_module.time() - t1:.2f}s", flush=True)
        print(f"[SCHEDULER] Phase 1 complete: {phase1_game_count} games in {time_module.time() - t0:.2f}s", flush=True)

        # Phase 2: Schedule all practices for all leagues using round-robin
        # This ensures fair slot allocation - each league gets one practice before any gets a second
        t0 = time_module.time()
        before_count = len(self.proposed_games)
        self._schedule_practices_round_robin(league_configs, start_fresh)
        phase2_practice_count = len(self.proposed_games) - before_count
        print(f"[SCHEDULER] Phase 2 complete: {phase2_practice_count} practices (round-robin) in {time_module.time() - t0:.2f}s", flush=True)

        # Debug: Report phase results
        total_time_ranges = sum(len(ranges) for ranges in self._global_field_time_ranges.values())
        self.warnings.append({
            'type': 'debug_phases',
            'message': f'Phase 1 (games/scrimmages): {phase1_game_count} scheduled. Phase 2 (practices): {phase2_practice_count} scheduled. Field time ranges used after Phase 1: {total_time_ranges}.'
        })

        # Debug: Show what's scheduled on a Thursday in October (for debugging BB A issue)
        from datetime import date
        debug_date = date(self.year, 10, 15)  # Oct 15th
        if debug_date.weekday() == 3:  # Thursday
            oct15_activities = []
            for g in self.proposed_games:
                if g.game_date:
                    g_date = g.game_date.date() if hasattr(g.game_date, 'date') else g.game_date
                    if g_date == debug_date:
                        oct15_activities.append(f'{g.league}:{g.game_type}')
            if oct15_activities:
                from collections import Counter
                counts = Counter(oct15_activities)
                summary = ', '.join(f'{k}({v})' for k, v in sorted(counts.items()))
                self.warnings.append({
                    'type': 'debug_oct15',
                    'message': f'Oct 15 activities: {summary}'
                })

        # Validate the generated schedule (pass pre-loaded caches to avoid DB queries)
        t0 = time_module.time()
        validator = ScheduleValidator(
            self.year, self.is_spring,
            fields_cache=self._fields_cache,
            field_blackouts_cache=self._field_blackouts_cache,
            league_cache=self._league_cache
        )
        self.violations = validator.validate(self.proposed_games)
        print(f"[SCHEDULER] Validation complete: {len(self.violations)} violations in {time_module.time() - t0:.2f}s", flush=True)

        print(f"[SCHEDULER] Total generation time: {time_module.time() - gen_start:.2f}s", flush=True)
        return self._build_result()

    def _validate_prerequisites(self):
        """Check that all prerequisites are in place."""
        # Check field slots exist
        slots = FieldSlot.get_by_season(self.year, self.is_spring)
        if not slots:
            self.warnings.append({
                'type': 'missing_slots',
                'message': 'No field slots found. Create field allocations first.'
            })
            return False

        # Check teams exist
        teams = TeamSeason.get_by_season(self.year, self.is_spring)
        if not teams:
            self.warnings.append({
                'type': 'missing_teams',
                'message': 'No teams found for this season.'
            })
            return False

        # Check league configs exist
        configs = LeagueSeason.get_by_season(self.year, self.is_spring)
        if not configs:
            self.warnings.append({
                'type': 'missing_configs',
                'message': 'No league configurations found. Set up schedule settings first.'
            })
            return False

        # Check schedule settings
        for config in configs:
            if not config.first_practice_date:
                self.warnings.append({
                    'type': 'missing_date',
                    'message': f'{config.league}: First practice date not set.'
                })
            if not config.opening_day_date:
                self.warnings.append({
                    'type': 'missing_date',
                    'message': f'{config.league}: Opening day not set.'
                })

        return len(self.warnings) == 0

    def _generate_games_only(self, config, start_fresh=False):
        """Generate games and scrimmages for a single league.

        This is called first for all leagues to ensure games get priority
        over practices when claiming field slots.
        """
        league_name = config.league

        # Get teams for this league (from cache)
        teams = self._teams_by_league.get(league_name, [])

        if len(teams) < 2:
            self.warnings.append({
                'type': 'insufficient_teams',
                'message': f'{league_name}: Need at least 2 teams to schedule.'
            })
            return

        # Get league object for field rules (from cache)
        league = self._league_cache.get(league_name)

        # Get available field slots (from cache)
        all_slots = self._all_field_slots

        # Get existing game slots for this league (from cache)
        existing_games = self._games_by_league.get(league_name, [])

        # Separate by type
        regular_slots = [g for g in existing_games if g.game_type == 'regular']

        # If start_fresh, treat all as unassigned
        if start_fresh:
            for game in existing_games:
                game._temp_clear = True

        # Generate scrimmages (last day before opening) - only if league has scrimmages
        if config.has_scrimmages and config.first_practice_date and config.opening_day_date:
            scrimmage_date = config.opening_day_date - timedelta(days=1)
            # Find last activity day before opening
            practice_days = config.practice_days or []
            game_days = config.game_days or []
            all_activity_days = set(practice_days + game_days)
            current = scrimmage_date
            while current >= config.first_practice_date:
                if current.weekday() in all_activity_days and not self._is_blackout_date(current):
                    self._generate_scrimmages(config, teams, league, all_slots, current)
                    break
                current -= timedelta(days=1)

        # Generate regular season games
        self._generate_games(config, teams, league, all_slots, regular_slots, start_fresh)

    def _generate_practices_only(self, config, start_fresh=False):
        """Generate practices for a single league.

        This is called after all games are scheduled to ensure practices
        work around the game schedule.
        """
        league_name = config.league

        # Get teams for this league (from cache)
        teams = self._teams_by_league.get(league_name, [])

        if len(teams) < 2:
            return  # Warning already issued in games phase

        # Get league object for field rules (from cache)
        league = self._league_cache.get(league_name)

        # Get available field slots (from cache)
        all_slots = self._all_field_slots

        # Get existing practice slots for this league (from cache)
        existing_games = self._games_by_league.get(league_name, [])
        practice_slots = [g for g in existing_games if g.game_type == 'practice']

        # If start_fresh, treat all as unassigned
        if start_fresh:
            for game in existing_games:
                game._temp_clear = True

        # Pre-opening practices (before opening day, excluding scrimmage day)
        if config.first_practice_date and config.opening_day_date:
            practice_days = config.practice_days or []
            game_days = config.game_days or []
            all_activity_days = set(practice_days + game_days)

            current_date = config.first_practice_date
            end_date = config.opening_day_date - timedelta(days=1)

            # Find scrimmage date (last activity day before opening) to skip it
            scrimmage_date = None
            check_date = end_date
            while check_date >= config.first_practice_date:
                if check_date.weekday() in all_activity_days:
                    scrimmage_date = check_date
                    break
                check_date -= timedelta(days=1)

            while current_date <= end_date:
                if current_date.weekday() in all_activity_days and current_date != scrimmage_date:
                    # Skip season blackout dates
                    if self._is_blackout_date(current_date):
                        current_date += timedelta(days=1)
                        continue
                    # Pre-opening: schedule practices on ALL activity days (game + practice)
                    self._assign_practices_for_date(config, teams, league, all_slots, current_date, practice_slots, start_fresh, is_pre_opening=True)
                current_date += timedelta(days=1)

        # Post-opening practices
        self._generate_post_opening_practices(config, teams, league, all_slots, practice_slots, start_fresh)

    def _generate_for_league(self, config, start_fresh=False):
        """Generate schedule for a single league.

        Args:
            config: LeagueSeason configuration
            start_fresh: If True, treats all slots as unassigned
        """
        league_name = config.league

        # Get teams for this league (from cache)
        teams = self._teams_by_league.get(league_name, [])

        if len(teams) < 2:
            self.warnings.append({
                'type': 'insufficient_teams',
                'message': f'{league_name}: Need at least 2 teams to schedule.'
            })
            return

        # Get league object for field rules (from cache)
        league = self._league_cache.get(league_name)

        # Get available field slots (from cache)
        all_slots = self._all_field_slots

        # Get existing game slots for this league (from cache)
        existing_games = self._games_by_league.get(league_name, [])

        # Separate by type
        regular_slots = [g for g in existing_games if g.game_type == 'regular']
        practice_slots = [g for g in existing_games if g.game_type == 'practice']
        playoff_slots = [g for g in existing_games if g.game_type == 'playoff']

        # If start_fresh, treat all as unassigned
        if start_fresh:
            for game in existing_games:
                game._temp_clear = True  # Mark for proposal

        # Phase 1: Pre-opening day (practices and scrimmages)
        self._generate_pre_opening(config, teams, league, all_slots, practice_slots, start_fresh)

        # Phase 2: Games (opening day onwards)
        self._generate_games(config, teams, league, all_slots, regular_slots, start_fresh)

        # Phase 3: Post-opening day practices
        self._generate_post_opening_practices(config, teams, league, all_slots, practice_slots, start_fresh)

    def _generate_pre_opening(self, config, teams, league, all_slots, practice_slots=None, start_fresh=False):
        """Generate practices and scrimmages before opening day."""
        if not config.first_practice_date or not config.opening_day_date:
            return

        # Get P and G days for this league, including team-specific overrides
        practice_days = set(config.practice_days or [])
        for team in teams:
            team_days = team.get_practice_days(config)
            practice_days.update(team_days)
        game_days = config.game_days or []
        all_activity_days = practice_days | set(game_days)

        # Get dates from first practice to day before opening
        current_date = config.first_practice_date
        end_date = config.opening_day_date - timedelta(days=1)

        activity_dates = []
        while current_date <= end_date:
            if current_date.weekday() in all_activity_days:
                # Skip season blackout dates
                if not self._is_blackout_date(current_date):
                    activity_dates.append(current_date)
            current_date += timedelta(days=1)

        if not activity_dates:
            return

        # If league has scrimmages, last activity date becomes scrimmage day
        # Otherwise, all dates are practice dates
        if config.has_scrimmages:
            scrimmage_date = activity_dates[-1]
            practice_dates = activity_dates[:-1]
        else:
            scrimmage_date = None
            practice_dates = activity_dates

        # Generate practices for each date (except scrimmage day if applicable)
        for practice_date in practice_dates:
            self._assign_practices_for_date(config, teams, league, all_slots, practice_date, practice_slots, start_fresh)

        # Generate scrimmages on scrimmage day (only if league has scrimmages)
        if scrimmage_date:
            self._generate_scrimmages(config, teams, league, all_slots, scrimmage_date)

    def _generate_games(self, config, teams, league, all_slots, existing_slots=None, start_fresh=False):
        """Generate regular season games from opening day onwards.

        If existing_slots is provided, fills those slots instead of creating new ones.
        Games are scheduled between opening_day_date and regular_season_end_date.
        """
        if not config.opening_day_date:
            return

        games_per_team = config.regular_season_games or 10
        game_days = config.game_days

        if not game_days:
            self.warnings.append({
                'type': 'no_game_days',
                'message': f'{config.league}: No game days configured.'
            })
            return

        # Check for regular season end date
        if not config.regular_season_end_date:
            self.warnings.append({
                'type': 'missing_end_date',
                'message': f'{config.league}: Regular season end date not set. Using 12 weeks from opening day.'
            })

        # Generate round-robin matchups
        matchups = self._generate_round_robin(teams, games_per_team)

        # Get game dates from opening day to regular season end
        game_dates = self._get_dates_for_days(
            config.opening_day_date,
            game_days,
            len(matchups) * 2,  # Get more dates than needed to ensure coverage
            end_date=config.regular_season_end_date  # Don't schedule past this date
        )

        # Get available slots for each date
        slots_by_date = self._group_slots_by_date(all_slots, game_dates, league, 'game')

        # Debug: Check specifically for Oct 15th for BB A
        from datetime import date as date_class
        oct15 = date_class(self.year, 10, 15)
        if config.league == 'BB A' and oct15 in game_dates:
            if oct15 in slots_by_date:
                slot_count = len(slots_by_date[oct15])
                slot_fields = [s.field.location_title for s in slots_by_date[oct15] if s.field]
                self.warnings.append({
                    'type': 'debug_bba_oct15',
                    'message': f'BB A Oct 15: {slot_count} slots available at start of Phase 1. Fields: {", ".join(slot_fields)}'
                })
            else:
                self.warnings.append({
                    'type': 'debug_bba_oct15',
                    'message': f'BB A Oct 15: NO slots in slots_by_date (date not found)'
                })

        # Debug: Report date coverage and diagnose missing dates
        if game_dates:
            dates_with_slots = [d for d in game_dates if d in slots_by_date]
            dates_without_slots = [d for d in game_dates if d not in slots_by_date]
            last_date_with_slots = max(dates_with_slots) if dates_with_slots else None

            # Check for dates that SHOULD have slots but don't
            if dates_without_slots and config.regular_season_end_date:
                # Find dates within the season that are missing slots
                missing_in_season = [d for d in dates_without_slots if d <= config.regular_season_end_date]
                if missing_in_season:
                    # Diagnose WHY slots are missing for a sample date
                    sample_date = missing_in_season[0]
                    sample_day = sample_date.weekday()
                    day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][sample_day]

                    # Count slots for this day of week
                    all_day_slots = [s for s in all_slots if s.day_of_week == sample_day]
                    game_capable = [s for s in all_day_slots if s.field and s.field.allows_games]
                    league_accessible = [s for s in game_capable if self._can_use_slot(s, league, 'game')]

                    if not league_accessible and game_capable:
                        # There are game-capable slots but this league can't use them
                        # Diagnose why
                        slot_leagues = set()
                        inaccessible_fields = set()
                        time_restricted = 0
                        for s in game_capable:
                            if s.league:
                                slot_leagues.add(s.league)
                            if league and s.field:
                                if not league.can_play_at_field(s.field.ID, is_practice=False):
                                    inaccessible_fields.add(s.field.location_title)
                            if league and s.start_time:
                                if not league.can_play_at_time(s.start_time):
                                    time_restricted += 1

                        reasons = []
                        if slot_leagues:
                            reasons.append(f'slots assigned to: {", ".join(sorted(slot_leagues))}')
                        if inaccessible_fields:
                            reasons.append(f'fields not in allowed list: {", ".join(sorted(inaccessible_fields))}')
                        if time_restricted:
                            reasons.append(f'{time_restricted} slots outside time restrictions')

                        if reasons:
                            self.warnings.append({
                                'type': 'slot_access',
                                'message': f'{config.league}: No accessible {day_name} game slots. '
                                           f'{len(game_capable)} game-capable slots exist but: {"; ".join(reasons)}.'
                            })

            if config.regular_season_end_date and last_date_with_slots:
                days_unused = (config.regular_season_end_date - last_date_with_slots).days
                if days_unused > 7:
                    self.warnings.append({
                        'type': 'date_coverage',
                        'message': f'{config.league}: Last available slot date is {last_date_with_slots.strftime("%b %d")}, '
                                   f'but season ends {config.regular_season_end_date.strftime("%b %d")} '
                                   f'({days_unused} days unused). Check field allocations for {", ".join(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] for d in game_days)}.'
                    })

        # Assign games to slots, using existing game records if available
        # For P/G leagues, limit to 2 games per team per week
        if config.has_pg_days:
            self._assign_games_to_slots(config, matchups, slots_by_date, league, existing_slots, start_fresh, max_games_per_week=2)
        else:
            self._assign_games_to_slots(config, matchups, slots_by_date, league, existing_slots, start_fresh)

    def _generate_post_opening_practices(self, config, teams, league, all_slots, practice_slots=None, start_fresh=False):
        """Generate practices after opening day (on P days only).

        Practices are scheduled from first_practice_date through regular_season_end_date.
        If first_practice_date is before opening_day, practices start from opening_day.
        Supports team-specific practice days that override the league default.

        For P/G leagues: Each team gets exactly 1 practice per week.
        """
        if not config.opening_day_date:
            return

        # Collect all practice days across all teams (league default + team overrides)
        all_practice_days = set(config.practice_days or [])
        for team in teams:
            team_days = team.get_practice_days(config)
            all_practice_days.update(team_days)

        if not all_practice_days:
            return

        # Use regular_season_end_date if set, otherwise default to 12 weeks
        if config.regular_season_end_date:
            end_date = config.regular_season_end_date
        else:
            end_date = config.opening_day_date + timedelta(weeks=12)

        # Practices can only start from first_practice_date (if set)
        # Use the later of opening_day_date and first_practice_date
        if config.first_practice_date:
            current_date = max(config.opening_day_date, config.first_practice_date)
        else:
            current_date = config.opening_day_date

        # For P/G leagues, limit to 1 practice per team per week
        is_pg_league = config.has_pg_days

        while current_date <= end_date:
            # Run on any day that ANY team in this league has as a practice day
            if current_date.weekday() in all_practice_days:
                # Skip season blackout dates
                if self._is_blackout_date(current_date):
                    current_date += timedelta(days=1)
                    continue
                if is_pg_league:
                    # For P/G leagues, pass weekly limit constraint
                    self._assign_practices_for_date(
                        config, teams, league, all_slots, current_date,
                        practice_slots, start_fresh, is_pre_opening=False,
                        max_practices_per_week=1
                    )
                else:
                    self._assign_practices_for_date(config, teams, league, all_slots, current_date, practice_slots, start_fresh)
            current_date += timedelta(days=1)

    def _generate_round_robin(self, teams, games_per_team):
        """Generate round-robin matchups ensuring PAIR BALANCE (rule a1) and TEAM BALANCE (rule e1).

        Constraints:
        - Each team plays exactly games_per_team games
        - All pairs must play each other (if mathematically possible)
        - The gap between most-played and least-played pair is at most 1

        Returns list of (home_team, away_team) tuples.
        """
        n = len(teams)
        if n < 2:
            return []

        total_games_needed = (games_per_team * n) // 2

        # Check if configuration is mathematically possible
        # With n teams and g games/team, total slots = n*g, total games = n*g/2
        # This must be an integer, so n*g must be even
        if (games_per_team * n) % 2 != 0:
            # Odd number of total slots - one team will be short
            self.warnings.append({
                'type': 'math_impossible',
                'message': f'Configuration warning: {n} teams × {games_per_team} games = {games_per_team * n} slots (odd). '
                          f'One team will have {games_per_team - 1} games. Consider {games_per_team - 1} or {games_per_team + 1} games/team.'
            })

        # Calculate pair frequency requirements
        min_games_per_pair = games_per_team // (n - 1)
        num_pairs = n * (n - 1) // 2
        base_total = num_pairs * min_games_per_pair
        extra_games_needed = total_games_needed - base_total

        # Create all pairs with their base targets
        all_pairs = []
        pair_targets = {}
        for i in range(n):
            for j in range(i + 1, n):
                pair_key = (teams[i].team_ID, teams[j].team_ID)
                all_pairs.append((teams[i], teams[j]))
                pair_targets[pair_key] = min_games_per_pair

        # FIXED EXTRA DISTRIBUTION: Guarantee each team gets their fair share
        # Each team needs: games_per_team total games
        # Each team's games from base: min_games_per_pair * (n-1)
        # Each team's extras needed: games_per_team - min_games_per_pair * (n-1)
        team_extras_needed = {}
        for t in teams:
            base_games = min_games_per_pair * (n - 1)
            team_extras_needed[t.team_ID] = games_per_team - base_games

        # Distribute extras using a round-robin approach that guarantees balance
        extras_given = {t.team_ID: 0 for t in teams}
        pair_has_extra = set()  # Track which pairs already have an extra
        candidate_pairs = list(all_pairs)
        # Sort deterministically by team IDs instead of random shuffle for consistent results
        candidate_pairs.sort(key=lambda p: (p[0].team_ID, p[1].team_ID))

        extras_assigned = 0
        max_iterations = extra_games_needed * 10  # Safety limit
        iteration = 0

        while extras_assigned < extra_games_needed and iteration < max_iterations:
            iteration += 1

            # Find the team that needs the most extras and hasn't gotten their fair share
            teams_needing_extras = [
                (team_extras_needed[t.team_ID] - extras_given[t.team_ID], t)
                for t in teams
                if extras_given[t.team_ID] < team_extras_needed[t.team_ID]
            ]

            if not teams_needing_extras:
                break

            # Sort by need descending (use team_ID as tiebreaker for determinism)
            teams_needing_extras.sort(key=lambda x: (-x[0], x[1].team_ID))
            # Take the first (already sorted by team_ID for determinism)
            chosen_team = teams_needing_extras[0][1]

            # Find a pair involving chosen_team that hasn't gotten an extra yet
            # and where the partner also needs extras
            best_pairs = []
            for pair in candidate_pairs:
                t1, t2 = pair
                pair_key = (min(t1.team_ID, t2.team_ID), max(t1.team_ID, t2.team_ID))
                if pair_key in pair_has_extra:
                    continue
                if t1.team_ID == chosen_team.team_ID:
                    partner = t2
                elif t2.team_ID == chosen_team.team_ID:
                    partner = t1
                else:
                    continue

                partner_need = team_extras_needed[partner.team_ID] - extras_given[partner.team_ID]
                if partner_need > 0:
                    best_pairs.append((partner_need, pair))

            if not best_pairs:
                # No valid pair found - try next team
                continue

            # Pick the pair with the partner that needs the most extras
            # Sort by partner_need descending
            best_pairs.sort(key=lambda x: -x[0])
            _, chosen_pair = best_pairs[0]
            t1, t2 = chosen_pair
            pair_key = (min(t1.team_ID, t2.team_ID), max(t1.team_ID, t2.team_ID))

            pair_targets[pair_key] += 1
            pair_has_extra.add(pair_key)
            extras_given[t1.team_ID] += 1
            extras_given[t2.team_ID] += 1
            extras_assigned += 1

        # Verify team targets sum correctly and fix if needed
        # LIMIT: Never increase a pair target beyond min_games_per_pair + 1 (to maintain gap ≤ 1)
        max_pair_target = min_games_per_pair + 1

        for t in teams:
            team_target_sum = sum(
                pair_targets[(min(t.team_ID, t2.team_ID), max(t.team_ID, t2.team_ID))]
                for t2 in teams if t2.team_ID != t.team_ID
            )
            # If a team doesn't have enough games from pair targets, try to add more
            while team_target_sum < games_per_team:
                # Find a pair involving this team that can be increased
                best_pair = None
                best_partner_need = -1
                for t2 in teams:
                    if t2.team_ID == t.team_ID:
                        continue
                    pair_key = (min(t.team_ID, t2.team_ID), max(t.team_ID, t2.team_ID))

                    # Don't exceed max pair target (to maintain gap ≤ 1)
                    if pair_targets[pair_key] >= max_pair_target:
                        continue

                    # Check if the other team can handle more games
                    partner_sum = sum(
                        pair_targets[(min(t2.team_ID, t3.team_ID), max(t2.team_ID, t3.team_ID))]
                        for t3 in teams if t3.team_ID != t2.team_ID
                    )
                    partner_need = games_per_team - partner_sum
                    if partner_need > 0 and partner_need > best_partner_need:
                        best_partner_need = partner_need
                        best_pair = pair_key

                if best_pair:
                    pair_targets[best_pair] += 1
                    team_target_sum += 1
                else:
                    # Can't add more without breaking pair balance
                    break

        # Now select matchups to meet pair targets while respecting team limits
        # Use a smarter approach: prioritize teams with fewer games remaining
        pair_counts = defaultdict(int)
        team_counts = {t.team_ID: 0 for t in teams}
        home_counts = {t.team_ID: 0 for t in teams}
        selected = []

        while len(selected) < total_games_needed:
            # Find pairs that still need games AND both teams are under their limit
            pairs_needing_games = []
            for t1, t2 in all_pairs:
                # Check team limits
                if team_counts[t1.team_ID] >= games_per_team or team_counts[t2.team_ID] >= games_per_team:
                    continue

                pair_key = (t1.team_ID, t2.team_ID) if t1.team_ID < t2.team_ID else (t2.team_ID, t1.team_ID)
                target = pair_targets[pair_key]
                current = pair_counts[pair_key]

                if current < target:
                    # Priority 1: Pairs with fewer games
                    # Priority 2: Teams closer to their limit (need fewer games) - to avoid leaving them stranded
                    # This ensures teams approaching their limit get paired with other teams approaching their limit
                    t1_remaining = games_per_team - team_counts[t1.team_ID]
                    t2_remaining = games_per_team - team_counts[t2.team_ID]
                    min_remaining = min(t1_remaining, t2_remaining)

                    # Lower min_remaining = higher priority (schedule these pairs first)
                    pairs_needing_games.append((current, min_remaining, t1.team_ID, t2.team_ID, t1, t2))

            if not pairs_needing_games:
                # No pairs available within targets - check if teams still need games
                # Try to add any valid matchup (may exceed pair targets)
                for t1, t2 in all_pairs:
                    if team_counts[t1.team_ID] >= games_per_team or team_counts[t2.team_ID] >= games_per_team:
                        continue
                    t1_remaining = games_per_team - team_counts[t1.team_ID]
                    t2_remaining = games_per_team - team_counts[t2.team_ID]
                    min_remaining = min(t1_remaining, t2_remaining)
                    pairs_needing_games.append((0, min_remaining, t1.team_ID, t2.team_ID, t1, t2))

                if not pairs_needing_games:
                    break

            # Sort by pair count (ascending), then by min_remaining (ascending = tightest constraint first)
            pairs_needing_games.sort()

            # Select from top candidates (same pair count and similar remaining)
            min_count = pairs_needing_games[0][0]
            min_remaining = pairs_needing_games[0][1]
            # Allow a small window for remaining games
            top_candidates = [p for p in pairs_needing_games
                            if p[0] == min_count and p[1] <= min_remaining + 1]

            # Pick deterministically (first candidate, already sorted by team IDs)
            chosen = top_candidates[0]
            t1, t2 = chosen[4], chosen[5]

            # Determine home/away based on balance
            if home_counts[t1.team_ID] <= home_counts[t2.team_ID]:
                selected.append((t1, t2))
                home_counts[t1.team_ID] += 1
            else:
                selected.append((t2, t1))
                home_counts[t2.team_ID] += 1

            # Update counts
            pair_key = (t1.team_ID, t2.team_ID) if t1.team_ID < t2.team_ID else (t2.team_ID, t1.team_ID)
            pair_counts[pair_key] += 1
            team_counts[t1.team_ID] += 1
            team_counts[t2.team_ID] += 1

        return selected

    def _find_complete_round(self, eligible_matchups, available_slots, games_needed, all_team_ids, late_counts=None):
        """Find a combination of matchups that covers all teams.

        Uses backtracking to find games_needed matchups where all teams play exactly once.
        Then assigns slots with late game balance awareness if late_counts is provided.

        Args:
            eligible_matchups: List of (idx, priority, home, away) tuples
            available_slots: List of slot_info dicts
            games_needed: Number of games to schedule (n_teams / 2)
            all_team_ids: Set of all team IDs that must be covered
            late_counts: Optional dict of team_id -> late game count for balancing

        Returns:
            List of (idx, home, away, slot_info) tuples, or None if no valid combination
        """
        if len(available_slots) < games_needed:
            return None

        # Try to find a combination using backtracking (without slot assignment)
        def backtrack(selected, teams_used):
            if len(selected) == games_needed:
                return selected.copy()

            for matchup in eligible_matchups:
                # Handle both 4-element and 5-element tuples (with is_repeat)
                if len(matchup) == 5:
                    idx, priority, is_repeat, home, away = matchup
                else:
                    idx, priority, home, away = matchup

                # Skip if either team already used
                if home.team_ID in teams_used or away.team_ID in teams_used:
                    continue

                # Skip if this matchup was already selected
                if any(s[0] == idx for s in selected):
                    continue

                # Try adding this matchup (without slot - we'll assign later)
                selected.append((idx, home, away))
                teams_used.add(home.team_ID)
                teams_used.add(away.team_ID)

                result = backtrack(selected, teams_used)
                if result is not None:
                    return result

                # Backtrack
                selected.pop()
                teams_used.remove(home.team_ID)
                teams_used.remove(away.team_ID)

            return None

        matchups = backtrack([], set())
        if matchups is None:
            return None

        # Now assign slots with late game balance awareness
        # Keep the same slots in the same positions, but assign matchups
        # so that teams with fewer late games get the late slots
        if late_counts is not None:
            # Identify which slot positions are late (6pm or later)
            late_slot_indices = set()
            for i, slot in enumerate(available_slots[:len(matchups)]):
                if slot['datetime'] and slot['datetime'].hour >= 18:
                    late_slot_indices.add(i)

            if late_slot_indices:
                # Sort matchups by late need: teams with fewer late games should get late slots
                def matchup_late_need(m):
                    idx, home, away = m
                    home_late = late_counts.get(home.team_ID, 0)
                    away_late = late_counts.get(away.team_ID, 0)
                    return (min(home_late, away_late), home_late + away_late)

                matchups_sorted = sorted(matchups, key=matchup_late_need)

                # Assign: matchups with LOWEST late_need get late slot positions
                # matchups with HIGHEST late_need get early slot positions
                result = [None] * len(matchups)
                late_indices = sorted(late_slot_indices)
                early_indices = [i for i in range(len(matchups)) if i not in late_slot_indices]

                # Teams needing late slots (lowest late_need) get late positions
                for i, matchup in enumerate(matchups_sorted):
                    if i < len(late_indices):
                        pos = late_indices[i]
                    else:
                        pos = early_indices[i - len(late_indices)]
                    idx, home, away = matchup
                    result[pos] = (idx, home, away, available_slots[pos])

                return result

        # No late balancing needed - assign sequentially
        return [(idx, home, away, available_slots[i]) for i, (idx, home, away) in enumerate(matchups)]

    def _generate_scrimmages(self, config, teams, league, all_slots, scrimmage_date):
        """Generate scrimmages - one per team, deterministic pairing.

        Scrimmages are treated like games for time-based scheduling (2 hours each).
        """
        # Sort teams by ID for deterministic pairing
        shuffled = sorted(teams, key=lambda t: t.team_ID)

        # Get available slots for this date
        day_of_week = scrimmage_date.weekday()
        available_slots = [
            s for s in all_slots
            if s.day_of_week == day_of_week and self._can_use_slot(s, league, 'game')
        ]

        if not available_slots:
            self.warnings.append({
                'type': 'no_slots',
                'message': f'{config.league}: No available slots for scrimmages on {scrimmage_date}'
            })
            return

        # Track slot usage for time-based capacity
        slot_usage = defaultdict(int)

        # Get date string for team-day tracking
        date_str = scrimmage_date.isoformat() if hasattr(scrimmage_date, 'isoformat') else str(scrimmage_date)

        for i in range(0, len(shuffled) - 1, 2):
            home = shuffled[i]
            away = shuffled[i + 1]

            # Check if either team already has activity on this day
            home_day_key = (home.team_ID, date_str)
            away_day_key = (away.team_ID, date_str)
            if home_day_key in self._team_day_usage or away_day_key in self._team_day_usage:
                # One of the teams already has activity today, skip this scrimmage
                self.warnings.append({
                    'type': 'team_busy',
                    'message': f'{config.league}: Cannot schedule scrimmage {home.display_name} vs {away.display_name} - team already has activity today'
                })
                continue

            # Find a slot with capacity that isn't already used globally
            assigned_slot = None
            time_offset = 0
            game_duration = league.get_game_duration() if league else GAME_DURATION_MINUTES
            for slot in available_slots:
                capacity = self._get_time_based_game_capacity(slot, league)
                field_id = slot.field.ID if slot and slot.field else None

                # Try each time offset in this slot
                for time_slot_idx in range(slot_usage[slot.slot_ID], capacity):
                    test_offset = time_slot_idx * game_duration
                    test_datetime = self._slot_to_datetime(slot, scrimmage_date)
                    if test_datetime and test_offset > 0:
                        test_datetime = test_datetime + timedelta(minutes=test_offset)

                    # Check global usage (duration-aware)
                    if field_id and test_datetime:
                        if not self._check_field_time_available(
                            field_id, test_datetime, game_duration, config.league, is_practice=False
                        ):
                            continue  # Would overlap with another activity

                    # Found an available slot/time
                    assigned_slot = slot
                    time_offset = test_offset
                    slot_usage[slot.slot_ID] = time_slot_idx + 1
                    break

                if assigned_slot:
                    break

            if not assigned_slot:
                # All slots at capacity - skip this scrimmage
                self.warnings.append({
                    'type': 'no_capacity',
                    'message': f'{config.league}: No available slot for scrimmage {home.display_name} vs {away.display_name}'
                })
                continue

            game_datetime = self._slot_to_datetime(assigned_slot, scrimmage_date)
            if game_datetime and time_offset > 0:
                game_datetime = game_datetime + timedelta(minutes=time_offset)

            game = ProposedGame(
                game_type='scrimmage',
                league=config.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=home,
                away_team=away,
                field=assigned_slot.field if assigned_slot else None,
                game_date=game_datetime,
                is_scrimmage=True
            )
            game.slot = assigned_slot
            game.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(game)

            # Mark as used globally (with duration)
            field_id = assigned_slot.field.ID if assigned_slot and assigned_slot.field else None
            if field_id and game_datetime:
                self._add_field_time_usage(field_id, game_datetime, game_duration, config.league, is_practice=False)

            # Mark both teams as having activity on this day
            self._team_day_usage.add((home.team_ID, date_str))
            self._team_day_usage.add((away.team_ID, date_str))

        # Handle odd team out (no scrimmage partner)
        if len(shuffled) % 2 == 1:
            self.warnings.append({
                'type': 'odd_team',
                'message': f'{config.league}: Odd number of teams - {shuffled[-1].display_name} has no scrimmage partner.'
            })

    def _schedule_paired_practices_for_date(self, practice_date, all_slots, all_teams_by_id):
        """Schedule paired practices for this date. Called before regular practice assignment.

        Paired practices are processed first so both teams in a pairing get scheduled
        together on the same field. This bypasses normal solo-first logic.

        Args:
            practice_date: The date to schedule for
            all_slots: All available field slots for the season
            all_teams_by_id: Dict mapping team_id -> TeamSeason object

        Returns:
            Set of team IDs that have been assigned paired practices on this date
        """
        day_of_week = practice_date.weekday()
        date_str = practice_date.isoformat() if hasattr(practice_date, 'isoformat') else str(practice_date)
        assigned_team_ids = set()

        # Get pairings for this day of week
        pairings_today = [p for p in self._practice_pairings if p.day_of_week == day_of_week]
        if not pairings_today:
            return assigned_team_ids

        # Get available slots for this day
        available_slots = [
            s for s in all_slots
            if s.day_of_week == day_of_week
        ]
        if not available_slots:
            return assigned_team_ids

        for pairing in pairings_today:
            team_one = all_teams_by_id.get(pairing.team_one_id)
            team_two = all_teams_by_id.get(pairing.team_two_id)

            if not team_one or not team_two:
                continue

            # Check if either team already has activity today
            if (pairing.team_one_id, date_str) in self._team_day_usage:
                continue
            if (pairing.team_two_id, date_str) in self._team_day_usage:
                continue

            # Check if either team has already been assigned a paired practice today
            if (pairing.team_one_id, date_str) in self._paired_practice_assigned:
                continue
            if (pairing.team_two_id, date_str) in self._paired_practice_assigned:
                continue

            # Find an available slot (check both teams' league constraints if different leagues)
            league_one = self._league_cache.get(team_one.league)
            league_two = self._league_cache.get(team_two.league)

            # For time constraints, use the more restrictive of the two leagues
            from datetime import time as dt_time
            DEFAULT_LATEST_START = dt_time(19, 30)  # 7:30pm default

            latest_one = getattr(league_one, 'latest_start_time', None) or DEFAULT_LATEST_START if league_one else DEFAULT_LATEST_START
            latest_two = getattr(league_two, 'latest_start_time', None) or DEFAULT_LATEST_START if league_two else DEFAULT_LATEST_START
            latest_time = min(latest_one, latest_two)

            earliest_one = getattr(league_one, 'earliest_start_time', None) if league_one else None
            earliest_two = getattr(league_two, 'earliest_start_time', None) if league_two else None
            earliest_time = None
            if earliest_one and earliest_two:
                earliest_time = max(earliest_one, earliest_two)
            elif earliest_one:
                earliest_time = earliest_one
            elif earliest_two:
                earliest_time = earliest_two

            assigned_option = None
            practice_duration = self._get_activity_duration_minutes(team_one.league, is_practice=True)

            for slot in available_slots:
                if not slot.field:
                    continue
                field_id = slot.field.ID

                # Check field availability
                if not self._is_field_available_on_date(field_id, practice_date):
                    continue

                # Build time options for this slot
                time_capacity = self._get_time_based_practice_capacity(slot)
                for time_block in range(time_capacity):
                    time_offset_minutes = time_block * PRACTICE_DURATION_MINUTES
                    game_datetime = self._slot_to_datetime(slot, practice_date)
                    if game_datetime and time_offset_minutes > 0:
                        game_datetime = game_datetime + timedelta(minutes=time_offset_minutes)

                    if not game_datetime:
                        continue

                    practice_time = game_datetime.time()

                    # Check time constraints
                    if practice_time > latest_time:
                        continue
                    if earliest_time and practice_time < earliest_time:
                        continue

                    # Check if slot would overlap with existing activities
                    if not self._check_field_time_available(
                        field_id, game_datetime, practice_duration, team_one.league, is_practice=True
                    ):
                        continue

                    # Get field capacity - for paired practice we need at least 2
                    is_late = game_datetime.hour >= 19
                    field_capacity = slot.field.get_practice_capacity(is_late_slot=is_late)
                    if field_capacity < 2:
                        continue

                    datetime_key = (field_id, game_datetime.isoformat())
                    current_count = self._practice_slot_counts[datetime_key]
                    if current_count + 2 > field_capacity:
                        continue  # Not enough capacity for both teams

                    assigned_option = {
                        'slot': slot,
                        'field_id': field_id,
                        'datetime': game_datetime,
                        'datetime_key': datetime_key,
                        'field_capacity': field_capacity
                    }
                    break

                if assigned_option:
                    break

            if not assigned_option:
                self.warnings.append({
                    'type': 'paired_practice_capacity',
                    'message': f'No slot available for paired practice: {team_one.display_name} + {team_two.display_name} on {practice_date}'
                })
                continue

            # Assign paired practice - create two practice entries at the same time/field
            datetime_key = assigned_option['datetime_key']
            self._practice_slot_counts[datetime_key] += 2  # Both teams count

            # Add to global field time ranges
            self._add_field_time_usage(
                assigned_option['field_id'],
                assigned_option['datetime'],
                practice_duration,
                team_one.league,  # Use first team's league
                is_practice=True
            )

            # Create practice for team one
            practice_one = ProposedGame(
                game_type='practice',
                league=team_one.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=team_one,
                away_team=None,
                field=assigned_option['slot'].field,
                game_date=assigned_option['datetime']
            )
            practice_one.slot = assigned_option['slot']
            practice_one.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(practice_one)

            # Create practice for team two
            practice_two = ProposedGame(
                game_type='practice',
                league=team_two.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=team_two,
                away_team=None,
                field=assigned_option['slot'].field,
                game_date=assigned_option['datetime']
            )
            practice_two.slot = assigned_option['slot']
            practice_two.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(practice_two)

            # Mark both teams as having activity on this day
            self._team_day_usage.add((pairing.team_one_id, date_str))
            self._team_day_usage.add((pairing.team_two_id, date_str))

            # Mark both teams as having been assigned a paired practice
            self._paired_practice_assigned.add((pairing.team_one_id, date_str))
            self._paired_practice_assigned.add((pairing.team_two_id, date_str))

            # Track practice counts
            self._team_practice_counts[pairing.team_one_id] += 1
            self._team_practice_counts[pairing.team_two_id] += 1

            assigned_team_ids.add(pairing.team_one_id)
            assigned_team_ids.add(pairing.team_two_id)

        return assigned_team_ids

    def _assign_practices_for_date(self, config, teams, league, all_slots, practice_date, existing_slots=None, start_fresh=False, is_pre_opening=False, max_practices_per_week=None, force_sharing=False):
        """Assign practices for all teams on a given date.

        Args:
            is_pre_opening: If True, schedule practices on ALL activity days (game + practice),
                           not just practice days. Used for pre-opening period before games start.
            max_practices_per_week: If set, limits practices per team to this number per week.
                                   Used for P/G leagues (typically 1 practice per week).
            force_sharing: If True, skip Pass 1 (solo field preference) and go straight to
                          Pass 2 (sharing allowed). Used when other leagues need slots.
        """
        day_of_week = practice_date.weekday()

        # For weekly limiting, get the week number relative to opening day
        week_num = None
        if max_practices_per_week and config.opening_day_date:
            week_num = self._get_week_number(practice_date, config.opening_day_date)

        # Get available slots for this day
        available_slots = [
            s for s in all_slots
            if s.day_of_week == day_of_week and self._can_use_slot(s, league, 'practice')
        ]

        if not available_slots:
            self.warnings.append({
                'type': 'no_slots',
                'message': f'{config.league}: No practice slots available on {practice_date}'
            })
            return

        # Get date string for team-day tracking
        date_str = practice_date.isoformat() if hasattr(practice_date, 'isoformat') else str(practice_date)

        # Build all possible practice time slots with their global capacity status
        # Each slot can have multiple time blocks (e.g., 5:30 and 7:00 for a 3-hour slot)
        practice_options = []
        for slot in available_slots:
            if not slot.field:
                continue
            field_id = slot.field.ID
            # Check field availability using cache (no DB query)
            if not self._is_field_available_on_date(field_id, practice_date):
                continue
            time_capacity = self._get_time_based_practice_capacity(slot)

            for time_block in range(time_capacity):
                time_offset_minutes = time_block * PRACTICE_DURATION_MINUTES
                game_datetime = self._slot_to_datetime(slot, practice_date)
                if game_datetime and time_offset_minutes > 0:
                    game_datetime = game_datetime + timedelta(minutes=time_offset_minutes)

                if game_datetime:
                    from datetime import time as dt_time
                    DEFAULT_LATEST_START = dt_time(19, 30)  # 7:30pm default

                    # Check league time restrictions (latest_start_time with default)
                    practice_time = game_datetime.time()
                    latest_time = getattr(league, 'latest_start_time', None) or DEFAULT_LATEST_START
                    if practice_time > latest_time:
                        # This time block is after the league's latest allowed start time
                        continue
                    if hasattr(league, 'earliest_start_time') and league.earliest_start_time:
                        if practice_time < league.earliest_start_time:
                            # This time block is before the league's earliest allowed start time
                            continue

                    # Check if this slot would overlap with a game (duration-aware)
                    practice_duration = self._get_activity_duration_minutes(league, is_practice=True)
                    if not self._check_field_time_available(
                        field_id, game_datetime, practice_duration, config.league, is_practice=True
                    ):
                        continue  # Would overlap with another activity

                    # Get field's practice capacity from DB, considering late slots
                    is_late = game_datetime.hour >= 19
                    field_capacity = slot.field.get_practice_capacity(is_late_slot=is_late)

                    # Skip if field has no capacity at this time
                    if field_capacity == 0:
                        continue

                    practice_options.append({
                        'slot': slot,
                        'field_id': field_id,
                        'datetime': game_datetime,
                        'datetime_key': (field_id, game_datetime.isoformat()),
                        'field_capacity': field_capacity
                    })

        # Sort practice options by time and field preference
        # Weekdays (Mon-Fri): Earlier time > Preferred field (families want kids home earlier)
        # Weekends (Sat-Sun): Preferred field > Time (bedtime less of a concern)
        preferred_field_ids = league.preferred_field_ids if hasattr(league, 'preferred_field_ids') else []

        def get_field_preference_rank(field_id):
            """Lower rank = more preferred. Non-preferred fields get rank after all preferred."""
            if field_id in preferred_field_ids:
                return preferred_field_ids.index(field_id)
            return len(preferred_field_ids) + 1  # Non-preferred at end

        is_weekday = practice_date.weekday() < 5  # Mon=0 to Fri=4

        if is_weekday:
            # Weekday: sort by (time, field_preference)
            practice_options.sort(key=lambda opt: (
                opt['datetime'].hour * 60 + opt['datetime'].minute,  # Earlier times first
                get_field_preference_rank(opt['field_id'])  # Then by field preference
            ))
        else:
            # Weekend: sort by (field_preference, time)
            practice_options.sort(key=lambda opt: (
                get_field_preference_rank(opt['field_id']),  # Field preference first
                opt['datetime'].hour * 60 + opt['datetime'].minute  # Then by time
            ))

        # Sort teams by practice count (ascending) to prioritize teams with fewer practices
        # This helps ensure practice balance across the league (no team should have 2+ more than others)
        sorted_teams = sorted(teams, key=lambda t: self._team_practice_counts[t.team_ID])

        for team in sorted_teams:
            # Check if this day is a practice day for this team
            # Team-specific practice_days ALWAYS takes precedence if set
            if team.practice_days:
                # Team has specific practice days set - use those exclusively
                team_practice_days = team.get_practice_days(config)
                if day_of_week not in team_practice_days:
                    # This is not a practice day for this team
                    continue
            elif not is_pre_opening:
                # For post-opening without team-specific days, use league default
                team_practice_days = team.get_practice_days(config)
                if day_of_week not in team_practice_days:
                    # This is not a practice day for this team
                    continue
            # For pre-opening without team-specific days, schedule on all activity days

            # Check if team already has activity on this day
            team_day_key = (team.team_ID, date_str)
            if team_day_key in self._team_day_usage:
                # Team already has a game or practice today, skip
                continue

            # For P/G leagues, check weekly practice limit
            if max_practices_per_week and week_num is not None:
                team_week_key = (team.team_ID, week_num)
                if self._team_week_practices[team_week_key] >= max_practices_per_week:
                    # Team already has max practices this week, skip
                    continue

            # Find best slot with available capacity (respects field's practice_capacity from DB)
            # Teams can only share a practice slot if they are in the same league
            # PRIORITY: Prefer empty fields over sharing - coaches prefer being alone at a
            # non-preferred field over sharing their preferred field with another team
            # UNLESS force_sharing is True (to free up fields for other leagues)
            assigned_option = None

            # First pass: Look for an EMPTY field (no other teams)
            # Skip this pass if force_sharing is True (need to share to free slots for other leagues)
            if not force_sharing:
                for option in practice_options:
                    datetime_key = option['datetime_key']
                    current_count = self._practice_slot_counts[datetime_key]

                    # Only consider empty slots in first pass
                    if current_count > 0:
                        continue

                    assigned_option = option
                    break

            # Second pass: If no empty fields (or force_sharing), allow sharing (same league only)
            if not assigned_option:
                for option in practice_options:
                    datetime_key = option['datetime_key']
                    current_count = self._practice_slot_counts[datetime_key]
                    field_capacity = option['field_capacity']

                    # Check if slot has capacity
                    if current_count >= field_capacity:
                        continue

                    # Check if slot is being used by a different league (same-league sharing only)
                    slot_league = self._practice_slot_leagues.get(datetime_key)
                    if slot_league is not None and slot_league != config.league:
                        # Slot is already used by a different league, can't share
                        continue

                    assigned_option = option
                    break

            if not assigned_option:
                # All practice slots at capacity, skip this team's practice
                self.warnings.append({
                    'type': 'practice_capacity',
                    'message': f'{config.league}: No practice slot available for {team.display_name} on {practice_date} (all slots at capacity)'
                })
                continue

            # Increment the global practice count for this field/time and track the league
            self._practice_slot_counts[assigned_option['datetime_key']] += 1
            self._practice_slot_leagues[assigned_option['datetime_key']] = config.league

            # Also add to global field time ranges for duration-based overlap checking
            practice_duration = self._get_activity_duration_minutes(config.league, is_practice=True)
            self._add_field_time_usage(
                assigned_option['field_id'],
                assigned_option['datetime'],
                practice_duration,
                config.league,
                is_practice=True
            )

            practice = ProposedGame(
                game_type='practice',
                league=config.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=team,
                away_team=None,
                field=assigned_option['slot'].field,
                game_date=assigned_option['datetime']
            )
            practice.slot = assigned_option['slot']
            practice.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(practice)

            # Mark team as having activity on this day
            self._team_day_usage.add(team_day_key)

            # Track total practice count per team for balance
            self._team_practice_counts[team.team_ID] += 1

            # Update weekly practice counter for P/G leagues
            if max_practices_per_week and week_num is not None:
                team_week_key = (team.team_ID, week_num)
                self._team_week_practices[team_week_key] += 1

    def _schedule_practices_round_robin(self, league_configs, start_fresh=False):
        """Schedule practices using round-robin across leagues to ensure fairness.

        Instead of processing all practices for League A then League B (sequential),
        this processes one practice per league at a time (round-robin). This ensures
        all leagues get at least one practice slot before any league gets a second.

        When there are more leagues needing practices than empty slots, force_sharing
        is enabled to make teams within a league share fields, freeing up slots for
        other leagues.
        """
        # Build practice dates and team info for each league
        league_info = {}
        all_practice_dates = set()

        for config in league_configs:
            league_name = config.league
            teams = self._teams_by_league.get(league_name, [])
            if len(teams) < 2:
                continue

            league = self._league_cache.get(league_name)
            all_slots = self._all_field_slots

            # Collect all practice dates for this league (pre-opening + post-opening)
            practice_dates = []

            # Pre-opening dates
            if config.first_practice_date and config.opening_day_date:
                practice_days = config.practice_days or []
                game_days = config.game_days or []
                all_activity_days = set(practice_days + game_days)

                current_date = config.first_practice_date
                end_date = config.opening_day_date - timedelta(days=1)

                # Find scrimmage date to skip
                scrimmage_date = None
                if config.has_scrimmages:
                    check_date = end_date
                    while check_date >= config.first_practice_date:
                        if check_date.weekday() in all_activity_days and not self._is_blackout_date(check_date):
                            scrimmage_date = check_date
                            break
                        check_date -= timedelta(days=1)

                while current_date <= end_date:
                    if current_date.weekday() in all_activity_days and not self._is_blackout_date(current_date):
                        if current_date != scrimmage_date:
                            practice_dates.append(('pre', current_date))
                    current_date += timedelta(days=1)

            # Post-opening dates
            if config.opening_day_date and config.regular_season_end_date:
                practice_days = config.practice_days or []
                if practice_days:
                    current_date = config.opening_day_date
                    while current_date <= config.regular_season_end_date:
                        if current_date.weekday() in practice_days and not self._is_blackout_date(current_date):
                            practice_dates.append(('post', current_date))
                        current_date += timedelta(days=1)

            if practice_dates:
                league_info[league_name] = {
                    'config': config,
                    'teams': teams,
                    'league': league,
                    'all_slots': all_slots,
                    'practice_dates': practice_dates
                }
                all_practice_dates.update(d for _, d in practice_dates)

        # Build team lookup by ID for paired practice scheduling
        all_teams_by_id = {}
        for league_name, teams in self._teams_by_league.items():
            for team in teams:
                all_teams_by_id[team.team_ID] = team

        # Process each date in chronological order
        for practice_date in sorted(all_practice_dates):
            # FIRST: Schedule paired practices for this date
            # Paired practices are processed before regular assignment so both teams
            # in a pairing get scheduled together on the same field.
            if self._practice_pairings:
                self._schedule_paired_practices_for_date(
                    practice_date, self._all_field_slots, all_teams_by_id
                )

            # Get leagues that need practices on this date
            leagues_today = []
            for league_name, info in league_info.items():
                dates_for_league = [(phase, d) for phase, d in info['practice_dates'] if d == practice_date]
                if dates_for_league:
                    leagues_today.append((league_name, info, dates_for_league[0][0]))

            if not leagues_today:
                continue

            # Count empty slots available on this date
            empty_slot_count = self._count_empty_practice_slots_for_date(practice_date)

            # Count leagues that have at least one team needing practice
            leagues_needing_practice = 0
            for league_name, info, phase in leagues_today:
                config = info['config']
                teams = info['teams']
                is_pre_opening = (phase == 'pre')
                day_of_week = practice_date.weekday()
                date_str = practice_date.isoformat()

                for team in teams:
                    # Check if team needs practice on this day
                    # If team has specific practice days, use those (even pre-opening)
                    # Otherwise: pre-opening = all activity days, post-opening = league default
                    if team.practice_days:
                        team_practice_days = team.get_practice_days(config)
                        if day_of_week not in team_practice_days:
                            continue
                    elif not is_pre_opening:
                        team_practice_days = team.get_practice_days(config)
                        if day_of_week not in team_practice_days:
                            continue

                    team_day_key = (team.team_ID, date_str)
                    if team_day_key not in self._team_day_usage:
                        leagues_needing_practice += 1
                        break

            # Force sharing if more leagues need practices than empty slots
            force_sharing = empty_slot_count < leagues_needing_practice

            # Round-robin: process one team per league at a time until all done
            # Build queue of teams needing practice, grouped by league
            team_queues = {}
            for league_name, info, phase in leagues_today:
                config = info['config']
                teams = info['teams']
                is_pre_opening = (phase == 'pre')

                # Sort teams by practice count to prioritize those with fewer
                sorted_teams = sorted(teams, key=lambda t: self._team_practice_counts[t.team_ID])
                team_queues[league_name] = {
                    'teams': list(sorted_teams),
                    'config': config,
                    'info': info,
                    'phase': phase
                }

            # Round-robin loop with retry tracking to prevent infinite loops
            # Track how many times each team has been tried without success
            retry_counts = defaultdict(int)
            max_retries = 3  # Give up after this many failed attempts

            made_progress = True
            while made_progress:
                made_progress = False
                for league_name in list(team_queues.keys()):
                    queue_info = team_queues[league_name]
                    if not queue_info['teams']:
                        continue

                    config = queue_info['config']
                    info = queue_info['info']
                    phase = queue_info['phase']
                    teams = queue_info['teams']
                    is_pre_opening = (phase == 'pre')

                    # Try to assign practice to the first team in queue
                    team = teams[0]
                    success = self._assign_single_practice(
                        config, team, info['league'], info['all_slots'],
                        practice_date, is_pre_opening, force_sharing
                    )

                    if success:
                        # Remove team from queue - they got their practice
                        teams.pop(0)
                        retry_counts[team.team_ID] = 0  # Reset retry count
                        made_progress = True
                    else:
                        # Check if we should retry or give up
                        retry_counts[team.team_ID] += 1
                        teams.pop(0)
                        if retry_counts[team.team_ID] < max_retries:
                            # Move team to end of queue to retry later
                            teams.append(team)
                        # else: team has exhausted retries, don't re-add

    def _count_empty_practice_slots_for_date(self, practice_date):
        """Count how many practice slots are currently empty (unused) for a given date."""
        count = 0

        # Check all field slots
        for slot in self._all_field_slots:
            # Check if this slot's day_of_week matches practice_date
            if slot.day_of_week != practice_date.weekday():
                continue

            # Check field availability (start date, blackouts)
            field = slot.field
            if field.start_date and practice_date < field.start_date:
                continue

            # Get time-based practice capacity
            slot_datetime = self._slot_to_datetime(slot, practice_date)
            if not slot_datetime:
                continue

            # Get practice capacity (number of sequential practices that fit)
            time_capacity = self._get_time_based_practice_capacity(slot, league=None)
            practice_duration = 90  # Default

            for time_offset in range(0, time_capacity):
                actual_time = slot_datetime + timedelta(minutes=time_offset * practice_duration)
                datetime_key = (field.ID, actual_time.isoformat())

                # Check if slot is empty
                if self._practice_slot_counts[datetime_key] == 0:
                    count += 1

        return count

    def _assign_single_practice(self, config, team, league, all_slots, practice_date, is_pre_opening, force_sharing):
        """Assign a single practice to a team on a given date.

        Returns True if practice was assigned, False otherwise.
        """
        day_of_week = practice_date.weekday()
        date_str = practice_date.isoformat()

        # Check if team should practice on this day
        # If team has specific practice days, use those (even pre-opening)
        # Otherwise: pre-opening = all activity days, post-opening = league default
        if team.practice_days:
            team_practice_days = team.get_practice_days(config)
            if day_of_week not in team_practice_days:
                return False
        elif not is_pre_opening:
            team_practice_days = team.get_practice_days(config)
            if day_of_week not in team_practice_days:
                return False

        # Check if team already has activity today
        team_day_key = (team.team_ID, date_str)
        if team_day_key in self._team_day_usage:
            return False

        # Build practice options for this date
        practice_options = []
        practice_duration = self._get_activity_duration_minutes(config.league, is_practice=True)
        is_weekend = practice_date.weekday() >= 5

        for slot in all_slots:
            if slot.day_of_week != day_of_week:
                continue

            # Check field availability using cache
            field = slot.field
            if not self._is_field_available_on_date(field.ID, practice_date):
                continue

            # Check if league can use this field for practice
            if league and not league.can_play_at_field(field.ID, is_practice=True):
                continue

            # Get slot datetime
            slot_datetime = self._slot_to_datetime(slot, practice_date)
            if not slot_datetime:
                continue

            # Check field capacity
            is_late = slot_datetime.hour >= 19
            field_capacity = field.get_practice_capacity(is_late_slot=is_late)
            if field_capacity == 0:
                continue

            # Get time-based capacity (how many practice slots fit in the field slot)
            time_capacity = self._get_time_based_practice_capacity(slot, league)

            # Get league time restrictions
            from datetime import time as dt_time
            DEFAULT_LATEST_START = dt_time(19, 30)
            latest_time = getattr(league, 'latest_start_time', None) or DEFAULT_LATEST_START
            earliest_time = getattr(league, 'earliest_start_time', None)

            for time_offset in range(0, time_capacity):
                actual_time = slot_datetime + timedelta(minutes=time_offset * practice_duration)
                datetime_key = (field.ID, actual_time.isoformat())

                # Check league time restrictions on actual_time (not slot start time)
                actual_time_only = actual_time.time()
                if actual_time_only > latest_time:
                    continue
                if earliest_time and actual_time_only < earliest_time:
                    continue

                # Check for overlap with existing activities
                if not self._check_field_time_available(field.ID, actual_time, practice_duration, config.league, is_practice=True):
                    continue

                practice_options.append({
                    'slot': slot,
                    'field_id': field.ID,
                    'datetime': actual_time,
                    'datetime_key': datetime_key,
                    'field_capacity': field_capacity
                })

        if not practice_options:
            return False

        # Sort options (weekday: time first, weekend: field preference first)
        preferred_fields = []
        if league:
            preferred_fields = league.preferred_fields or []
        preferred_set = set(preferred_fields)

        def get_field_preference_rank(field_id):
            if field_id in preferred_set:
                return preferred_fields.index(field_id)
            return len(preferred_fields) + 1000

        if not is_weekend:
            practice_options.sort(key=lambda opt: (
                opt['datetime'].hour * 60 + opt['datetime'].minute,
                get_field_preference_rank(opt['field_id'])
            ))
        else:
            practice_options.sort(key=lambda opt: (
                get_field_preference_rank(opt['field_id']),
                opt['datetime'].hour * 60 + opt['datetime'].minute
            ))

        # Find best slot (Pass 1: empty, Pass 2: sharing allowed)
        assigned_option = None

        if not force_sharing:
            # First pass: Look for EMPTY field
            for option in practice_options:
                datetime_key = option['datetime_key']
                if self._practice_slot_counts[datetime_key] == 0:
                    assigned_option = option
                    break

        # Second pass: Allow sharing (same league only)
        if not assigned_option:
            for option in practice_options:
                datetime_key = option['datetime_key']
                current_count = self._practice_slot_counts[datetime_key]
                field_capacity = option['field_capacity']

                if current_count >= field_capacity:
                    continue

                slot_league = self._practice_slot_leagues.get(datetime_key)
                if slot_league is not None and slot_league != config.league:
                    continue

                assigned_option = option
                break

        if not assigned_option:
            return False

        # Assign the practice
        self._practice_slot_counts[assigned_option['datetime_key']] += 1
        self._practice_slot_leagues[assigned_option['datetime_key']] = config.league

        self._add_field_time_usage(
            assigned_option['field_id'],
            assigned_option['datetime'],
            practice_duration,
            config.league,
            is_practice=True
        )

        practice = ProposedGame(
            game_type='practice',
            league=config.league,
            year=self.year,
            is_spring=self.is_spring,
            home_team=team,
            away_team=None,
            field=assigned_option['slot'].field,
            game_date=assigned_option['datetime']
        )
        practice.slot = assigned_option['slot']
        practice.id = self._next_id
        self._next_id += 1
        self.proposed_games.append(practice)

        self._team_day_usage.add(team_day_key)
        self._team_practice_counts[team.team_ID] += 1

        return True

    def _assign_games_to_slots(self, config, matchups, slots_by_date, league, existing_game_records=None, start_fresh=False, max_games_per_week=None):
        """Assign game matchups to available slots.

        Scheduling strategy:
        - Schedule by DATE to ensure all teams play on the same game days
        - For each date, schedule n/2 games (where n = team count) so all teams play
        - Only use a date if we have enough slot capacity for all teams
        - Prioritizes teams with fewer scheduled games when selecting matchups

        Time-based scheduling:
        - Each game is 2 hours (120 minutes)
        - A 4-hour slot can hold 2 sequential games

        Args:
            max_games_per_week: For P/G leagues, limit each team to this many games per week (typically 2)
        """
        existing_idx = 0
        games_per_team = config.regular_season_games or 10

        # Track home/away counts for balancing
        home_counts = defaultdict(int)
        away_counts = defaultdict(int)
        early_counts = defaultdict(int)
        late_counts = defaultdict(int)

        # Track total games per team
        team_game_counts = defaultdict(int)

        # Track games per pair for a1 compliance (pair balance)
        pair_game_counts = defaultdict(int)  # (team_id1, team_id2) -> count, where id1 < id2

        # Track per-pair home team for a2 compliance (alternate home/away per pair)
        # Key: (min_team_id, max_team_id), Value: list of home_team_ids for each game
        pair_home_history = defaultdict(list)

        # Track last scheduled pair for gap compliance (avoid back-to-back same pairs)
        last_scheduled_pair = None

        # Filter existing records to those needing assignment
        records_to_fill = []
        if existing_game_records:
            for g in existing_game_records:
                if start_fresh or g.home_ID is None:
                    records_to_fill.append(g)

        # Get all team IDs
        all_team_ids = set()
        for home, away in matchups:
            all_team_ids.add(home.team_ID)
            all_team_ids.add(away.team_ID)
        num_teams = len(all_team_ids)
        games_per_date = num_teams // 2  # All teams play = n/2 games
        is_odd_league = num_teams % 2 == 1  # Odd team count - can't have complete rounds

        # Build slot info grouped by date
        # Get league-specific game duration
        game_duration = league.get_game_duration() if league else GAME_DURATION_MINUTES
        slots_info_by_date = {}
        for game_date, slots in sorted(slots_by_date.items()):
            date_slots = []
            for slot in slots:
                slot_capacity = self._get_time_based_game_capacity(slot, league)
                field_id = slot.field.ID if slot and slot.field else None
                for time_slot_idx in range(slot_capacity):
                    time_offset_minutes = time_slot_idx * game_duration
                    game_datetime = self._slot_to_datetime(slot, game_date)
                    if game_datetime and time_offset_minutes > 0:
                        game_datetime = game_datetime + timedelta(minutes=time_offset_minutes)
                    date_slots.append({
                        'date': game_date,
                        'slot': slot,
                        'datetime': game_datetime,
                        'field_id': field_id,
                        'time_slot_idx': time_slot_idx
                    })
            slots_info_by_date[game_date] = date_slots

        # Track which matchups have been scheduled
        scheduled_matchups = set()
        unscheduled_matchups = list(range(len(matchups)))

        # Process dates in order, scheduling full rounds when possible
        for game_date in sorted(slots_info_by_date.keys()):
            date_slots = slots_info_by_date[game_date]
            date_str = game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date)

            # For weekly limiting in P/G leagues, calculate week number relative to opening day
            week_num = None
            if max_games_per_week and config.opening_day_date:
                week_num = self._get_week_number(game_date, config.opening_day_date)

            # Filter out slots already used by other leagues (duration-aware)
            available_date_slots = []
            used_by_other_league = []
            game_duration = self._get_activity_duration_minutes(config.league, is_practice=False)
            for slot_info in date_slots:
                field_id = slot_info['field_id']
                game_datetime = slot_info['datetime']
                if field_id and game_datetime:
                    if self._check_field_time_available(
                        field_id, game_datetime, game_duration, config.league, is_practice=False
                    ):
                        available_date_slots.append(slot_info)
                    else:
                        used_by_other_league.append(slot_info)
                else:
                    available_date_slots.append(slot_info)

            # Record skipped slots (used by other leagues)
            for slot_info in used_by_other_league:
                self._record_decision(
                    date_str, config.league, slot_info['slot'],
                    'skipped', 'Already used by another league',
                    game_info={'time': slot_info['datetime'].strftime('%I:%M %p') if slot_info['datetime'] else 'N/A'}
                )

            # Check if we have enough slots for a full round (all teams playing)
            # NOTE: We no longer skip dates with insufficient capacity - we use greedy
            # scheduling to use whatever slots are available. This ensures better
            # distribution of games and prevents catch-up pass overload.
            use_greedy_for_partial = len(available_date_slots) < games_per_date

            # Find teams that need more games and don't have activity on this day
            available_teams = set()
            unavailable_teams = []
            for team_id in sorted(all_team_ids):  # Sort for deterministic iteration
                team_day_key = (team_id, date_str)
                if team_day_key not in self._team_day_usage:
                    if team_game_counts[team_id] < games_per_team:
                        # For P/G leagues, also check weekly game limit
                        if max_games_per_week and week_num is not None:
                            team_week_key = (team_id, week_num)
                            if self._team_week_games[team_week_key] >= max_games_per_week:
                                unavailable_teams.append(f'Team {team_id} hit weekly limit ({max_games_per_week} games)')
                                continue
                        available_teams.add(team_id)
                    else:
                        unavailable_teams.append(f'Team {team_id} has enough games')
                else:
                    unavailable_teams.append(f'Team {team_id} already has activity')

            # Find matchups where both teams are available and need games
            eligible_matchups = []
            for idx in unscheduled_matchups:
                if idx in scheduled_matchups:
                    continue
                home, away = matchups[idx]
                if home.team_ID in available_teams and away.team_ID in available_teams:
                    # Prioritize by how many games teams still need
                    home_needs = games_per_team - team_game_counts[home.team_ID]
                    away_needs = games_per_team - team_game_counts[away.team_ID]
                    # Deprioritize if this is the same pair as last scheduled (gap rule)
                    pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))
                    is_repeat = 1 if pair_key == last_scheduled_pair else 0
                    eligible_matchups.append((idx, home_needs + away_needs, is_repeat, home, away))

            # Sort by priority: avoid repeat pairs first, then most needed
            eligible_matchups.sort(key=lambda x: (x[2], -x[1]))

            # For odd team counts, partial capacity dates, or when not all teams available, use greedy scheduling
            # For even team counts with all teams available and full capacity, try to find complete rounds
            matchups_for_today = None

            if is_odd_league or use_greedy_for_partial or len(available_teams) < num_teams:
                # Greedy scheduling with late game balance awareness
                # Process slots in order, picking best matchup for each slot
                # For late slots: prefer teams with fewer late games
                # For early slots: prefer teams with more late games (so they get early)
                matchups_for_today = []
                teams_used_today = set()

                for slot in available_date_slots:
                    is_late_slot = slot['datetime'] and slot['datetime'].hour >= 18

                    # Find best available matchup for this slot
                    best_matchup = None
                    best_score = None

                    for idx, priority, is_repeat, home, away in eligible_matchups:
                        if home.team_ID in teams_used_today or away.team_ID in teams_used_today:
                            continue

                        home_late = late_counts.get(home.team_ID, 0)
                        away_late = late_counts.get(away.team_ID, 0)
                        min_late = min(home_late, away_late)
                        sum_late = home_late + away_late

                        # For late slots: lower late count = better (teams need late games)
                        # For early slots: higher late count = better (teams already have late games)
                        if is_late_slot:
                            score = (min_late, sum_late, is_repeat, -priority)  # Lower is better
                        else:
                            score = (-min_late, -sum_late, is_repeat, -priority)  # Higher late count is better

                        if best_score is None or score < best_score:
                            best_score = score
                            best_matchup = (idx, home, away)

                    if best_matchup:
                        idx, home, away = best_matchup
                        matchups_for_today.append((idx, home, away, slot))
                        teams_used_today.add(home.team_ID)
                        teams_used_today.add(away.team_ID)

                if not matchups_for_today:
                    matchups_for_today = None
            else:
                # If not all teams are available for even leagues, log and try greedy
                if len(available_teams) < num_teams:
                    for slot_info in available_date_slots:
                        self._record_decision(
                            date_str, config.league, slot_info['slot'],
                            'skipped', f'Not all teams available ({len(available_teams)}/{num_teams}). Will retry in catch-up pass.',
                            game_info={'unavailable': unavailable_teams[:3]}
                        )
                    continue

                # Try to find a COMPLETE round (all teams play) for even leagues
                # Pass late_counts for balance-aware slot assignment
                matchups_for_today = self._find_complete_round(
                    eligible_matchups, available_date_slots, games_per_date, all_team_ids,
                    late_counts=late_counts
                )

                # If complete round fails, fall back to greedy with late game balance awareness
                if matchups_for_today is None:
                    matchups_for_today = []
                    teams_used_today = set()

                    # Process slots in order, picking best matchup for each slot
                    for slot in available_date_slots:
                        is_late_slot = slot['datetime'] and slot['datetime'].hour >= 18

                        # Find best available matchup for this slot
                        best_matchup = None
                        best_score = None

                        for idx, priority, is_repeat, home, away in eligible_matchups:
                            if home.team_ID in teams_used_today or away.team_ID in teams_used_today:
                                continue

                            home_late = late_counts.get(home.team_ID, 0)
                            away_late = late_counts.get(away.team_ID, 0)
                            min_late = min(home_late, away_late)
                            sum_late = home_late + away_late

                            # For late slots: lower late count = better
                            # For early slots: higher late count = better
                            if is_late_slot:
                                score = (min_late, sum_late, is_repeat, -priority)
                            else:
                                score = (-min_late, -sum_late, is_repeat, -priority)

                            if best_score is None or score < best_score:
                                best_score = score
                                best_matchup = (idx, home, away)

                        if best_matchup:
                            idx, home, away = best_matchup
                            matchups_for_today.append((idx, home, away, slot))
                            teams_used_today.add(home.team_ID)
                            teams_used_today.add(away.team_ID)

                    if not matchups_for_today:
                        matchups_for_today = None

            # Only proceed if we have matchups to schedule
            if matchups_for_today is None or len(matchups_for_today) == 0:
                # Can't schedule any games - skip this date
                for slot_info in available_date_slots[:games_per_date]:
                    self._record_decision(
                        date_str, config.league, slot_info['slot'],
                        'skipped', f'No valid matchups available for this date',
                        game_info=None
                    )
                continue

            teams_scheduled_today = set()
            for _, home, away, _ in matchups_for_today:
                teams_scheduled_today.add(home.team_ID)
                teams_scheduled_today.add(away.team_ID)

            # Commit the games for this date
            for idx, home, away, slot_info in matchups_for_today:
                slot = slot_info['slot']
                game_datetime = slot_info['datetime']
                field_id = slot_info['field_id']

                # Balance home/away - prioritize per-pair alternation (a2), then overall balance
                actual_home, actual_away = home, away
                pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))

                # Check per-pair history first
                pair_history = pair_home_history[pair_key]
                if pair_history:
                    # Alternate: if last home was team A, make team B home this time
                    last_home = pair_history[-1]
                    if last_home == home.team_ID:
                        actual_home, actual_away = away, home
                    # else keep home as is (last_home was away, so home should be home)
                elif home_counts[home.team_ID] > away_counts[home.team_ID] + 1:
                    # No pair history - use overall balance
                    actual_home, actual_away = away, home

                is_early = game_datetime.hour < 18 if game_datetime else True

                game = ProposedGame(
                    game_type='regular',
                    league=config.league,
                    year=self.year,
                    is_spring=self.is_spring,
                    home_team=actual_home,
                    away_team=actual_away,
                    field=slot.field if slot else None,
                    game_date=game_datetime
                )
                game.slot = slot

                # Link to existing game record if available
                if existing_idx < len(records_to_fill):
                    existing_game = records_to_fill[existing_idx]
                    game.id = existing_game.ID
                    game.existing_record = existing_game
                    self._slot_assignments[existing_game.ID] = {
                        'game_id': existing_game.ID,
                        'home_id': actual_home.team_ID,
                        'away_id': actual_away.team_ID,
                        'game_date': game_datetime.isoformat() if game_datetime else None,
                        'field_id': field_id
                    }
                    existing_idx += 1
                else:
                    game.id = self._next_id
                    self._next_id += 1

                self.proposed_games.append(game)

                # Record the assignment decision
                self._record_decision(
                    date_str, config.league, slot,
                    'assigned', 'Full round scheduling',
                    game_info={
                        'home': actual_home.display_name,
                        'away': actual_away.display_name,
                        'time': game_datetime.strftime('%I:%M %p') if game_datetime else 'N/A',
                        'phase': 'full_round'
                    }
                )

                # Update tracking
                home_counts[actual_home.team_ID] += 1
                away_counts[actual_away.team_ID] += 1
                team_game_counts[home.team_ID] += 1
                team_game_counts[away.team_ID] += 1
                if is_early:
                    early_counts[actual_home.team_ID] += 1
                    early_counts[actual_away.team_ID] += 1
                else:
                    late_counts[actual_home.team_ID] += 1
                    late_counts[actual_away.team_ID] += 1

                # Mark field/time as used globally (with duration)
                if field_id and game_datetime:
                    self._add_field_time_usage(field_id, game_datetime, game_duration, config.league, is_practice=False)

                # Mark teams as having activity on this day
                self._team_day_usage.add((home.team_ID, date_str))
                self._team_day_usage.add((away.team_ID, date_str))

                # Track pair game count for a1 compliance
                pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))
                pair_game_counts[pair_key] += 1

                # Track per-pair home history for a2 compliance
                pair_home_history[pair_key].append(actual_home.team_ID)

                # Track last scheduled pair for gap compliance
                last_scheduled_pair = pair_key

                # Update weekly game counter for P/G leagues
                if max_games_per_week and week_num is not None:
                    self._team_week_games[(home.team_ID, week_num)] += 1
                    self._team_week_games[(away.team_ID, week_num)] += 1

                scheduled_matchups.add(idx)
                unscheduled_matchups = [m for m in unscheduled_matchups if m != idx]

        # Second pass: Fill remaining games (catch-up)
        # IMPORTANT: Prioritize pairs that have never played (a1 rule compliance)
        # This may result in some e2 violations but ensures a1 (all pairs play) is met

        # Sort unscheduled matchups by pair game count (0 games first = highest priority)
        def matchup_priority(idx):
            home, away = matchups[idx]
            pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))
            pair_count = pair_game_counts[pair_key]
            # Secondary: teams that need more games
            team_need = (games_per_team - team_game_counts[home.team_ID]) + (games_per_team - team_game_counts[away.team_ID])
            return (pair_count, -team_need)  # Lower pair count = higher priority

        # Sort unscheduled matchups by priority (pairs with 0 games first)
        unscheduled_matchups.sort(key=matchup_priority)

        still_unscheduled = []
        for idx in unscheduled_matchups:
            if idx in scheduled_matchups:
                continue

            home, away = matchups[idx]
            pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))

            # Only skip if BOTH: teams have enough games AND pair has already played
            if (team_game_counts[home.team_ID] >= games_per_team and
                team_game_counts[away.team_ID] >= games_per_team and
                pair_game_counts[pair_key] > 0):
                scheduled_matchups.add(idx)
                continue

            # Find any available slot with early/late balance awareness
            assigned = False
            # Calculate late need for this matchup - teams with fewer late games need late slots more
            matchup_late_count = self._get_late_need_score(
                [home.team_ID, away.team_ID], late_counts
            )
            # Get average late count for the league to determine if this matchup needs late slots
            all_late_counts = [late_counts.get(tid, 0) for tid in all_team_ids]
            avg_late = sum(all_late_counts) / len(all_late_counts) if all_late_counts else 0

            for game_date in sorted(slots_info_by_date.keys()):
                if assigned:
                    break
                date_str = game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date)

                # Check if teams already have activity on this day
                home_day_key = (home.team_ID, date_str)
                away_day_key = (away.team_ID, date_str)
                if home_day_key in self._team_day_usage or away_day_key in self._team_day_usage:
                    continue

                # For P/G leagues, check weekly game limit
                if max_games_per_week and config.opening_day_date:
                    catch_up_week_num = self._get_week_number(game_date, config.opening_day_date)
                    home_week_key = (home.team_ID, catch_up_week_num)
                    away_week_key = (away.team_ID, catch_up_week_num)
                    if (self._team_week_games[home_week_key] >= max_games_per_week or
                            self._team_week_games[away_week_key] >= max_games_per_week):
                        continue

                # Collect available slots for this date, separated by early/late
                available_early_slots = []
                available_late_slots = []
                for slot_info in slots_info_by_date[game_date]:
                    field_id = slot_info['field_id']
                    game_datetime = slot_info['datetime']

                    # Check if slot is available (duration-aware)
                    if field_id and game_datetime:
                        if not self._check_field_time_available(
                            field_id, game_datetime, game_duration, config.league, is_practice=False
                        ):
                            continue

                    if game_datetime and game_datetime.hour < 18:
                        available_early_slots.append(slot_info)
                    else:
                        available_late_slots.append(slot_info)

                # Choose slot: prefer early slots for everyone
                # Only use late slots when no early available, and prioritize teams with fewer late games
                slot_info = None
                if available_early_slots:
                    # Early slots preferred for everyone
                    slot_info = available_early_slots[0]
                elif available_late_slots:
                    # Must use late slot - this will be balanced by the outer loop
                    # (catch-up iterates through matchups, and teams with fewer late games
                    # will tend to get late slots when early slots run out)
                    slot_info = available_late_slots[0]

                if slot_info is None:
                    continue

                field_id = slot_info['field_id']
                game_datetime = slot_info['datetime']
                slot = slot_info['slot']

                # Balance home/away - prioritize per-pair alternation (a2), then overall balance
                actual_home, actual_away = home, away
                pair_key = (min(home.team_ID, away.team_ID), max(home.team_ID, away.team_ID))

                # Check per-pair history first
                pair_history = pair_home_history[pair_key]
                if pair_history:
                    # Alternate: if last home was team A, make team B home this time
                    last_home = pair_history[-1]
                    if last_home == home.team_ID:
                        actual_home, actual_away = away, home
                elif home_counts[home.team_ID] > away_counts[home.team_ID] + 1:
                    # No pair history - use overall balance
                    actual_home, actual_away = away, home

                is_early = game_datetime.hour < 18 if game_datetime else True

                game = ProposedGame(
                    game_type='regular',
                    league=config.league,
                    year=self.year,
                    is_spring=self.is_spring,
                    home_team=actual_home,
                    away_team=actual_away,
                    field=slot.field if slot else None,
                    game_date=game_datetime
                )
                game.slot = slot

                if existing_idx < len(records_to_fill):
                    existing_game = records_to_fill[existing_idx]
                    game.id = existing_game.ID
                    game.existing_record = existing_game
                    self._slot_assignments[existing_game.ID] = {
                        'game_id': existing_game.ID,
                        'home_id': actual_home.team_ID,
                        'away_id': actual_away.team_ID,
                        'game_date': game_datetime.isoformat() if game_datetime else None,
                        'field_id': field_id
                    }
                    existing_idx += 1
                else:
                    game.id = self._next_id
                    self._next_id += 1

                self.proposed_games.append(game)

                # Record the catch-up assignment
                self._record_decision(
                    date_str, config.league, slot,
                    'assigned', 'Catch-up scheduling (partial round)',
                    game_info={
                        'home': actual_home.display_name,
                        'away': actual_away.display_name,
                        'time': game_datetime.strftime('%I:%M %p') if game_datetime else 'N/A',
                        'phase': 'catch_up'
                    }
                )

                home_counts[actual_home.team_ID] += 1
                away_counts[actual_away.team_ID] += 1
                team_game_counts[home.team_ID] += 1
                team_game_counts[away.team_ID] += 1
                if is_early:
                    early_counts[actual_home.team_ID] += 1
                    early_counts[actual_away.team_ID] += 1
                else:
                    late_counts[actual_home.team_ID] += 1
                    late_counts[actual_away.team_ID] += 1

                if field_id and game_datetime:
                    self._add_field_time_usage(field_id, game_datetime, game_duration, config.league, is_practice=False)

                self._team_day_usage.add((home.team_ID, date_str))
                self._team_day_usage.add((away.team_ID, date_str))

                # Track pair game count for a1 compliance
                # Note: pair_key already calculated above for home/away balance
                pair_game_counts[pair_key] += 1

                # Track per-pair home history for a2 compliance
                pair_home_history[pair_key].append(actual_home.team_ID)

                # Track last scheduled pair for gap compliance
                last_scheduled_pair = pair_key

                # Update weekly game counter for P/G leagues
                if max_games_per_week and config.opening_day_date:
                    catch_up_week_num = self._get_week_number(game_date, config.opening_day_date)
                    self._team_week_games[(home.team_ID, catch_up_week_num)] += 1
                    self._team_week_games[(away.team_ID, catch_up_week_num)] += 1

                scheduled_matchups.add(idx)
                assigned = True
                break

            if not assigned:
                still_unscheduled.append(idx)
                # Debug: Why couldn't we assign this matchup?
                if config.league == 'BB A' and len(still_unscheduled) <= 3:
                    reasons = []
                    for game_date in sorted(slots_info_by_date.keys()):
                        date_str = game_date.isoformat()
                        home_busy = (home.team_ID, date_str) in self._team_day_usage
                        away_busy = (away.team_ID, date_str) in self._team_day_usage
                        slots_available = sum(1 for s in slots_info_by_date[game_date]
                                              if self._check_field_time_available(s['field_id'], s['datetime'], game_duration, config.league, is_practice=False)
                                              if s['field_id'] and s['datetime'])
                        if home_busy or away_busy or slots_available == 0:
                            if game_date.month == 10 and game_date.day >= 10:
                                reasons.append(f'{game_date.strftime("%b%d")}:{"H" if home_busy else ""}{"A" if away_busy else ""}{"S0" if slots_available==0 else ""}')
                    if reasons:
                        self.warnings.append({
                            'type': 'debug_bba_unassigned',
                            'message': f'BB A matchup {home.display_name} vs {away.display_name} unassigned. Oct dates: {", ".join(reasons[:5])}'
                        })

        unscheduled_matchups = still_unscheduled

        # Check for teams below minimum and report
        teams_below_min = []
        for team_id in sorted(all_team_ids):  # Sort for deterministic reporting
            count = team_game_counts[team_id]
            if count < games_per_team:
                # Get team name
                team = None
                for home, away in matchups:
                    if home.team_ID == team_id:
                        team = home
                        break
                    if away.team_ID == team_id:
                        team = away
                        break
                team_name = team.display_name if team else str(team_id)
                teams_below_min.append(f'{team_name} ({count}/{games_per_team})')

        if teams_below_min:
            # Find the last date that was actually used for this league
            scheduled_dates = set()
            for g in self.proposed_games:
                if g.league == config.league and g.game_type == 'regular' and g.game_date:
                    scheduled_dates.add(g.game_date.date() if hasattr(g.game_date, 'date') else g.game_date)

            last_scheduled = max(scheduled_dates) if scheduled_dates else None
            last_available = max(slots_info_by_date.keys()) if slots_info_by_date else None

            detail = f'{config.league}: Teams below minimum games: {", ".join(teams_below_min)}.'
            if last_scheduled and last_available and last_scheduled < last_available:
                detail += f' Last game scheduled: {last_scheduled.strftime("%b %d")}. Slots available through: {last_available.strftime("%b %d")}.'
                detail += f' Check if field slots have correct league assignments.'
            else:
                detail += ' Need more field slots or fewer constraints.'

            self.warnings.append({
                'type': 'insufficient_games',
                'message': detail
            })

        # Warn about unscheduled matchups
        if unscheduled_matchups:
            self.warnings.append({
                'type': 'insufficient_slots',
                'message': f'{config.league}: {len(unscheduled_matchups)} matchups could not be scheduled. Need more field slots.'
            })

    def _can_use_slot(self, slot, league, usage_type):
        """Check if a league can use a slot.

        Checks:
        1. Slot has a valid field
        2. Field allows the usage type (game vs practice)
        3. Slot league restriction (NULL = any league, otherwise must match)
        4. League's allowed fields list
        5. League's time restrictions
        """
        if not slot.field:
            return False

        field = slot.field

        # Check field usage type
        if usage_type == 'game' and not field.allows_games:
            return False
        if usage_type == 'practice' and not field.allows_practices:
            return False

        # Check slot league restriction
        # If slot.league is set, only that league can use it
        # If slot.league is NULL/empty, any league can use it
        if slot.league and league:
            if slot.league != league.display_name and slot.league != league.ID:
                # Slot is restricted to a different league
                return False

        # Check league field rules
        if league:
            if usage_type == 'game':
                if not league.can_play_at_field(field.ID, is_practice=False):
                    return False
            else:
                if not league.can_play_at_field(field.ID, is_practice=True):
                    return False

            # Check time restrictions
            if slot.start_time and not league.can_play_at_time(slot.start_time):
                return False

        return True

    def _get_slot_duration_minutes(self, slot):
        """Calculate the duration of a slot in minutes."""
        if not slot or not slot.start_time or not slot.end_time:
            return 0

        # Convert times to minutes since midnight
        start_minutes = slot.start_time.hour * 60 + slot.start_time.minute
        end_minutes = slot.end_time.hour * 60 + slot.end_time.minute

        # Handle case where end time might be past midnight (shouldn't happen but be safe)
        if end_minutes < start_minutes:
            end_minutes += 24 * 60

        return end_minutes - start_minutes

    def _get_time_based_game_capacity(self, slot, league=None):
        """Calculate how many games can fit in a slot based on duration.

        Uses league-specific game duration if set, otherwise defaults to 120 minutes.

        Args:
            slot: FieldSlot object
            league: Optional League object for league-specific duration
        """
        duration = self._get_slot_duration_minutes(slot)
        if duration <= 0:
            return 1  # Default to 1 if we can't calculate

        # Get league-specific duration or default
        game_duration = GAME_DURATION_MINUTES
        if league:
            game_duration = league.get_game_duration(is_no_time_limit=False)

        return duration // game_duration

    def _get_time_based_practice_capacity(self, slot, league=None):
        """Calculate how many sequential practices can fit in a slot based on duration.

        Uses league-specific practice duration if set, otherwise defaults to 90 minutes.

        Args:
            slot: FieldSlot object
            league: Optional League object for league-specific duration
        """
        duration = self._get_slot_duration_minutes(slot)
        if duration <= 0:
            return 1  # Default to 1 if we can't calculate

        # Get league-specific duration or default
        practice_duration = PRACTICE_DURATION_MINUTES
        if league:
            practice_duration = league.get_practice_duration()

        return duration // practice_duration

    def _get_slot_capacity(self, slot, game_date, usage_type='practice', league=None):
        """Get capacity for a slot based on time and field settings.

        For games: Returns how many games can fit (based on league's game duration)
        For practices: Returns how many teams can practice simultaneously,
                       limited by both time and field's practice_capacity setting

        Args:
            slot: FieldSlot object
            game_date: The date for the activity
            usage_type: 'game' or 'practice'
            league: Optional League object for league-specific durations
        """
        if not slot or not slot.field:
            return 1

        if usage_type == 'game':
            # Games run sequentially - capacity based on time only
            return self._get_time_based_game_capacity(slot, league)

        # For practices, consider both time-based capacity and field sharing capacity
        # Time-based: how many sequential time slots fit
        time_capacity = self._get_time_based_practice_capacity(slot, league)

        # Field sharing: how many teams can practice at the same time
        is_late = slot.start_time and slot.start_time.hour >= 19
        sharing_capacity = slot.field.get_practice_capacity(is_late_slot=is_late)

        # Total capacity is time slots × sharing capacity
        # e.g., 4-hour slot with 2 practice time slots and field capacity of 2
        # = 2 time slots × 2 teams per slot = 4 teams total
        return time_capacity * sharing_capacity

    def _slot_to_datetime(self, slot, target_date):
        """Convert a slot to a datetime on the target date."""
        if not slot or not slot.start_time:
            return None
        return datetime.combine(target_date, slot.start_time)

    def _get_week_number(self, target_date, reference_date=None):
        """Get week number relative to a reference date (usually opening day).

        Uses ISO week if no reference date provided.
        For P/G league scheduling, use opening_day as reference to track weekly limits.
        """
        if reference_date:
            # Week 1 starts on reference_date
            delta = (target_date - reference_date).days
            return delta // 7
        else:
            # Use ISO week number
            return target_date.isocalendar()[1]

    def _get_late_need_score(self, team_ids, late_counts):
        """Calculate how much a matchup needs a late slot.

        Returns a LOWER score if teams need late slots (have fewer late games).
        Teams with fewer late games should get priority for late slots.
        """
        total_late = 0
        for team_id in team_ids:
            total_late += late_counts.get(team_id, 0)
        return total_late  # Lower = needs late slot more

    def _get_dates_for_days(self, start_date, day_numbers, count_needed, end_date=None):
        """Get dates that fall on specified days of week.

        Args:
            start_date: First possible date
            day_numbers: List of weekday numbers (0=Mon, 6=Sun)
            count_needed: Maximum number of dates to return
            end_date: Optional hard stop date (won't return dates after this)

        Returns:
            List of dates
        """
        dates = []
        current = start_date
        max_weeks = 20  # Safety limit

        while len(dates) < count_needed and (current - start_date).days < max_weeks * 7:
            # Stop if we've passed the end date
            if end_date and current > end_date:
                break

            if current.weekday() in day_numbers:
                # Skip season blackout dates
                if not self._is_blackout_date(current):
                    dates.append(current)
            current += timedelta(days=1)

        return dates

    def _group_slots_by_date(self, all_slots, dates, league, usage_type):
        """Group available slots by date, sorted by field preference.

        Fields are ordered:
        1. Fields in league's preferred_fields list (in order)
        2. Other allowed fields (lowest priority)
        """
        result = {}

        # Get preferred field IDs for this league (as list of integers)
        preferred_ids = []
        if league and hasattr(league, 'preferred_field_ids'):
            preferred_ids = league.preferred_field_ids or []

        def slot_preference_key(slot):
            """Sort key: preferred fields first (in order), then others."""
            if not slot.field:
                return (999999,)  # No field = lowest priority

            field_id = slot.field.ID
            if field_id in preferred_ids:
                # Preferred field - use its position in the list
                return (preferred_ids.index(field_id),)
            else:
                # Non-preferred but allowed field - after all preferred
                return (len(preferred_ids) + 1, field_id)

        for target_date in dates:
            day_of_week = target_date.weekday()
            day_slots = [
                s for s in all_slots
                if s.day_of_week == day_of_week
                and self._can_use_slot(s, league, usage_type)
                and (not s.field or self._is_field_available_on_date(s.field.ID, target_date))  # Check field availability (cached)
            ]
            if day_slots:
                # Sort by preference
                day_slots.sort(key=slot_preference_key)
                result[target_date] = day_slots

        return result

    def _record_decision(self, date_str, league, slot, decision, reason, game_info=None):
        """Record a slot assignment decision for tracing."""
        self._slot_decisions.append(SlotDecision(
            date_str=date_str,
            league=league,
            slot=slot,
            decision=decision,
            reason=reason,
            game_info=game_info
        ))

    def _build_result(self):
        """Build the result dictionary."""
        # Group slot decisions by date for easier lookup
        decisions_by_date = {}
        for d in self._slot_decisions:
            if d.date_str not in decisions_by_date:
                decisions_by_date[d.date_str] = []
            decisions_by_date[d.date_str].append(d.to_dict())

        return {
            'games': [g.to_dict() for g in self.proposed_games],
            'violations': [v.to_dict() for v in self.violations],
            'warnings': self.warnings,
            'assignments': self._slot_assignments,  # Maps existing game IDs to proposed values
            'slot_decisions': decisions_by_date,  # Detailed trace by date
            'summary': {
                'total_games': len([g for g in self.proposed_games if g.game_type in ('regular', 'playoff')]),
                'total_practices': len([g for g in self.proposed_games if g.game_type == 'practice']),
                'total_scrimmages': len([g for g in self.proposed_games if g.game_type == 'scrimmage']),
                'hard_violations': len([v for v in self.violations if v.severity == ScheduleViolation.HARD]),
                'soft_violations': len([v for v in self.violations if v.severity == ScheduleViolation.SOFT]),
                'existing_games_updated': len(self._slot_assignments)
            }
        }
