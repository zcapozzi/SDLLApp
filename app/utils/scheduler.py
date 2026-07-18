"""Schedule generator and validator for SDLL games, practices, and scrimmages."""

from datetime import date, datetime, timedelta
from collections import defaultdict
import random
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

    def __init__(self, rule_code, rule_name, severity, message, games=None):
        self.rule_code = rule_code
        self.rule_name = rule_name
        self.severity = severity
        self.message = message
        self.games = games or []

    def to_dict(self):
        return {
            'rule_code': self.rule_code,
            'rule_name': self.rule_name,
            'severity': self.severity,
            'message': self.message,
            'game_ids': [g.ID if hasattr(g, 'ID') else g.get('id') for g in self.games]
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

    def validate(self, games):
        """Validate a list of games/proposed games.

        Args:
            games: List of Game or ProposedGame objects

        Returns:
            List of ScheduleViolation objects
        """
        self.violations = []

        # Group games by league
        games_by_league = defaultdict(list)
        for g in games:
            if hasattr(g, 'league') and g.league:
                games_by_league[g.league].append(g)

        for league, league_games in games_by_league.items():
            self._validate_league(league, league_games)

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

        # Rule b2: Balance 5:30 vs 7:30 per team
        self._check_time_balance(league, actual_games, teams)

        # Rule c2: Balance practice fields
        practices = [g for g in games if self._is_practice(g)]
        if practices:
            self._check_practice_field_balance(league, practices, teams)

        # Check no back-to-back against same team
        self._check_same_team_gap(league, actual_games, teams)

    def _is_actual_game(self, game):
        """Check if this is an actual game (not practice)."""
        if hasattr(game, 'game_type'):
            return game.game_type in ('regular', 'playoff', 'scrimmage')
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

        for team in teams:
            home = home_counts.get(team, 0)
            away = away_counts.get(team, 0)
            diff = abs(home - away)
            if diff > 1:
                self.violations.append(ScheduleViolation(
                    'b1', 'Home/away balance',
                    ScheduleViolation.HARD,
                    f'{league}: Team {team} has {home} home games and {away} away games (diff: {diff})'
                ))

    def _check_home_away_vs_opponent(self, league, games, teams):
        """Rule a2: No team home twice vs same opponent."""
        home_vs_opponent = defaultdict(lambda: defaultdict(int))

        for g in games:
            home = self._get_home_team(g)
            away = self._get_away_team(g)
            if home and away:
                home_vs_opponent[home][away] += 1

        for team, opponents in home_vs_opponent.items():
            for opponent, home_count in opponents.items():
                away_count = home_vs_opponent.get(opponent, {}).get(team, 0)
                if home_count >= 2 and away_count == 0:
                    self.violations.append(ScheduleViolation(
                        'a2', 'Home/away vs opponent',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team} is home {home_count}x vs {opponent} but never away'
                    ))

    def _check_time_balance(self, league, games, teams):
        """Rule b2: Balance 5:30 vs 7:30 start times per team."""
        early_counts = defaultdict(int)  # Before 6:00 PM
        late_counts = defaultdict(int)   # 6:00 PM or later

        for g in games:
            start_time = self._get_start_time(g)
            if start_time is None:
                continue

            home = self._get_home_team(g)
            away = self._get_away_team(g)

            if start_time < 18:  # Before 6 PM
                if home:
                    early_counts[home] += 1
                if away:
                    early_counts[away] += 1
            else:
                if home:
                    late_counts[home] += 1
                if away:
                    late_counts[away] += 1

        for team in teams:
            early = early_counts.get(team, 0)
            late = late_counts.get(team, 0)
            total = early + late
            if total > 0:
                diff = abs(early - late)
                # Allow some imbalance, but flag if more than 2 difference
                if diff > 2:
                    self.violations.append(ScheduleViolation(
                        'b2', 'Early/late time balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team} has {early} early games and {late} late games'
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
        for team in teams:
            counts = field_counts.get(team, {})
            if len(counts) > 1:
                values = list(counts.values())
                if max(values) - min(values) > 2:
                    self.violations.append(ScheduleViolation(
                        'c2', 'Practice field balance',
                        ScheduleViolation.SOFT,
                        f'{league}: Team {team} has uneven practice field distribution'
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
                        self.violations.append(ScheduleViolation(
                            'gap', 'Same team gap',
                            ScheduleViolation.HARD,
                            f'{league}: Teams play back-to-back without a game gap'
                        ))
                last_matchup[key] = i


class ScheduleGenerator:
    """Generates proposed schedules for a season."""

    def __init__(self, year, is_spring):
        self.year = year
        self.is_spring = is_spring
        self.proposed_games = []
        self.violations = []
        self.warnings = []
        self._next_id = 1

    def generate(self):
        """Generate a complete proposed schedule.

        Returns:
            dict with 'games', 'violations', 'warnings'
        """
        self.proposed_games = []
        self.violations = []
        self.warnings = []

        # Validate prerequisites
        if not self._validate_prerequisites():
            return self._build_result()

        # Get league configurations
        league_configs = LeagueSeason.get_by_season(self.year, self.is_spring)

        for config in league_configs:
            self._generate_for_league(config)

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

    def _generate_for_league(self, config):
        """Generate schedule for a single league."""
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

        # Phase 1: Pre-opening day (practices and scrimmages)
        self._generate_pre_opening(config, teams, league, all_slots)

        # Phase 2: Games (opening day onwards)
        self._generate_games(config, teams, league, all_slots)

        # Phase 3: Post-opening day practices
        self._generate_post_opening_practices(config, teams, league, all_slots)

    def _generate_pre_opening(self, config, teams, league, all_slots):
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
            self._assign_practices_for_date(config, teams, league, all_slots, practice_date)

        # Generate scrimmages on scrimmage day
        self._generate_scrimmages(config, teams, league, all_slots, scrimmage_date)

    def _generate_games(self, config, teams, league, all_slots):
        """Generate regular season games from opening day onwards."""
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

        # Generate round-robin matchups
        matchups = self._generate_round_robin(teams, games_per_team)

        # Get game dates from opening day
        game_dates = self._get_dates_for_days(
            config.opening_day_date,
            game_days,
            len(matchups)  # Estimate needed dates
        )

        # Get available slots for each date
        slots_by_date = self._group_slots_by_date(all_slots, game_dates, league, 'game')

        # Assign games to slots
        self._assign_games_to_slots(config, matchups, slots_by_date, league)

    def _generate_post_opening_practices(self, config, teams, league, all_slots):
        """Generate practices after opening day (on P days only)."""
        if not config.opening_day_date:
            return

        practice_days = config.practice_days
        if not practice_days:
            return

        # Get practice dates for ~10 weeks after opening
        end_date = config.opening_day_date + timedelta(weeks=12)
        current_date = config.opening_day_date

        while current_date <= end_date:
            if current_date.weekday() in practice_days:
                self._assign_practices_for_date(config, teams, league, all_slots, current_date)
            current_date += timedelta(days=1)

    def _generate_round_robin(self, teams, games_per_team):
        """Generate round-robin matchups ensuring balance.

        Returns list of (home_team, away_team) tuples.
        """
        n = len(teams)
        matchups = []

        # Calculate how many times each pair should play
        # For games_per_team games, we need games_per_team / (n-1) matchups per pair
        total_games_needed = (games_per_team * n) // 2
        games_per_pair = max(1, games_per_team // (n - 1))

        # Generate base round-robin
        for round_num in range(games_per_pair):
            for i in range(n):
                for j in range(i + 1, n):
                    # Alternate home/away each round
                    if (round_num + i + j) % 2 == 0:
                        matchups.append((teams[i], teams[j]))
                    else:
                        matchups.append((teams[j], teams[i]))

        # Shuffle to avoid predictable patterns
        random.shuffle(matchups)

        # Trim to exact number needed
        matchups = matchups[:total_games_needed]

        return matchups

    def _generate_scrimmages(self, config, teams, league, all_slots, scrimmage_date):
        """Generate scrimmages - one per team, random pairing."""
        # Shuffle teams and pair them up
        shuffled = list(teams)
        random.shuffle(shuffled)

        # Get available slots for this date
        day_of_week = scrimmage_date.weekday()
        available_slots = [
            s for s in all_slots
            if s.day_of_week == day_of_week and self._can_use_slot(s, league, 'game')
        ]

        slot_idx = 0
        for i in range(0, len(shuffled) - 1, 2):
            home = shuffled[i]
            away = shuffled[i + 1]

            # Find a slot
            slot = available_slots[slot_idx % len(available_slots)] if available_slots else None
            game_datetime = self._slot_to_datetime(slot, scrimmage_date) if slot else None

            game = ProposedGame(
                game_type='scrimmage',
                league=config.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=home,
                away_team=away,
                field=slot.field if slot else None,
                game_date=game_datetime,
                is_scrimmage=True
            )
            game.slot = slot
            game.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(game)

            slot_idx += 1

        # Handle odd team out (no scrimmage partner)
        if len(shuffled) % 2 == 1:
            self.warnings.append({
                'type': 'odd_team',
                'message': f'{config.league}: Odd number of teams - {shuffled[-1].display_name} has no scrimmage partner.'
            })

    def _assign_practices_for_date(self, config, teams, league, all_slots, practice_date):
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

        # Track slot usage (for capacity)
        slot_usage = defaultdict(int)

        for team in teams:
            # Find best slot (considering capacity and balance)
            assigned_slot = None
            for slot in available_slots:
                capacity = self._get_slot_capacity(slot, practice_date)
                if slot_usage[slot.slot_ID] < capacity:
                    assigned_slot = slot
                    break

            if not assigned_slot:
                # All slots at capacity, use first one anyway
                assigned_slot = available_slots[0]

            slot_usage[assigned_slot.slot_ID] += 1

            game_datetime = self._slot_to_datetime(assigned_slot, practice_date)

            practice = ProposedGame(
                game_type='practice',
                league=config.league,
                year=self.year,
                is_spring=self.is_spring,
                home_team=team,
                away_team=None,
                field=assigned_slot.field if assigned_slot else None,
                game_date=game_datetime
            )
            practice.slot = assigned_slot
            practice.id = self._next_id
            self._next_id += 1
            self.proposed_games.append(practice)

    def _assign_games_to_slots(self, config, matchups, slots_by_date, league):
        """Assign game matchups to available slots."""
        matchup_idx = 0

        # Track home/away counts for balancing
        home_counts = defaultdict(int)
        away_counts = defaultdict(int)
        early_counts = defaultdict(int)
        late_counts = defaultdict(int)

        for game_date, slots in sorted(slots_by_date.items()):
            for slot in slots:
                if matchup_idx >= len(matchups):
                    break

                home, away = matchups[matchup_idx]

                # Try to balance home/away
                if home_counts[home.team_ID] > away_counts[home.team_ID] + 1:
                    # Swap home/away
                    home, away = away, home

                game_datetime = self._slot_to_datetime(slot, game_date)
                is_early = game_datetime.hour < 18 if game_datetime else True

                game = ProposedGame(
                    game_type='regular',
                    league=config.league,
                    year=self.year,
                    is_spring=self.is_spring,
                    home_team=home,
                    away_team=away,
                    field=slot.field if slot else None,
                    game_date=game_datetime
                )
                game.slot = slot
                game.id = self._next_id
                self._next_id += 1
                self.proposed_games.append(game)

                # Update tracking
                home_counts[home.team_ID] += 1
                away_counts[away.team_ID] += 1
                if is_early:
                    early_counts[home.team_ID] += 1
                    early_counts[away.team_ID] += 1
                else:
                    late_counts[home.team_ID] += 1
                    late_counts[away.team_ID] += 1

                matchup_idx += 1

            if matchup_idx >= len(matchups):
                break

        # Warn if not all matchups assigned
        if matchup_idx < len(matchups):
            self.warnings.append({
                'type': 'insufficient_slots',
                'message': f'{config.league}: Only {matchup_idx} of {len(matchups)} games could be scheduled. Need more field slots.'
            })

    def _can_use_slot(self, slot, league, usage_type):
        """Check if a league can use a slot."""
        if not slot.field:
            return False

        field = slot.field

        # Check field usage type
        if usage_type == 'game' and not field.allows_games:
            return False
        if usage_type == 'practice' and not field.allows_practices:
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

    def _get_slot_capacity(self, slot, game_date):
        """Get practice capacity for a slot."""
        if not slot.field:
            return 1

        # Check if late slot
        is_late = slot.start_time and slot.start_time.hour >= 19
        return slot.field.get_practice_capacity(is_late_slot=is_late)

    def _slot_to_datetime(self, slot, target_date):
        """Convert a slot to a datetime on the target date."""
        if not slot or not slot.start_time:
            return None
        return datetime.combine(target_date, slot.start_time)

    def _get_dates_for_days(self, start_date, day_numbers, count_needed):
        """Get the next N dates that fall on specified days of week."""
        dates = []
        current = start_date
        max_weeks = 20  # Safety limit

        while len(dates) < count_needed and (current - start_date).days < max_weeks * 7:
            if current.weekday() in day_numbers:
                dates.append(current)
            current += timedelta(days=1)

        return dates

    def _group_slots_by_date(self, all_slots, dates, league, usage_type):
        """Group available slots by date."""
        result = {}

        for target_date in dates:
            day_of_week = target_date.weekday()
            day_slots = [
                s for s in all_slots
                if s.day_of_week == day_of_week and self._can_use_slot(s, league, usage_type)
            ]
            if day_slots:
                result[target_date] = day_slots

        return result

    def _build_result(self):
        """Build the result dictionary."""
        return {
            'games': [g.to_dict() for g in self.proposed_games],
            'violations': [v.to_dict() for v in self.violations],
            'warnings': self.warnings,
            'summary': {
                'total_games': len([g for g in self.proposed_games if g.game_type in ('regular', 'playoff')]),
                'total_practices': len([g for g in self.proposed_games if g.game_type == 'practice']),
                'total_scrimmages': len([g for g in self.proposed_games if g.game_type == 'scrimmage']),
                'hard_violations': len([v for v in self.violations if v.severity == ScheduleViolation.HARD]),
                'soft_violations': len([v for v in self.violations if v.severity == ScheduleViolation.SOFT])
            }
        }
