"""Game model - maps to sdll_games table"""

from datetime import datetime
from app.extensions import db


class Game(db.Model):
    """Represents a scheduled game"""
    __tablename__ = 'sdll_games'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    game_date = db.Column(db.DateTime)
    home_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'))
    away_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'))
    league = db.Column(db.String(30))
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, postponed, cancelled
    assignr_id = db.Column(db.String(15))
    year = db.Column(db.Integer)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    duration_in_hours = db.Column(db.Float)
    is_doubleheader = db.Column(db.SmallInteger, default=0)
    is_spring = db.Column(db.SmallInteger)  # 0=Fall, 1=Spring
    game_type = db.Column(db.String(20), default='regular')  # regular, playoff, practice
    is_scrimmage = db.Column(db.SmallInteger, default=0)
    umpire_override = db.Column(db.String(20))

    def __repr__(self):
        return f'<Game {self.ID}: {self.league} at {self.location} on {self.game_date}>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return 'Spring' if self.is_spring else 'Fall'

    @property
    def is_upcoming(self):
        """Check if game is in the future"""
        return self.game_date and self.game_date > datetime.utcnow()

    @property
    def needs_umpire(self):
        """Check if game needs an umpire assignment"""
        return not self.is_scrimmage and self.status == 'scheduled'

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active games for a specific season"""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.game_date).all()

    @classmethod
    def get_upcoming(cls, limit=20):
        """Get upcoming scheduled games"""
        return cls.query.filter(
            cls.game_date > datetime.utcnow(),
            cls.status == 'scheduled',
            cls.active == 1
        ).order_by(cls.game_date).limit(limit).all()

    @classmethod
    def copy_to_new_season(cls, source_year, source_is_spring, target_year, target_is_spring,
                           team_id_mapping=None, adjust_dates=True):
        """
        Copy all games from source season to target season.

        Args:
            source_year: Year of source season
            source_is_spring: Whether source is spring season
            target_year: Year of target season
            target_is_spring: Whether target is spring season
            team_id_mapping: Dict mapping old team_IDs to new team_IDs
            adjust_dates: Whether to adjust dates by year difference
        """
        from dateutil.relativedelta import relativedelta

        source_games = cls.get_by_season(source_year, source_is_spring)
        year_diff = target_year - source_year
        new_games = []

        for game in source_games:
            new_game_date = game.game_date
            if adjust_dates and game.game_date:
                new_game_date = game.game_date + relativedelta(years=year_diff)

            new_home_ID = None
            new_away_ID = None
            if team_id_mapping:
                if game.home_ID:
                    new_home_ID = team_id_mapping.get(game.home_ID)
                if game.away_ID:
                    new_away_ID = team_id_mapping.get(game.away_ID)

            new_game = Game(
                active=1,
                game_date=new_game_date,
                home_ID=new_home_ID,
                away_ID=new_away_ID,
                league=game.league,
                location=game.location,
                status='scheduled',
                year=target_year,
                date_added=datetime.utcnow(),
                duration_in_hours=game.duration_in_hours,
                is_doubleheader=game.is_doubleheader,
                is_spring=target_is_spring,
                is_scrimmage=game.is_scrimmage
            )
            db.session.add(new_game)
            new_games.append(new_game)

        db.session.commit()
        return new_games

    @classmethod
    def generate_regular_season_games(cls, year, is_spring, league, teams, games_per_team):
        """
        Generate regular season game slots with team matchups.

        Uses a round-robin algorithm to create balanced matchups.
        Each team plays approximately games_per_team games.

        Args:
            year: Season year
            is_spring: Whether spring season
            league: League name
            teams: List of TeamSeason objects (regular teams, not placeholders)
            games_per_team: Number of games each team should play

        Returns:
            List of created Game objects
        """
        if len(teams) < 2:
            return []

        new_games = []
        team_ids = [t.team_ID for t in teams]
        n = len(team_ids)

        # Calculate total games needed
        # Each game involves 2 teams, so total = (n * games_per_team) / 2
        total_games = (n * games_per_team) // 2

        # Generate round-robin matchups
        # Each round-robin cycle gives each team (n-1) games
        matchups = []
        for round_num in range((games_per_team // (n - 1)) + 1):
            # Standard round-robin: rotate all but first team
            rotation = team_ids.copy()
            for _ in range(n - 1):
                # Pair teams: first with last, second with second-to-last, etc.
                for i in range(n // 2):
                    home = rotation[i]
                    away = rotation[n - 1 - i]
                    # Alternate home/away based on round
                    if round_num % 2 == 1:
                        home, away = away, home
                    matchups.append((home, away))
                # Rotate: keep first fixed, rotate rest
                rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]

        # Take only the number of games we need
        matchups = matchups[:total_games]

        # Create game records
        for home_id, away_id in matchups:
            game = cls(
                active=1,
                home_ID=home_id,
                away_ID=away_id,
                league=league,
                status='scheduled',
                year=year,
                is_spring=is_spring,
                game_type='regular',
                date_added=datetime.utcnow()
            )
            db.session.add(game)
            new_games.append(game)

        db.session.commit()
        return new_games

    @classmethod
    def generate_playoff_games(cls, year, is_spring, league, seed_placeholders, playoff_format):
        """
        Generate playoff game slots using seed placeholders.

        Args:
            year: Season year
            is_spring: Whether spring season
            league: League name
            seed_placeholders: List of TeamSeason placeholder objects (Seed 1, Seed 2, etc.)
            playoff_format: 'single_elimination', 'double_elimination', or 'round_robin_knockout'

        Returns:
            List of created Game objects
        """
        new_games = []
        n = len(seed_placeholders)

        if n < 2:
            return []

        # Sort by seed number
        seeds = sorted(seed_placeholders, key=lambda t: t.seed_number or 999)

        if playoff_format == 'single_elimination':
            # Single elimination always has n-1 total games
            total_games_needed = n - 1

            # For non-power-of-2 brackets, some teams get byes
            # Find next power of 2 >= n
            bracket_size = 1
            while bracket_size < n:
                bracket_size *= 2
            num_byes = bracket_size - n
            first_round_games = (n - num_byes) // 2  # Teams without byes play first

            # First round: lower seeds play each other
            # E.g., 6 teams: seeds 3,4,5,6 play (2 games), seeds 1,2 get byes
            games_created = 0
            for i in range(first_round_games):
                # Pair from the bottom of the bracket
                # For 6 teams: Game 1 = Seed 3 vs Seed 6, Game 2 = Seed 4 vs Seed 5
                high_idx = num_byes + i  # Start after bye teams
                low_idx = n - 1 - i
                if high_idx < low_idx:
                    high_seed = seeds[high_idx]
                    low_seed = seeds[low_idx]
                    game = cls(
                        active=1,
                        home_ID=high_seed.team_ID,
                        away_ID=low_seed.team_ID,
                        league=league,
                        status='scheduled',
                        year=year,
                        is_spring=is_spring,
                        game_type='playoff',
                        date_added=datetime.utcnow()
                    )
                    db.session.add(game)
                    new_games.append(game)
                    games_created += 1

            # Remaining games (semis, finals, etc.) - teams TBD
            remaining_games = total_games_needed - games_created
            for _ in range(remaining_games):
                game = cls(
                    active=1,
                    home_ID=None,  # TBD - winner of previous game
                    away_ID=None,  # TBD - winner of previous game
                    league=league,
                    status='scheduled',
                    year=year,
                    is_spring=is_spring,
                    game_type='playoff',
                    date_added=datetime.utcnow()
                )
                db.session.add(game)
                new_games.append(game)

        elif playoff_format == 'double_elimination':
            # Double elimination is more complex
            # Winners bracket + losers bracket + championship
            # For simplicity, create the expected number of games
            total_games = (2 * n) - 2

            # First round of winners bracket
            for i in range(n // 2):
                high_seed = seeds[i]
                low_seed = seeds[n - 1 - i]
                game = cls(
                    active=1,
                    home_ID=high_seed.team_ID,
                    away_ID=low_seed.team_ID,
                    league=league,
                    status='scheduled',
                    year=year,
                    is_spring=is_spring,
                    game_type='playoff',
                    date_added=datetime.utcnow()
                )
                db.session.add(game)
                new_games.append(game)

            # Remaining games (losers bracket, later rounds)
            remaining = total_games - (n // 2)
            for _ in range(remaining):
                game = cls(
                    active=1,
                    home_ID=None,
                    away_ID=None,
                    league=league,
                    status='scheduled',
                    year=year,
                    is_spring=is_spring,
                    game_type='playoff',
                    date_added=datetime.utcnow()
                )
                db.session.add(game)
                new_games.append(game)

        elif playoff_format == 'round_robin_knockout':
            # Round robin among all playoff teams
            for i in range(n):
                for j in range(i + 1, n):
                    game = cls(
                        active=1,
                        home_ID=seeds[i].team_ID,
                        away_ID=seeds[j].team_ID,
                        league=league,
                        status='scheduled',
                        year=year,
                        is_spring=is_spring,
                        game_type='playoff',
                        date_added=datetime.utcnow()
                    )
                    db.session.add(game)
                    new_games.append(game)

            # Knockout rounds (assume top 4 advance)
            knockout_teams = min(n, 4)
            knockout_games = knockout_teams - 1
            for _ in range(knockout_games):
                game = cls(
                    active=1,
                    home_ID=None,
                    away_ID=None,
                    league=league,
                    status='scheduled',
                    year=year,
                    is_spring=is_spring,
                    game_type='playoff',
                    date_added=datetime.utcnow()
                )
                db.session.add(game)
                new_games.append(game)

        db.session.commit()
        return new_games

    @classmethod
    def get_by_type(cls, year, is_spring, league, game_type):
        """Get games by type (regular, playoff, practice)"""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            game_type=game_type,
            active=1
        ).order_by(cls.game_date).all()

    @classmethod
    def count_by_type(cls, year, is_spring, league):
        """Count games by type for a league"""
        from sqlalchemy import func
        results = db.session.query(
            cls.game_type,
            func.count(cls.ID)
        ).filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            active=1
        ).group_by(cls.game_type).all()
        return {game_type: count for game_type, count in results}
