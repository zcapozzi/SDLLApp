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

from datetime import date, datetime, timedelta
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
            'home_team_name': self.home_team.display_name if self.home_team else None,
            'away_team_id': self.away_team.team_ID if self.away_team else None,
            'away_team_name': self.away_team.display_name if self.away_team else None,
            'field_id': self.field.ID if self.field else None,
            'field_name': self.field.location_title if self.field else None,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'is_scrimmage': self.is_scrimmage,
            'slot_id': self.slot.slot_ID if self.slot else None
        }


class ScheduleValidator:
    """Validates schedules against hard and soft rules."""

    def __init__(self, year, is_spring):
        self.year = year
        self.is_spring = is_spring
        self.violations = []
        self._team_names = {}  # Cache: team_id -> team_name
        self._league_configs = {}  # Cache: league_name -> LeagueSeason config

    def _get_team_name(self, team_id):
        """Get team name from ID (with caching)."""
        if team_id is None:
            return None
        if team_id not in self._team_names:
            # Try to look up from database
            from app.models.team import TeamSeason
            team = TeamSeason.query.filter_by(team_ID=team_id).first()
            if team:
                self._team_names[team_id] = team.computed_display_name or team.display_name or str(team_id)
            else:
                self._team_names[team_id] = str(team_id)
        return self._team_names[team_id]

    def _build_team_info(self, team_id):
        """Build team info dict for violation."""
        return {'id': team_id, 'name': self._get_team_name(team_id)}

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
                    name = getattr(team, 'computed_display_name', None) or getattr(team, 'display_name', None) or str(team_id)
                    self._team_names[team_id] = name
            if hasattr(g, 'away_team') and g.away_team:
                team = g.away_team
                team_id = team.team_ID if hasattr(team, 'team_ID') else None
                if team_id:
                    name = getattr(team, 'computed_display_name', None) or getattr(team, 'display_name', None) or str(team_id)
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

    def _check_matchup_balance(self, league, games, teams):
        """Rule a1: Play everyone at least once, max 1 game difference."""
        matchup_counts = defaultdict(int)

        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home and away:
                key = tuple(sorted([home, away]))
                matchup_counts[key] += 1

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
            self.violations.append(ScheduleViolation(
                'a1', 'Play everyone at least once',
                ScheduleViolation.HARD,
                f'{league}: {len(unplayed_pairs)} team pairs have not played each other'
            ))

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
        """Rule b2: Balance early vs late start times per team.

        Only games starting at 4pm or later count toward this balance:
        - Early: 4:00 PM to before 6:00 PM
        - Late: 6:00 PM or later
        - Games before 4pm: not counted
        """
        early_counts = defaultdict(int)  # 4:00 PM to before 6:00 PM
        late_counts = defaultdict(int)   # 6:00 PM or later

        for g in games:
            start_time = self._get_start_time(g)
            if start_time is None:
                continue

            # Only count games starting at 4pm or later
            if start_time < 16:
                continue

            home = self._get_home_team(g)
            away = self._get_away_team(g)

            if start_time < 18:  # 4pm to before 6pm = early
                if home:
                    early_counts[home] += 1
                if away:
                    early_counts[away] += 1
            else:  # 6pm or later = late
                if home:
                    late_counts[home] += 1
                if away:
                    late_counts[away] += 1

        for team_id in teams:
            early = early_counts.get(team_id, 0)
            late = late_counts.get(team_id, 0)
            total = early + late
            if total > 0:
                diff = abs(early - late)
                # Allow some imbalance, but flag if more than 2 difference
                if diff > 2:
                    team_name = self._get_team_name(team_id)
                    self.violations.append(ScheduleViolation(
                        'b2', 'Early/late time balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team_name} has {early} early games and {late} late games',
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

    def _check_same_team_gap(self, league, games, teams):
        """Check that same teams don't play back-to-back."""
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
                            ScheduleViolation.HARD,
                            f'{league}: {home_name} vs {away_name} play back-to-back without a game gap',
                            teams=[self._build_team_info(home), self._build_team_info(away)]
                        ))
                last_matchup[key] = i

    def _check_field_conflicts(self, games):
        """Check for games scheduled at the same time on the same field.

        Rule: No two games can be at the same time on the same field.
        Note: Sequential games (e.g., 5:30 and 7:30) on the same field are OK.
        """
        # Group games by (field, exact datetime)
        field_time_slots = defaultdict(list)

        for game in games:
            game_date = self._get_game_date(game)
            if not game_date:
                continue

            # Get field
            field = None
            if hasattr(game, 'field') and game.field:
                field = game.field.ID if hasattr(game.field, 'ID') else game.field
            elif hasattr(game, 'location'):
                field = game.location

            if not field:
                continue

            # Skip practices - multiple teams can share a field at the same time
            if self._is_practice(game):
                continue

            # Key: (field, date, hour, minute) - exact time slot
            key = (field, game_date.date(), game_date.hour, game_date.minute)
            field_time_slots[key].append(game)

        # Check for conflicts
        for key, games_at_slot in field_time_slots.items():
            if len(games_at_slot) > 1:
                field, date, hour, minute = key
                time_str = f'{hour:02d}:{minute:02d}'
                self.violations.append(ScheduleViolation(
                    'slot', 'Field double-booked',
                    ScheduleViolation.HARD,
                    f'Field {field} has {len(games_at_slot)} games at {date} {time_str}',
                    games=games_at_slot
                ))

    def _check_practice_field_capacity(self, games):
        """Check practice field capacity limits.

        Rule f1: Practice field capacity - enforces each field's practice_capacity
        setting from the database. If not set, defaults to 1.
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

        # Check for capacity violations
        for key, practices_at_slot in practices_by_slot.items():
            field_id, field_name, field_obj, date, hour, minute = key

            # Get field's practice_capacity from DB (defaults to 1 if not set)
            if field_obj and hasattr(field_obj, 'get_practice_capacity'):
                is_late = hour >= 19
                field_capacity = field_obj.get_practice_capacity(is_late_slot=is_late)
            else:
                field_capacity = 1  # Default if no field object

            if len(practices_at_slot) > field_capacity:
                time_str = f'{hour:02d}:{minute:02d}'

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
        """
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
            if teams_sitting and teams_playing:
                # Only flag if some teams ARE playing (not an empty date)
                # and not ALL teams are sitting (which would mean no games that day)
                sitting_names = [self._get_team_name(t) for t in teams_sitting]
                self.violations.append(ScheduleViolation(
                    'e2', 'Game day balance',
                    ScheduleViolation.SOFT,
                    f'{league}: On {date_str}, {len(teams_sitting)} team(s) not playing: {", ".join(sitting_names)}',
                    teams=[self._build_team_info(t) for t in teams_sitting]
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
        self._global_field_time_usage = set()  # Tracks (field_id, datetime) across all leagues
        self._team_day_usage = set()  # Tracks (team_id, date_str) - one activity per team per day
        self._slot_decisions = []  # Detailed decision log for tracing
        self._practice_slot_counts = defaultdict(int)  # Tracks practice count per (field_id, datetime) - f1 rule

    def generate(self, start_fresh=False):
        """Generate a complete proposed schedule.

        This fills in existing game slots with matchups, dates, and fields.
        Does NOT create new game records - those should exist already.

        Args:
            start_fresh: If True, treats all slots as unassigned (ignores existing assignments)

        Returns:
            dict with 'games', 'violations', 'warnings', 'assignments'
        """
        self.proposed_games = []
        self.violations = []
        self.warnings = []
        self._slot_assignments = {}
        # Global tracker for field/time usage across all leagues
        # Key: (field_id, datetime_isoformat) - prevents double-booking
        self._global_field_time_usage = set()
        # Global tracker for team-day usage (one game/practice per team per day)
        # Key: (team_id, date_str) - prevents multiple activities on same day
        self._team_day_usage = set()

        # Validate prerequisites
        if not self._validate_prerequisites():
            return self._build_result()

        # Get league configurations
        league_configs = LeagueSeason.get_by_season(self.year, self.is_spring)

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
        phase1_game_count = 0
        for config in league_configs:
            before = len(self.proposed_games)
            self._generate_games_only(config, start_fresh)
            after = len(self.proposed_games)
            games_added = after - before
            phase1_game_count += games_added

        # Phase 2: Schedule all practices for all leagues
        phase2_practice_count = 0
        for config in league_configs:
            before = len(self.proposed_games)
            self._generate_practices_only(config, start_fresh)
            after = len(self.proposed_games)
            practices_added = after - before
            phase2_practice_count += practices_added

        # Debug: Report phase results
        self.warnings.append({
            'type': 'debug_phases',
            'message': f'Phase 1 (games/scrimmages): {phase1_game_count} scheduled. Phase 2 (practices): {phase2_practice_count} scheduled. Field slots used after Phase 1: {len(self._global_field_time_usage)}.'
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

        # Validate the generated schedule
        validator = ScheduleValidator(self.year, self.is_spring)
        self.violations = validator.validate(self.proposed_games)

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

        # Get teams for this league
        teams = TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1,
            is_placeholder=0
        ).all()

        if len(teams) < 2:
            self.warnings.append({
                'type': 'insufficient_teams',
                'message': f'{league_name}: Need at least 2 teams to schedule.'
            })
            return

        # Get league object for field rules
        league = League.get_by_name(league_name)

        # Get available field slots
        all_slots = FieldSlot.get_by_season(self.year, self.is_spring)

        # Get existing game slots for this league
        existing_games = Game.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1
        ).all()

        # Separate by type
        regular_slots = [g for g in existing_games if g.game_type == 'regular']

        # If start_fresh, treat all as unassigned
        if start_fresh:
            for game in existing_games:
                game._temp_clear = True

        # Generate scrimmages (last day before opening)
        if config.first_practice_date and config.opening_day_date:
            scrimmage_date = config.opening_day_date - timedelta(days=1)
            # Find last activity day before opening
            practice_days = config.practice_days or []
            game_days = config.game_days or []
            all_activity_days = set(practice_days + game_days)
            current = scrimmage_date
            while current >= config.first_practice_date:
                if current.weekday() in all_activity_days:
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

        # Get teams for this league
        teams = TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1,
            is_placeholder=0
        ).all()

        if len(teams) < 2:
            return  # Warning already issued in games phase

        # Get league object for field rules
        league = League.get_by_name(league_name)

        # Get available field slots
        all_slots = FieldSlot.get_by_season(self.year, self.is_spring)

        # Get existing practice slots for this league
        existing_games = Game.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1
        ).all()
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
                    self._assign_practices_for_date(config, teams, league, all_slots, current_date, practice_slots, start_fresh)
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

        # Get teams for this league
        teams = TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1,
            is_placeholder=0
        ).all()

        if len(teams) < 2:
            self.warnings.append({
                'type': 'insufficient_teams',
                'message': f'{league_name}: Need at least 2 teams to schedule.'
            })
            return

        # Get league object for field rules
        league = League.get_by_name(league_name)

        # Get available field slots
        all_slots = FieldSlot.get_by_season(self.year, self.is_spring)

        # Get existing game slots for this league
        existing_games = Game.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=league_name,
            active=1
        ).all()

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

        # Get P and G days for this league
        practice_days = config.practice_days  # List of day numbers
        game_days = config.game_days
        all_activity_days = set(practice_days + game_days)

        # Get dates from first practice to day before opening
        current_date = config.first_practice_date
        end_date = config.opening_day_date - timedelta(days=1)

        activity_dates = []
        while current_date <= end_date:
            if current_date.weekday() in all_activity_days:
                activity_dates.append(current_date)
            current_date += timedelta(days=1)

        if not activity_dates:
            return

        # Last activity date becomes scrimmage day
        scrimmage_date = activity_dates[-1]
        practice_dates = activity_dates[:-1]

        # Generate practices for each date (except scrimmage day)
        for practice_date in practice_dates:
            self._assign_practices_for_date(config, teams, league, all_slots, practice_date, practice_slots, start_fresh)

        # Generate scrimmages on scrimmage day
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
        self._assign_games_to_slots(config, matchups, slots_by_date, league, existing_slots, start_fresh)

    def _generate_post_opening_practices(self, config, teams, league, all_slots, practice_slots=None, start_fresh=False):
        """Generate practices after opening day (on P days only).

        Practices are scheduled from opening_day_date through regular_season_end_date.
        """
        if not config.opening_day_date:
            return

        practice_days = config.practice_days
        if not practice_days:
            return

        # Use regular_season_end_date if set, otherwise default to 12 weeks
        if config.regular_season_end_date:
            end_date = config.regular_season_end_date
        else:
            end_date = config.opening_day_date + timedelta(weeks=12)

        current_date = config.opening_day_date

        while current_date <= end_date:
            if current_date.weekday() in practice_days:
                self._assign_practices_for_date(config, teams, league, all_slots, current_date, practice_slots, start_fresh)
            current_date += timedelta(days=1)

    def _generate_round_robin(self, teams, games_per_team):
        """Generate round-robin matchups ensuring BALANCED team appearances.

        Each team should have exactly games_per_team appearances in the matchups.

        Returns list of (home_team, away_team) tuples.
        """
        n = len(teams)
        total_games_needed = (games_per_team * n) // 2

        # Calculate how many times each pair should play (use ceiling to generate enough)
        games_per_pair = max(1, -(-games_per_team // (n - 1)))  # Ceiling division

        # Generate base round-robin matchups
        all_matchups = []
        for round_num in range(games_per_pair):
            for i in range(n):
                for j in range(i + 1, n):
                    # Alternate home/away each round
                    if (round_num + i + j) % 2 == 0:
                        all_matchups.append((teams[i], teams[j]))
                    else:
                        all_matchups.append((teams[j], teams[i]))

        # Shuffle to avoid predictable patterns
        random.shuffle(all_matchups)

        # Select matchups while maintaining balance
        # Use priority-based selection: prioritize matchups involving teams that need more games
        team_counts = {t.team_ID: 0 for t in teams}
        selected = []
        available = list(all_matchups)  # Copy so we can remove as we select

        while len(selected) < total_games_needed and available:
            # Find the matchup that most helps teams below their target
            best_matchup = None
            best_priority = -1
            best_idx = -1

            for idx, (home, away) in enumerate(available):
                # Skip if either team already has enough games
                if team_counts[home.team_ID] >= games_per_team or team_counts[away.team_ID] >= games_per_team:
                    continue

                # Priority = how many games both teams still need (higher = more needed)
                home_needs = games_per_team - team_counts[home.team_ID]
                away_needs = games_per_team - team_counts[away.team_ID]
                priority = home_needs + away_needs

                if priority > best_priority:
                    best_priority = priority
                    best_matchup = (home, away)
                    best_idx = idx

            if best_matchup is None:
                # No valid matchups left (all remaining matchups have at least one team with enough games)
                break

            # Select this matchup
            home, away = best_matchup
            selected.append(best_matchup)
            team_counts[home.team_ID] += 1
            team_counts[away.team_ID] += 1
            available.pop(best_idx)

        return selected

    def _find_complete_round(self, eligible_matchups, available_slots, games_needed, all_team_ids):
        """Find a combination of matchups that covers all teams.

        Uses backtracking to find games_needed matchups where all teams play exactly once.

        Args:
            eligible_matchups: List of (idx, priority, home, away) tuples
            available_slots: List of slot_info dicts
            games_needed: Number of games to schedule (n_teams / 2)
            all_team_ids: Set of all team IDs that must be covered

        Returns:
            List of (idx, home, away, slot_info) tuples, or None if no valid combination
        """
        if len(available_slots) < games_needed:
            return None

        # Try to find a combination using backtracking
        def backtrack(selected, teams_used, slot_idx):
            if len(selected) == games_needed:
                # Found a valid combination
                return selected.copy()

            for idx, priority, home, away in eligible_matchups:
                # Skip if either team already used
                if home.team_ID in teams_used or away.team_ID in teams_used:
                    continue

                # Skip if this matchup was already selected
                if any(s[0] == idx for s in selected):
                    continue

                # Try adding this matchup
                selected.append((idx, home, away, available_slots[slot_idx]))
                teams_used.add(home.team_ID)
                teams_used.add(away.team_ID)

                result = backtrack(selected, teams_used, slot_idx + 1)
                if result is not None:
                    return result

                # Backtrack
                selected.pop()
                teams_used.remove(home.team_ID)
                teams_used.remove(away.team_ID)

            return None

        return backtrack([], set(), 0)

    def _generate_scrimmages(self, config, teams, league, all_slots, scrimmage_date):
        """Generate scrimmages - one per team, random pairing.

        Scrimmages are treated like games for time-based scheduling (2 hours each).
        """
        # Shuffle teams and pair them up
        shuffled = list(teams)
        random.shuffle(shuffled)

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

                    # Check global usage
                    if field_id and test_datetime:
                        usage_key = (field_id, test_datetime.isoformat())
                        if usage_key in self._global_field_time_usage:
                            continue  # Already used by another league

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

            # Mark as used globally
            field_id = assigned_slot.field.ID if assigned_slot and assigned_slot.field else None
            if field_id and game_datetime:
                self._global_field_time_usage.add((field_id, game_datetime.isoformat()))

            # Mark both teams as having activity on this day
            self._team_day_usage.add((home.team_ID, date_str))
            self._team_day_usage.add((away.team_ID, date_str))

        # Handle odd team out (no scrimmage partner)
        if len(shuffled) % 2 == 1:
            self.warnings.append({
                'type': 'odd_team',
                'message': f'{config.league}: Odd number of teams - {shuffled[-1].display_name} has no scrimmage partner.'
            })

    def _assign_practices_for_date(self, config, teams, league, all_slots, practice_date, existing_slots=None, start_fresh=False):
        """Assign practices for all teams on a given date."""
        day_of_week = practice_date.weekday()

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
            time_capacity = self._get_time_based_practice_capacity(slot)

            for time_block in range(time_capacity):
                time_offset_minutes = time_block * PRACTICE_DURATION_MINUTES
                game_datetime = self._slot_to_datetime(slot, practice_date)
                if game_datetime and time_offset_minutes > 0:
                    game_datetime = game_datetime + timedelta(minutes=time_offset_minutes)

                if game_datetime:
                    # Get field's practice capacity from DB, considering late slots
                    is_late = game_datetime.hour >= 19
                    field_capacity = slot.field.get_practice_capacity(is_late_slot=is_late)

                    practice_options.append({
                        'slot': slot,
                        'field_id': field_id,
                        'datetime': game_datetime,
                        'datetime_key': (field_id, game_datetime.isoformat()),
                        'field_capacity': field_capacity
                    })

        for team in teams:
            # Check if team already has activity on this day
            team_day_key = (team.team_ID, date_str)
            if team_day_key in self._team_day_usage:
                # Team already has a game or practice today, skip
                continue

            # Find best slot with available capacity (respects field's practice_capacity from DB)
            assigned_option = None
            for option in practice_options:
                datetime_key = option['datetime_key']
                current_count = self._practice_slot_counts[datetime_key]
                field_capacity = option['field_capacity']
                if current_count < field_capacity:
                    assigned_option = option
                    break

            if not assigned_option:
                # All practice slots at capacity, skip this team's practice
                self.warnings.append({
                    'type': 'practice_capacity',
                    'message': f'{config.league}: No practice slot available for {team.display_name} on {practice_date} (all slots at capacity)'
                })
                continue

            # Increment the global practice count for this field/time
            self._practice_slot_counts[assigned_option['datetime_key']] += 1

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

    def _assign_games_to_slots(self, config, matchups, slots_by_date, league, existing_game_records=None, start_fresh=False):
        """Assign game matchups to available slots.

        Scheduling strategy:
        - Schedule by DATE to ensure all teams play on the same game days
        - For each date, schedule n/2 games (where n = team count) so all teams play
        - Only use a date if we have enough slot capacity for all teams
        - Prioritizes teams with fewer scheduled games when selecting matchups

        Time-based scheduling:
        - Each game is 2 hours (120 minutes)
        - A 4-hour slot can hold 2 sequential games
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

            # Filter out slots already used by other leagues
            available_date_slots = []
            used_by_other_league = []
            for slot_info in date_slots:
                field_id = slot_info['field_id']
                game_datetime = slot_info['datetime']
                if field_id and game_datetime:
                    usage_key = (field_id, game_datetime.isoformat())
                    if usage_key not in self._global_field_time_usage:
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
            if len(available_date_slots) < games_per_date:
                # Not enough capacity - skip this date for full rounds
                # Record why we skipped this date
                for slot_info in available_date_slots:
                    self._record_decision(
                        date_str, config.league, slot_info['slot'],
                        'skipped', f'Insufficient capacity for full round (need {games_per_date} slots, have {len(available_date_slots)}). Will retry in catch-up pass.',
                        game_info=None
                    )
                continue

            # Find teams that need more games and don't have activity on this day
            available_teams = set()
            unavailable_teams = []
            for team_id in all_team_ids:
                team_day_key = (team_id, date_str)
                if team_day_key not in self._team_day_usage:
                    if team_game_counts[team_id] < games_per_team:
                        available_teams.add(team_id)
                    else:
                        unavailable_teams.append(f'Team {team_id} has enough games')
                else:
                    unavailable_teams.append(f'Team {team_id} already has activity')

            # If not all teams are available, skip this date for a full round
            if len(available_teams) < num_teams:
                for slot_info in available_date_slots:
                    self._record_decision(
                        date_str, config.league, slot_info['slot'],
                        'skipped', f'Not all teams available ({len(available_teams)}/{num_teams}). Will retry in catch-up pass.',
                        game_info={'unavailable': unavailable_teams[:3]}
                    )
                continue

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
                    eligible_matchups.append((idx, home_needs + away_needs, home, away))

            # Sort by priority (most needed first)
            eligible_matchups.sort(key=lambda x: -x[1])

            # Try to find a COMPLETE round (all teams play)
            # Use backtracking to find a valid combination of matchups
            matchups_for_today = self._find_complete_round(
                eligible_matchups, available_date_slots, games_per_date, all_team_ids
            )

            # Only proceed if we found a complete round
            if matchups_for_today is None:
                # Can't schedule a complete round - skip this date
                for slot_info in available_date_slots[:games_per_date]:
                    self._record_decision(
                        date_str, config.league, slot_info['slot'],
                        'skipped', f'Could not form complete round (need {games_per_date} non-overlapping matchups)',
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

                # Balance home/away
                actual_home, actual_away = home, away
                if home_counts[home.team_ID] > away_counts[home.team_ID] + 1:
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

                # Mark field/time as used globally
                if field_id and game_datetime:
                    self._global_field_time_usage.add((field_id, game_datetime.isoformat()))

                # Mark teams as having activity on this day
                self._team_day_usage.add((home.team_ID, date_str))
                self._team_day_usage.add((away.team_ID, date_str))

                scheduled_matchups.add(idx)
                unscheduled_matchups = [m for m in unscheduled_matchups if m != idx]

        # Second pass: Fill remaining games (catch-up for teams below minimum)
        # This may result in some e2 violations but ensures e1 (minimum games) is met

        # Debug: For BB A, show catch-up status
        if config.league == 'BB A':
            remaining = len([m for m in unscheduled_matchups if m not in scheduled_matchups])
            self.warnings.append({
                'type': 'debug_bba_catchup',
                'message': f'BB A catch-up starting: {remaining} matchups remaining, {len(slots_info_by_date)} dates with slots'
            })

        still_unscheduled = []
        for idx in unscheduled_matchups:
            if idx in scheduled_matchups:
                continue

            home, away = matchups[idx]

            # Check if both teams already have enough games
            if team_game_counts[home.team_ID] >= games_per_team and team_game_counts[away.team_ID] >= games_per_team:
                scheduled_matchups.add(idx)
                continue

            # Find any available slot
            assigned = False
            for game_date in sorted(slots_info_by_date.keys()):
                if assigned:
                    break
                date_str = game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date)

                # Check if teams already have activity on this day
                home_day_key = (home.team_ID, date_str)
                away_day_key = (away.team_ID, date_str)
                if home_day_key in self._team_day_usage or away_day_key in self._team_day_usage:
                    continue

                for slot_info in slots_info_by_date[game_date]:
                    field_id = slot_info['field_id']
                    game_datetime = slot_info['datetime']

                    # Check if slot is available
                    if field_id and game_datetime:
                        usage_key = (field_id, game_datetime.isoformat())
                        if usage_key in self._global_field_time_usage:
                            continue

                    slot = slot_info['slot']

                    # Balance home/away
                    actual_home, actual_away = home, away
                    if home_counts[home.team_ID] > away_counts[home.team_ID] + 1:
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
                        self._global_field_time_usage.add((field_id, game_datetime.isoformat()))

                    self._team_day_usage.add((home.team_ID, date_str))
                    self._team_day_usage.add((away.team_ID, date_str))

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
                                              if (s['field_id'], s['datetime'].isoformat()) not in self._global_field_time_usage
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
        for team_id in all_team_ids:
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
                if s.day_of_week == day_of_week and self._can_use_slot(s, league, usage_type)
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
