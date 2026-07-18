"""League Season model - maps to sdll_league_seasons table"""

from datetime import date
from app.extensions import db


class LeagueSeason(db.Model):
    """Represents league configuration for a specific season.

    Stores playoff format and other league-specific settings that may
    vary from season to season.
    """
    __tablename__ = 'sdll_league_seasons'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    league = db.Column(db.String(50), nullable=False)
    playoff_format = db.Column(db.String(30), default='single_elimination')
    playoff_teams = db.Column(db.Integer, default=0)  # 0 = all teams qualify
    regular_season_games = db.Column(db.Integer, default=10)  # Games per team in regular season
    notes = db.Column(db.String(200))

    # Schedule settings - day types: NULL=nothing, 'practice', 'game'
    monday_type = db.Column(db.String(10))
    tuesday_type = db.Column(db.String(10))
    wednesday_type = db.Column(db.String(10))
    thursday_type = db.Column(db.String(10))
    friday_type = db.Column(db.String(10))
    saturday_type = db.Column(db.String(10))
    sunday_type = db.Column(db.String(10))
    first_practice_date = db.Column(db.Date)
    opening_day_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    # Playoff format options
    PLAYOFF_FORMATS = [
        ('single_elimination', 'Single Elimination'),
        ('double_elimination', 'Double Elimination'),
        ('round_robin_knockout', 'Round Robin + Knockout'),
    ]

    # Day type options
    DAY_TYPE_PRACTICE = 'practice'
    DAY_TYPE_GAME = 'game'

    # Day name mapping
    DAY_COLUMNS = ['monday_type', 'tuesday_type', 'wednesday_type', 'thursday_type',
                   'friday_type', 'saturday_type', 'sunday_type']
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    DAY_ABBREVS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __repr__(self):
        return f'<LeagueSeason {self.league} {self.season_name}>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    @property
    def playoff_format_display(self):
        """Return human-readable playoff format"""
        for value, label in self.PLAYOFF_FORMATS:
            if value == self.playoff_format:
                return label
        return self.playoff_format

    @property
    def actual_playoff_teams(self):
        """Get actual number of playoff teams (resolves 0 to team count)"""
        if self.playoff_teams and self.playoff_teams > 0:
            return self.playoff_teams
        # 0 or NULL means all teams qualify
        from app.models.team import TeamSeason
        return TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=self.league,
            is_placeholder=0,
            active=1
        ).count()

    @property
    def playoff_game_count(self):
        """Calculate number of playoff games based on format and teams"""
        n = self.actual_playoff_teams
        if n < 2:
            return 0
        if self.playoff_format == 'single_elimination':
            return n - 1
        elif self.playoff_format == 'double_elimination':
            # Double elim: winners bracket (n-1) + losers bracket (n-1) + finals (1-2)
            # Simplified: approximately 2n - 2
            return (2 * n) - 2
        elif self.playoff_format == 'round_robin_knockout':
            # Round robin among n teams + knockout
            # Round robin = n*(n-1)/2 games, then top teams do knockout
            round_robin = (n * (n - 1)) // 2
            # Assume top 4 go to knockout (3 games)
            knockout = min(n, 4) - 1
            return round_robin + knockout
        return n - 1  # Default to single elim

    @property
    def total_regular_season_games(self):
        """Calculate total regular season games for the league.

        Each team plays regular_season_games, but each game involves 2 teams,
        so total games = (teams * games_per_team) / 2
        """
        from app.models.team import TeamSeason
        team_count = TeamSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            league=self.league,
            is_placeholder=0,
            active=1
        ).count()
        if team_count == 0:
            return 0
        return (team_count * (self.regular_season_games or 10)) // 2

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active league configs for a specific season"""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.league).all()

    @classmethod
    def get_or_create(cls, year, is_spring, league):
        """Get existing config or create a new one with defaults"""
        # First check for active config
        config = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            active=1
        ).first()

        if not config:
            # Check for soft-deleted config to reactivate
            config = cls.query.filter_by(
                year=year,
                is_spring=is_spring,
                league=league,
                active=0
            ).first()

            if config:
                # Reactivate it
                config.active = 1
                db.session.commit()
            else:
                # Create new
                config = cls(
                    year=year,
                    is_spring=is_spring,
                    league=league,
                    playoff_format='single_elimination',
                    playoff_teams=0  # 0 = all teams qualify
                )
                db.session.add(config)
                db.session.commit()

        return config

    @classmethod
    def copy_to_new_season(cls, source_year, source_is_spring, target_year, target_is_spring):
        """Copy all league configs from source season to target season."""
        source_configs = cls.get_by_season(source_year, source_is_spring)
        new_configs = []

        for source in source_configs:
            # Check if target already exists
            existing = cls.query.filter_by(
                year=target_year,
                is_spring=target_is_spring,
                league=source.league,
                active=1
            ).first()

            if not existing:
                new_config = cls(
                    active=1,
                    year=target_year,
                    is_spring=target_is_spring,
                    league=source.league,
                    playoff_format=source.playoff_format,
                    playoff_teams=source.playoff_teams,
                    regular_season_games=source.regular_season_games,
                    notes=source.notes,
                    # Copy schedule day settings (but not dates - those change each year)
                    monday_type=source.monday_type,
                    tuesday_type=source.tuesday_type,
                    wednesday_type=source.wednesday_type,
                    thursday_type=source.thursday_type,
                    friday_type=source.friday_type,
                    saturday_type=source.saturday_type,
                    sunday_type=source.sunday_type
                )
                db.session.add(new_config)
                new_configs.append(new_config)

        db.session.commit()
        return new_configs

    @classmethod
    def ensure_leagues_for_season(cls, year, is_spring, leagues):
        """Ensure all leagues have a config for this season.

        Creates configs with defaults for any missing leagues.
        Reactivates soft-deleted configs if they exist.
        """
        existing = {c.league for c in cls.get_by_season(year, is_spring)}

        for league in leagues:
            league_name = league if isinstance(league, str) else league.display_name
            if league_name not in existing:
                # Check for soft-deleted config to reactivate
                soft_deleted = cls.query.filter_by(
                    year=year,
                    is_spring=is_spring,
                    league=league_name,
                    active=0
                ).first()

                if soft_deleted:
                    soft_deleted.active = 1
                else:
                    config = cls(
                        year=year,
                        is_spring=is_spring,
                        league=league_name,
                        playoff_format='single_elimination',
                        playoff_teams=0  # 0 = all teams qualify
                    )
                    db.session.add(config)

        db.session.commit()

    def get_day_type(self, day_index):
        """Get the type for a specific day (0=Monday, 6=Sunday)"""
        col = self.DAY_COLUMNS[day_index]
        return getattr(self, col)

    def set_day_type(self, day_index, day_type):
        """Set the type for a specific day (0=Monday, 6=Sunday)"""
        col = self.DAY_COLUMNS[day_index]
        setattr(self, col, day_type if day_type else None)

    @property
    def day_types(self):
        """Get all day types as a list [Mon, Tue, Wed, Thu, Fri, Sat, Sun]"""
        return [getattr(self, col) for col in self.DAY_COLUMNS]

    @property
    def practice_days(self):
        """Get list of day numbers (0=Monday) that are practice days"""
        return [i for i, col in enumerate(self.DAY_COLUMNS)
                if getattr(self, col) == self.DAY_TYPE_PRACTICE]

    @property
    def game_days(self):
        """Get list of day numbers (0=Monday) that are game days"""
        return [i for i, col in enumerate(self.DAY_COLUMNS)
                if getattr(self, col) == self.DAY_TYPE_GAME]

    @property
    def practice_days_display(self):
        """Get human-readable practice days"""
        days = self.practice_days
        if not days:
            return None
        return ', '.join(self.DAY_ABBREVS[d] for d in days)

    @property
    def game_days_display(self):
        """Get human-readable game days"""
        days = self.game_days
        if not days:
            return None
        return ', '.join(self.DAY_ABBREVS[d] for d in days)

    @property
    def schedule_ready(self):
        """Check if this league has all required schedule settings"""
        has_game_day = any(getattr(self, col) == self.DAY_TYPE_GAME for col in self.DAY_COLUMNS)
        has_dates = self.first_practice_date is not None and self.opening_day_date is not None
        return has_game_day and has_dates

    @property
    def schedule_status(self):
        """Get a human-readable schedule configuration status"""
        issues = []
        if not any(getattr(self, col) == self.DAY_TYPE_GAME for col in self.DAY_COLUMNS):
            issues.append("No game days set")
        if not self.first_practice_date:
            issues.append("No first practice date")
        if not self.opening_day_date:
            issues.append("No opening day")
        if issues:
            return ", ".join(issues)
        return "Ready"
