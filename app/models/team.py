"""Team Season model - maps to sdll_team_seasons table"""

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

    def __repr__(self):
        season = 'Spring' if self.is_spring else 'Fall'
        return f'<TeamSeason {self.display_name} ({season} {self.year})>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return 'Spring' if self.is_spring else 'Fall'

    @property
    def full_season_name(self):
        """Return full season description"""
        return f'{self.season_name} {self.year}'

    @property
    def computed_display_name(self):
        """
        Get the display name based on current state:
        1. team_name if set
        2. "Team [Coach Last Name]" if coach assigned (future)
        3. display_name (placeholder) otherwise
        """
        if self.team_name:
            return self.team_name
        # Future: check for coach
        # if self.coach and self.coach.last_name:
        #     return f"Team {self.coach.last_name}"
        return self.display_name

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active teams for a specific season"""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.league, cls.display_name).all()

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
