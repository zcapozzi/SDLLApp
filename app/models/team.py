"""Team Season model - maps to sdll_team_seasons table"""

import secrets
from app.extensions import db


class TeamSeason(db.Model):
    """Represents a team for a specific season

    Display name logic:
    1. If team_name is set -> show team_name (e.g., "The Thunderbolts")
    2. If coach is assigned but no team_name -> show "Team [Coach Last Name]"
    3. Otherwise -> show placeholder (e.g., "BB Majors Team 1")
    """
    __tablename__ = 'sdll_team_seasons'

    team_ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    year = db.Column(db.Integer)
    league = db.Column(db.String(50))
    display_name = db.Column(db.String(50))  # Placeholder name (e.g., "BB Majors Team 1")
    team_name = db.Column(db.String(50))  # Chosen team name (e.g., "Thunderbolts")
    is_placeholder = db.Column(db.SmallInteger, default=0)
    seed_number = db.Column(db.Integer)  # For "Seed 1", "Seed 2" placeholders
    bracket_position = db.Column(db.String(20))  # For "Winner Game 1" type placeholders
    resolved_team_id = db.Column(db.BigInteger)  # Actual team that fills this placeholder
    is_spring = db.Column(db.SmallInteger)  # 0=Fall, 1=Spring

    # Team-specific practice days (overrides league default if set)
    # Format: comma-separated day numbers (0=Mon, 1=Tue, ..., 6=Sun), e.g., "1,3" for Tue/Thu
    # NULL means use the league default
    practice_days = db.Column(db.String(50), nullable=True)

    # Organization - NULL means SDLL (home org), set for external teams
    organization_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=True)

    # Public schedule URL token - unique per team for sharing schedules
    schedule_token = db.Column(db.String(32), unique=True, nullable=True, index=True)

    # Future: coach_id will link to sdll_coach_seasons
    # coach_id = db.Column(db.BigInteger, db.ForeignKey('sdll_coach_seasons.ID'))

    # Relationships - games where this team is home or away
    home_games = db.relationship(
        'Game',
        foreign_keys='Game.home_ID',
        backref='home_team',
        lazy='dynamic'
    )
    away_games = db.relationship(
        'Game',
        foreign_keys='Game.away_ID',
        backref='away_team',
        lazy='dynamic'
    )

    # Relationship to organization (for external teams)
    organization = db.relationship('Organization', backref='teams')

    def __repr__(self):
        season = 'Spring' if self.is_spring else 'Fall'
        return f'<TeamSeason {self.display_name} ({season} {self.year})>'

    @property
    def is_external(self):
        """Check if this is an external (non-SDLL) team"""
        return self.organization_id is not None

    @property
    def season_name(self):
        """Return human-readable season name"""
        return 'Spring' if self.is_spring else 'Fall'

    @property
    def full_season_name(self):
        """Return full season description"""
        return f'{self.season_name} {self.year}'

    # Class-level cache for team name lookups
    _team_name_cache = {}

    @property
    def computed_display_name(self):
        """
        Get the display name based on current state:
        1. team_name if set
        2. Look for matching team with team_name in same league/season (cached)
        3. display_name (placeholder) otherwise
        """
        if self.team_name:
            return self.team_name

        # If this team doesn't have a team_name, look for a matching team that does
        # This handles the case where games are linked to placeholder teams
        # but actual teams with coach names exist separately
        if self.display_name and self.league and self.year is not None and self.is_spring is not None:
            cache_key = (self.display_name, self.league, self.year, self.is_spring)

            if cache_key not in TeamSeason._team_name_cache:
                matching_team = TeamSeason.query.filter(
                    TeamSeason.display_name == self.display_name,
                    TeamSeason.league == self.league,
                    TeamSeason.year == self.year,
                    TeamSeason.is_spring == self.is_spring,
                    TeamSeason.team_name.isnot(None),
                    TeamSeason.team_ID != self.team_ID
                ).first()
                TeamSeason._team_name_cache[cache_key] = matching_team.team_name if matching_team else None

            cached_name = TeamSeason._team_name_cache.get(cache_key)
            if cached_name:
                return cached_name

        return self.display_name

    @classmethod
    def clear_name_cache(cls):
        """Clear the team name lookup cache."""
        cls._team_name_cache = {}

    @property
    def display_name_with_org(self):
        """Get display name with organization suffix for external teams"""
        name = self.computed_display_name
        if self.is_external and self.organization:
            return f"{name} ({self.organization.display_name})"
        return name

    def get_practice_days(self, league_season=None):
        """Get the effective practice days for this team.

        Returns a list of day numbers (0=Monday, ..., 6=Sunday).
        Uses team-specific practice_days if set, otherwise falls back to league default.

        Args:
            league_season: Optional LeagueSeason object. If not provided, will be queried.
        """
        # If team has specific practice days, parse and return them
        if self.practice_days:
            try:
                return [int(d.strip()) for d in self.practice_days.split(',') if d.strip()]
            except ValueError:
                pass  # Fall back to league default if parse fails

        # Get league default
        if league_season is None:
            from app.models.league_season import LeagueSeason
            league_season = LeagueSeason.query.filter_by(
                year=self.year,
                is_spring=self.is_spring,
                league=self.league,
                active=1
            ).first()

        if league_season:
            return league_season.practice_days

        return []  # No practice days configured

    @property
    def practice_days_display(self):
        """Get human-readable practice days for this team."""
        days = self.get_practice_days()
        if not days:
            return None
        day_abbrevs = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        return ', '.join(day_abbrevs[d] for d in days if 0 <= d <= 6)

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active teams for a specific season"""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.league, cls.display_name).all()

    @classmethod
    def get_by_schedule_token(cls, token):
        """Look up a team by its public schedule token."""
        if not token:
            return None
        return cls.query.filter_by(schedule_token=token, active=1).first()

    def generate_schedule_token(self):
        """Generate a unique schedule token for this team."""
        # Generate a 16-character URL-safe token
        self.schedule_token = secrets.token_urlsafe(12)
        db.session.commit()
        return self.schedule_token

    def get_or_create_schedule_token(self):
        """Get existing token or generate a new one."""
        if not self.schedule_token:
            return self.generate_schedule_token()
        return self.schedule_token

    @classmethod
    def generate_all_tokens_for_season(cls, year, is_spring):
        """Generate schedule tokens for all teams in a season that don't have one."""
        teams = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).filter(cls.schedule_token.is_(None)).all()

        for team in teams:
            team.schedule_token = secrets.token_urlsafe(12)

        db.session.commit()
        return len(teams)

    @classmethod
    def copy_to_new_season(cls, source_year, source_is_spring, target_year, target_is_spring):
        """
        Copy team STRUCTURE from source season to target season.
        Team names are reset to placeholders (e.g., "BB Majors Team 1").
        """
        source_teams = cls.get_by_season(source_year, source_is_spring)
        new_teams = []

        # Group source teams by league to maintain counts
        teams_by_league = {}
        for team in source_teams:
            league = team.league or 'Unknown'
            if league not in teams_by_league:
                teams_by_league[league] = []
            teams_by_league[league].append(team)

        # Create new teams with placeholder names
        for league, teams in teams_by_league.items():
            for i, source_team in enumerate(teams, start=1):
                # Create placeholder name: "BB Majors Team 1"
                placeholder_name = f'{league} Team {i}'

                new_team = TeamSeason(
                    active=1,
                    year=target_year,
                    league=league,
                    display_name=placeholder_name,
                    team_name=None,  # Reset - no chosen name yet
                    is_placeholder=source_team.is_placeholder,
                    is_spring=target_is_spring
                )
                db.session.add(new_team)
                new_teams.append(new_team)

        db.session.commit()
        return new_teams

    @classmethod
    def delete_season_teams(cls, year, is_spring):
        """
        Delete all teams for a season (soft delete).
        Returns count of deleted teams.
        """
        teams = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).all()

        count = 0
        for team in teams:
            team.active = 0
            count += 1

        db.session.commit()
        return count

    @classmethod
    def hard_delete_season_teams(cls, year, is_spring):
        """
        Permanently delete all teams for a season.
        WARNING: This also affects any games referencing these teams.
        Returns count of deleted teams.
        """
        count = cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).delete()
        db.session.commit()
        return count

    @classmethod
    def generate_seed_placeholders(cls, year, is_spring, league, num_seeds):
        """
        Generate seed placeholders (Seed 1, Seed 2, etc.) for a league's playoffs.
        Returns list of created placeholder teams.
        """
        placeholders = []

        # Check for existing seed placeholders
        existing = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            is_placeholder=1,
            active=1
        ).filter(cls.seed_number.isnot(None)).all()

        existing_seeds = {t.seed_number for t in existing}

        for seed in range(1, num_seeds + 1):
            if seed not in existing_seeds:
                placeholder = cls(
                    active=1,
                    year=year,
                    league=league,
                    display_name=f'Seed {seed}',
                    is_placeholder=1,
                    seed_number=seed,
                    is_spring=is_spring
                )
                db.session.add(placeholder)
                placeholders.append(placeholder)

        db.session.commit()
        return placeholders

    @classmethod
    def generate_bracket_placeholders(cls, year, is_spring, league, playoff_format, num_teams):
        """
        Generate bracket placeholders (Winner Game 1, etc.) based on format.
        Returns list of created placeholder teams.
        """
        placeholders = []

        if playoff_format == 'single_elimination':
            # Single elimination: need (num_teams - 1) games
            # Round 1: num_teams/2 games, Round 2: num_teams/4, etc.
            num_games = num_teams - 1
            game_num = 1

            # Start from quarterfinals/semis, work to finals
            teams_remaining = num_teams
            round_num = 1

            while teams_remaining > 1:
                games_in_round = teams_remaining // 2
                for g in range(games_in_round):
                    if teams_remaining > 2:  # Don't create "Winner" for championship
                        placeholder = cls(
                            active=1,
                            year=year,
                            league=league,
                            display_name=f'Winner Game {game_num}',
                            is_placeholder=1,
                            bracket_position=f'W{game_num}',
                            is_spring=is_spring
                        )
                        db.session.add(placeholder)
                        placeholders.append(placeholder)
                    game_num += 1
                teams_remaining = teams_remaining // 2
                round_num += 1

        elif playoff_format == 'double_elimination':
            # Double elimination needs winners and losers bracket
            # More complex - create Winner and Loser placeholders
            num_games = (num_teams * 2) - 2  # Approximate

            for game_num in range(1, num_games):
                # Winners bracket
                placeholder_w = cls(
                    active=1,
                    year=year,
                    league=league,
                    display_name=f'Winner Game {game_num}',
                    is_placeholder=1,
                    bracket_position=f'W{game_num}',
                    is_spring=is_spring
                )
                db.session.add(placeholder_w)
                placeholders.append(placeholder_w)

                # Losers bracket (for early rounds)
                if game_num <= num_teams // 2:
                    placeholder_l = cls(
                        active=1,
                        year=year,
                        league=league,
                        display_name=f'Loser Game {game_num}',
                        is_placeholder=1,
                        bracket_position=f'L{game_num}',
                        is_spring=is_spring
                    )
                    db.session.add(placeholder_l)
                    placeholders.append(placeholder_l)

        db.session.commit()
        return placeholders

    @classmethod
    def get_playoff_placeholders(cls, year, is_spring, league):
        """Get all playoff placeholders for a league, ordered by seed then bracket position."""
        # MySQL doesn't support NULLS LAST, so use CASE to sort nulls last
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            is_placeholder=1,
            active=1
        ).order_by(
            db.case((cls.seed_number.is_(None), 1), else_=0),
            cls.seed_number.asc(),
            cls.bracket_position.asc()
        ).all()

    @classmethod
    def get_regular_teams(cls, year, is_spring, league):
        """Get all regular (non-placeholder) teams for a league."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            is_placeholder=0,
            active=1
        ).order_by(cls.display_name).all()

    def resolve_to_team(self, actual_team_id):
        """Resolve this placeholder to an actual team."""
        if not self.is_placeholder:
            raise ValueError("Can only resolve placeholder teams")
        self.resolved_team_id = actual_team_id
        db.session.commit()

    @property
    def resolved_team(self):
        """Get the actual team this placeholder resolved to."""
        if self.resolved_team_id:
            return TeamSeason.query.get(self.resolved_team_id)
        return None

    @property
    def resolved_display_name(self):
        """Get display name, using resolved team if available."""
        if self.resolved_team_id:
            resolved = self.resolved_team
            if resolved:
                return resolved.computed_display_name
        return self.display_name
