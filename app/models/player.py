"""Player models - maps to sdll_players and sdll_player_seasons tables"""

from datetime import date
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class Player(db.Model):
    """
    Core player record - identified by parent_email + player_name composite.
    Persists across seasons for historical tracking.
    """
    __tablename__ = 'sdll_players'

    id = db.Column(db.Integer, primary_key=True)

    # Player identity (encrypted)
    _first_name = db.Column('first_name', db.String(500))
    _last_name = db.Column('last_name', db.String(500))
    name_hash = db.Column(db.String(64), index=True)  # Hash of normalized "firstlast"

    # Parent contact (encrypted) - used as part of composite key
    _parent_email = db.Column('parent_email', db.String(500))
    parent_email_hash = db.Column(db.String(64), index=True)
    _secondary_email = db.Column('secondary_email', db.String(500))
    _parent_first_name = db.Column('parent_first_name', db.String(500))
    _parent_last_name = db.Column('parent_last_name', db.String(500))
    _parent_phone = db.Column('parent_phone', db.String(500))

    # Link to parent user account (if exists)
    parent_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Demographics (not encrypted - needed for queries)
    birth_date = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(1))  # M/F

    # System-generated player ID (like "bennluk1810")
    player_code = db.Column(db.String(20), unique=True, index=True)

    # Program: baseball or softball
    program = db.Column(db.String(20))  # 'baseball' or 'softball'

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    # Relationships
    parent_user = db.relationship('User', backref='players')
    season_records = db.relationship('PlayerSeason', back_populates='player',
                                     lazy='dynamic', order_by='desc(PlayerSeason.id)')
    evaluations = db.relationship('PlayerEvaluation', back_populates='player',
                                  lazy='dynamic', order_by='desc(PlayerEvaluation.id)')

    # Encrypted property accessors
    @property
    def first_name(self):
        return decrypt_value(self._first_name) if self._first_name else None

    @first_name.setter
    def first_name(self, value):
        self._first_name = encrypt_value(value) if value else None
        self._update_name_hash()

    @property
    def last_name(self):
        return decrypt_value(self._last_name) if self._last_name else None

    @last_name.setter
    def last_name(self, value):
        self._last_name = encrypt_value(value) if value else None
        self._update_name_hash()

    @property
    def parent_email(self):
        return decrypt_value(self._parent_email) if self._parent_email else None

    @parent_email.setter
    def parent_email(self, value):
        self._parent_email = encrypt_value(value) if value else None
        self.parent_email_hash = hash_for_lookup(value) if value else None

    @property
    def secondary_email(self):
        return decrypt_value(self._secondary_email) if self._secondary_email else None

    @secondary_email.setter
    def secondary_email(self, value):
        self._secondary_email = encrypt_value(value) if value else None

    @property
    def parent_first_name(self):
        return decrypt_value(self._parent_first_name) if self._parent_first_name else None

    @parent_first_name.setter
    def parent_first_name(self, value):
        self._parent_first_name = encrypt_value(value) if value else None

    @property
    def parent_last_name(self):
        return decrypt_value(self._parent_last_name) if self._parent_last_name else None

    @parent_last_name.setter
    def parent_last_name(self, value):
        self._parent_last_name = encrypt_value(value) if value else None

    @property
    def parent_phone(self):
        return decrypt_value(self._parent_phone) if self._parent_phone else None

    @parent_phone.setter
    def parent_phone(self, value):
        self._parent_phone = encrypt_value(value) if value else None

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def parent_full_name(self):
        if self.parent_first_name and self.parent_last_name:
            return f"{self.parent_first_name} {self.parent_last_name}"
        return None

    def _update_name_hash(self):
        """Update name_hash when name changes."""
        first = decrypt_value(self._first_name) if self._first_name else ''
        last = decrypt_value(self._last_name) if self._last_name else ''
        if first or last:
            normalized = f"{first}{last}".lower().replace(' ', '').replace('-', '')
            self.name_hash = hash_for_lookup(normalized)

    def league_age(self, org_season):
        """Calculate league age for a given season.

        Little League uses April 30 cutoff for Spring, Aug 31 for Fall.
        """
        if not self.birth_date:
            return None

        if org_season.is_spring:
            cutoff = date(org_season.year, 4, 30)
        else:
            cutoff = date(org_season.year, 8, 31)

        age = cutoff.year - self.birth_date.year
        if (cutoff.month, cutoff.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1
        return age

    def __repr__(self):
        return f'<Player {self.player_code}: {self.full_name}>'

    @classmethod
    def find_by_email_and_name(cls, email, first_name, last_name):
        """Find player by parent email + name composite key."""
        email_hash = hash_for_lookup(email)
        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_h = hash_for_lookup(name_normalized)

        return cls.query.filter_by(
            parent_email_hash=email_hash,
            name_hash=name_h
        ).first()

    @classmethod
    def find_by_code(cls, player_code):
        """Find player by their player code."""
        return cls.query.filter_by(player_code=player_code).first()

    @classmethod
    def find_potential_matches(cls, first_name, last_name, birth_date, exclude_email=None):
        """Find potential matching players by name + birth_date.

        Used to detect possible duplicates when a different parent registers
        the same child. Returns players with matching name_hash and birth_date
        but different parent_email.

        Args:
            first_name: Player's first name
            last_name: Player's last name
            birth_date: Player's birth date
            exclude_email: Email to exclude (the current registration's email)

        Returns:
            List of potentially matching Player records
        """
        from app.utils.encryption import hash_for_lookup

        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_h = hash_for_lookup(name_normalized)

        query = cls.query.filter(
            cls.name_hash == name_h,
            cls.birth_date == birth_date
        )

        # Exclude records with the same email (those are exact matches, not potential)
        if exclude_email:
            email_hash = hash_for_lookup(exclude_email)
            query = query.filter(cls.parent_email_hash != email_hash)

        return query.all()

    @classmethod
    def generate_player_code(cls, first_name, last_name, birth_date):
        """Generate player code like 'bennluk1810' (last4 + first3 + MMYY).

        If the generated code already exists, appends a number.
        """
        last_part = (last_name or 'xxxx')[:4].lower()
        first_part = (first_name or 'xxx')[:3].lower()
        date_part = birth_date.strftime('%m%y') if birth_date else '0000'
        base_code = f"{last_part}{first_part}{date_part}"

        # Check if exists and add suffix if needed
        existing = cls.query.filter(cls.player_code.like(f'{base_code}%')).count()
        if existing == 0:
            return base_code
        return f"{base_code}{existing + 1}"

    @classmethod
    def get_or_create(cls, parent_email, first_name, last_name, birth_date,
                      gender=None, program=None, parent_first_name=None,
                      parent_last_name=None, parent_phone=None,
                      secondary_email=None, player_code=None):
        """Find existing player or create new one.

        Uses parent_email + player name as composite key.
        """
        player = cls.find_by_email_and_name(parent_email, first_name, last_name)
        if player:
            # Update any missing fields
            if gender and not player.gender:
                player.gender = gender
            if program and not player.program:
                player.program = program
            if secondary_email and not player.secondary_email:
                player.secondary_email = secondary_email
            if parent_first_name and not player.parent_first_name:
                player.parent_first_name = parent_first_name
            if parent_last_name and not player.parent_last_name:
                player.parent_last_name = parent_last_name
            if parent_phone and not player.parent_phone:
                player.parent_phone = parent_phone
            return player

        # Create new player
        player = cls(
            birth_date=birth_date,
            gender=gender,
            program=program
        )
        player.first_name = first_name
        player.last_name = last_name
        player.parent_email = parent_email
        player.secondary_email = secondary_email
        player.parent_first_name = parent_first_name
        player.parent_last_name = parent_last_name
        player.parent_phone = parent_phone

        # Use provided player_code or generate one
        if player_code:
            player.player_code = player_code
        else:
            player.player_code = cls.generate_player_code(first_name, last_name, birth_date)

        db.session.add(player)
        return player

    def link_to_parent_user(self, user):
        """Link this player to a parent user account."""
        self.parent_user_id = user.ID
        self.parent_user = user

    def merge_from(self, other_player):
        """Merge another player record into this one.

        Moves all related records (seasons, evaluations, stats) from other_player
        to this player, then deletes other_player.

        Args:
            other_player: The Player record to merge into this one

        Returns:
            dict with merge statistics
        """
        from app.models.pitching_stats import PitchingStats

        stats = {
            'seasons_moved': 0,
            'evaluations_moved': 0,
            'pitching_stats_moved': 0,
            'email_added': False
        }

        # Add other player's email as secondary if we don't have one
        if other_player.parent_email:
            if not self.secondary_email:
                self.secondary_email = other_player.parent_email
                stats['email_added'] = True
            elif not self._emails_match(self.secondary_email, other_player.parent_email):
                # If secondary is already set to a different email, we can't add another
                # Just log it - the email won't be preserved
                pass

        # Move PlayerSeason records
        for season in other_player.seasons:
            # Check if this player already has a record for this season
            existing = PlayerSeason.query.filter_by(
                player_id=self.id,
                org_season_id=season.org_season_id
            ).first()
            if existing:
                # Merge: keep existing, but copy over any data that's missing
                if season.team_id and not existing.team_id:
                    existing.team_id = season.team_id
                if season.placed_league_id and not existing.placed_league_id:
                    existing.placed_league_id = season.placed_league_id
                if season.prior_league_id and not existing.prior_league_id:
                    existing.prior_league_id = season.prior_league_id
                # Delete the duplicate season record
                db.session.delete(season)
            else:
                # Move the season record to this player
                season.player_id = self.id
            stats['seasons_moved'] += 1

        # Move PlayerEvaluation records
        for evaluation in other_player.evaluations:
            # Check if this player already has an evaluation for this season
            existing = PlayerEvaluation.query.filter_by(
                player_id=self.id,
                org_season_id=evaluation.org_season_id
            ).first()
            if existing:
                # Keep the existing evaluation (first one wins)
                db.session.delete(evaluation)
            else:
                evaluation.player_id = self.id
            stats['evaluations_moved'] += 1

        # Move PitchingStats records
        pitching_stats = PitchingStats.query.filter_by(player_id=other_player.id).all()
        for ps in pitching_stats:
            ps.player_id = self.id
            stats['pitching_stats_moved'] += 1

        # Flush to ensure FK constraints are satisfied before delete
        db.session.flush()

        # Delete the merged player
        db.session.delete(other_player)

        return stats

    def _emails_match(self, email1, email2):
        """Check if two emails are the same (case-insensitive)."""
        if not email1 or not email2:
            return False
        return email1.lower().strip() == email2.lower().strip()


class PlayerSeason(db.Model):
    """
    Player's participation in a specific season.
    Links player to org_season and tracks division/team assignment.
    """
    __tablename__ = 'sdll_player_seasons'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('sdll_players.id'), nullable=False)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'), nullable=False)

    # Registration info
    registration_division = db.Column(db.String(50))  # "League Age 10 Baseball" from registration

    # League assignment (FK to sdll_leagues)
    # prior_league_id = what they played last season (from registration form)
    # placed_league_id = what league they're placed in after evaluations
    prior_league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'))
    placed_league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'))

    # Team assignment (after draft)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'))

    # Coach recommendation from previous season
    coach_division_rec = db.Column(db.String(30))

    # Status tracking
    # registered -> evaluated -> placed -> drafted (assigned to team)
    status = db.Column(db.String(20), default='registered')

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    # Relationships
    player = db.relationship('Player', back_populates='season_records')
    org_season = db.relationship('OrgSeason', backref='player_seasons')
    prior_league = db.relationship('League', foreign_keys=[prior_league_id])
    placed_league = db.relationship('League', foreign_keys=[placed_league_id])
    team = db.relationship('TeamSeason', backref='players')

    # Unique constraint: one record per player per season
    __table_args__ = (
        db.UniqueConstraint('player_id', 'org_season_id', name='uq_player_org_season'),
    )

    @property
    def league_age(self):
        """Calculate league age for this season."""
        return self.player.league_age(self.org_season) if self.player and self.org_season else None

    @property
    def effective_league_id(self):
        """Get the effective league ID: team's league if assigned, otherwise placed_league_id."""
        if self.team_id and self.team:
            return self.team.league_id
        if self.placed_league_id:
            return self.placed_league_id
        return None

    @property
    def effective_league(self):
        """Get the effective league: team's league if assigned, otherwise placed_league."""
        if self.team_id and self.team:
            return self.team.league_rel
        if self.placed_league_id:
            return self.placed_league
        return None

    @property
    def effective_status(self):
        """Get the effective status: drafted if has team_id, otherwise stored status.

        This ensures players with a team assignment are always shown as 'drafted'
        even if their stored status is out of sync.
        """
        if self.status == 'withdrawn':
            return 'withdrawn'
        if self.team_id:
            return 'drafted'
        return self.status or 'registered'

    def __repr__(self):
        return f'<PlayerSeason player={self.player_id} season={self.org_season_id}>'

    @classmethod
    def get_or_create(cls, player, org_season, registration_division=None,
                      prior_league_id=None, status='registered'):
        """Find existing season record or create new one."""
        record = cls.query.filter_by(
            player_id=player.id,
            org_season_id=org_season.ID
        ).first()

        if record:
            # Update fields if provided
            if registration_division:
                record.registration_division = registration_division
            if prior_league_id:
                record.prior_league_id = prior_league_id
            return record

        record = cls(
            player_id=player.id,
            org_season_id=org_season.ID,
            registration_division=registration_division,
            prior_league_id=prior_league_id,
            status=status
        )
        db.session.add(record)
        return record


class EvaluationMetricAgeRange(db.Model):
    """Age-specific score ranges for evaluation metrics.

    Allows different score ranges (min/max/increment) for different age groups.
    For example, younger players (ages 4-6) might use a 1-3 scale while
    older players (ages 10-12) use the full 1-7 scale.
    """
    __tablename__ = 'sdll_evaluation_metric_age_ranges'

    id = db.Column(db.Integer, primary_key=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('sdll_evaluation_metrics.id',
                                                     ondelete='CASCADE'), nullable=False)

    # Age range (inclusive)
    min_age = db.Column(db.SmallInteger, nullable=False)  # e.g., 4
    max_age = db.Column(db.SmallInteger, nullable=False)  # e.g., 6

    # Score range for this age group
    min_score = db.Column(db.Numeric(3, 1), nullable=False)
    max_score = db.Column(db.Numeric(3, 1), nullable=False)
    score_increment = db.Column(db.Numeric(2, 1), nullable=False, default=0.5)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    metric = db.relationship('EvaluationMetric', back_populates='age_ranges')

    __table_args__ = (
        db.UniqueConstraint('metric_id', 'min_age', 'max_age', name='uq_metric_age_range'),
    )

    def __repr__(self):
        return f'<EvaluationMetricAgeRange metric={self.metric_id} ages={self.min_age}-{self.max_age}>'

    @property
    def age_range_display(self):
        """Display string for the age range."""
        if self.min_age == self.max_age:
            return f'Age {self.min_age}'
        return f'Ages {self.min_age}-{self.max_age}'


class EvaluationMetric(db.Model):
    """
    Defines evaluation metrics (what skills are measured and how).
    Allows adding new metrics without schema changes.
    """
    __tablename__ = 'sdll_evaluation_metrics'

    id = db.Column(db.Integer, primary_key=True)

    # Metric identity
    name = db.Column(db.String(30), unique=True, nullable=False)  # Internal key
    display_name = db.Column(db.String(50), nullable=False)       # UI display name
    description = db.Column(db.Text)                              # How to measure

    # Categorization
    category = db.Column(db.String(30))           # "batting", "fielding", "pitching", "running"
    program = db.Column(db.String(20), default='both')  # "baseball", "softball", "both"

    # Scoring rules (default fallback when no age-specific range matches)
    min_score = db.Column(db.Numeric(3, 1), default=1.0)
    max_score = db.Column(db.Numeric(3, 1), default=7.0)
    score_increment = db.Column(db.Numeric(2, 1), default=0.5)

    # Display
    sort_order = db.Column(db.Integer, default=100)
    active = db.Column(db.SmallInteger, default=1)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    # Relationships
    scores = db.relationship('PlayerEvaluationScore', back_populates='metric', lazy='dynamic')
    age_ranges = db.relationship('EvaluationMetricAgeRange', back_populates='metric',
                                 lazy='joined', cascade='all, delete-orphan',
                                 order_by='EvaluationMetricAgeRange.min_age')

    def __repr__(self):
        return f'<EvaluationMetric {self.name}: {self.display_name}>'

    def get_score_range(self, league_age=None):
        """Get min/max/increment for a specific league age, or default if no override.

        Args:
            league_age: Player's league age. If None, returns default range.

        Returns:
            dict with 'min', 'max', 'increment' keys (float values)
        """
        if league_age is not None:
            for ar in self.age_ranges:
                if ar.min_age <= league_age <= ar.max_age:
                    return {
                        'min': float(ar.min_score),
                        'max': float(ar.max_score),
                        'increment': float(ar.score_increment)
                    }
        # Default fallback (use column defaults if not set)
        return {
            'min': float(self.min_score) if self.min_score is not None else 1.0,
            'max': float(self.max_score) if self.max_score is not None else 7.0,
            'increment': float(self.score_increment) if self.score_increment is not None else 0.5
        }

    def validate_score(self, score, league_age=None):
        """Check if a score is valid for the given league age.

        Args:
            score: The score to validate
            league_age: Player's league age

        Returns:
            tuple (is_valid, error_message)
        """
        range_info = self.get_score_range(league_age)
        min_score = range_info['min']
        max_score = range_info['max']

        if score < min_score or score > max_score:
            return False, f"Score must be between {min_score} and {max_score}"
        return True, None

    @classmethod
    def get_active(cls, program=None):
        """Get all active metrics, optionally filtered by program."""
        query = cls.query.filter_by(active=1)
        if program:
            query = query.filter(
                (cls.program == program) | (cls.program == 'both')
            )
        return query.order_by(cls.sort_order).all()

    @classmethod
    def get_by_name(cls, name):
        """Find metric by internal name."""
        return cls.query.filter_by(name=name).first()

    @classmethod
    def get_by_category(cls, category, program=None):
        """Get metrics for a category (batting, fielding, etc.)."""
        query = cls.query.filter_by(category=category, active=1)
        if program:
            query = query.filter(
                (cls.program == program) | (cls.program == 'both')
            )
        return query.order_by(cls.sort_order).all()


class PlayerEvaluationScore(db.Model):
    """
    Individual score for a player evaluation on a specific metric.
    Links PlayerEvaluation to EvaluationMetric.
    """
    __tablename__ = 'sdll_player_evaluation_scores'

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('sdll_player_evaluations.id',
                                                         ondelete='CASCADE'), nullable=False)
    metric_id = db.Column(db.Integer, db.ForeignKey('sdll_evaluation_metrics.id'), nullable=False)
    score = db.Column(db.Numeric(3, 1))

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    evaluation = db.relationship('PlayerEvaluation', back_populates='scores')
    metric = db.relationship('EvaluationMetric', back_populates='scores')

    # Unique constraint: one score per metric per evaluation
    __table_args__ = (
        db.UniqueConstraint('evaluation_id', 'metric_id', name='uq_eval_metric'),
    )

    def __repr__(self):
        return f'<PlayerEvaluationScore eval={self.evaluation_id} {self.metric.name}={self.score}>'


class PlayerEvaluation(db.Model):
    """
    Player evaluation header/parent record.
    Scores are stored in PlayerEvaluationScore via flexible metrics system.
    """
    __tablename__ = 'sdll_player_evaluations'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('sdll_players.id'), nullable=False)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'), nullable=False)

    # Evaluation metadata
    eval_date = db.Column(db.Date)
    eval_session = db.Column(db.String(30))  # "Cactus", "Gila", etc. (eval group name)
    evaluator_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Overall/average score (calculated from individual metric scores)
    overall_score = db.Column(db.Numeric(3, 2))

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, onupdate=db.func.current_timestamp())

    # Relationships
    player = db.relationship('Player', back_populates='evaluations')
    org_season = db.relationship('OrgSeason', backref='player_evaluations')
    evaluator = db.relationship('User', backref='evaluations_given')
    scores = db.relationship('PlayerEvaluationScore', back_populates='evaluation',
                             lazy='joined', cascade='all, delete-orphan')

    def calculate_overall_score(self):
        """Calculate average of all scores from the flexible scores table."""
        score_values = [float(s.score) for s in self.scores if s.score is not None]

        if score_values:
            self.overall_score = sum(score_values) / len(score_values)
        else:
            self.overall_score = None
        return self.overall_score

    @property
    def score_dict(self):
        """Return scores as a dictionary {metric_name: score}."""
        return {s.metric.name: float(s.score) if s.score else None for s in self.scores}

    @property
    def scores_by_category(self):
        """Return scores grouped by category."""
        result = {}
        for s in self.scores:
            category = s.metric.category or 'other'
            if category not in result:
                result[category] = {}
            result[category][s.metric.name] = {
                'display_name': s.metric.display_name,
                'score': float(s.score) if s.score else None
            }
        return result

    def get_score(self, metric_name):
        """Get score for a specific metric by name."""
        for s in self.scores:
            if s.metric.name == metric_name:
                return float(s.score) if s.score else None
        return None

    def set_score(self, metric_name, value):
        """Set score for a specific metric by name."""
        metric = EvaluationMetric.get_by_name(metric_name)
        if not metric:
            raise ValueError(f"Unknown metric: {metric_name}")

        # Find existing score or create new
        for s in self.scores:
            if s.metric_id == metric.id:
                s.score = value
                return

        # Create new score
        score = PlayerEvaluationScore(
            evaluation_id=self.id,
            metric_id=metric.id,
            score=value
        )
        self.scores.append(score)

    @property
    def league_age(self):
        """Calculate league age at time of this evaluation's season."""
        return self.player.league_age(self.org_season) if self.player and self.org_season else None

    def __repr__(self):
        return f'<PlayerEvaluation player={self.player_id} season={self.org_season_id} avg={self.avg_score}>'

    @classmethod
    def create_for_player(cls, player, org_season, scores, eval_session=None,
                          eval_date=None, evaluator_id=None, notes=None):
        """Create evaluation record with scores dict.

        Args:
            player: Player instance
            org_season: OrgSeason instance
            scores: dict with metric names as keys (e.g., {'contact': 4.5, 'power': 3.0})
            eval_session: Evaluation group name (e.g., "Cactus")
            eval_date: Date of evaluation
            evaluator_id: User ID of evaluator
            notes: Additional notes

        Returns:
            PlayerEvaluation instance
        """
        evaluation = cls(
            player_id=player.id,
            org_season_id=org_season.ID,
            eval_session=eval_session,
            eval_date=eval_date,
            evaluator_id=evaluator_id,
            notes=notes
        )
        db.session.add(evaluation)
        db.session.flush()  # Get the evaluation ID

        # Add scores using flexible metrics
        for metric_name, value in scores.items():
            if value is not None:
                metric = EvaluationMetric.get_by_name(metric_name)
                if metric:
                    score = PlayerEvaluationScore(
                        evaluation_id=evaluation.id,
                        metric_id=metric.id,
                        score=value
                    )
                    db.session.add(score)
                    evaluation.scores.append(score)

        evaluation.calculate_overall_score()
        return evaluation
