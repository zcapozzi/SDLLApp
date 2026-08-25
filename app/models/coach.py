"""Coach models - coach users and team assignments."""

from datetime import datetime
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class CoachUser(db.Model):
    """Links a user to coaching role with sport affiliation.

    This table tracks which users are registered as coaches and what
    sport(s) they coach (baseball, softball, or both).
    """
    __tablename__ = 'sdll_coaches'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=False)
    sport = db.Column(db.Enum('baseball', 'softball', 'both'), nullable=False)
    season_year = db.Column(db.Integer, default=2026)
    is_spring = db.Column(db.SmallInteger, default=1)
    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to User
    user = db.relationship('User', backref=db.backref('coach_records', lazy='dynamic'))

    def __repr__(self):
        return f'<CoachUser {self.id} user={self.user_id} sport={self.sport}>'

    @classmethod
    def get_active_coaches(cls, season_year=None, is_spring=None, sport=None):
        """Get all active coaches, optionally filtered by season and sport."""
        query = cls.query.filter_by(active=1)

        if season_year:
            query = query.filter_by(season_year=season_year)
        if is_spring is not None:
            query = query.filter_by(is_spring=is_spring)
        if sport:
            query = query.filter(
                (cls.sport == sport) | (cls.sport == 'both')
            )

        return query.all()

    @classmethod
    def get_by_user(cls, user_id, season_year=None, is_spring=None):
        """Get coach record for a specific user."""
        query = cls.query.filter_by(user_id=user_id, active=1)

        if season_year:
            query = query.filter_by(season_year=season_year)
        if is_spring is not None:
            query = query.filter_by(is_spring=is_spring)

        return query.first()

    @property
    def season_name(self):
        """Get formatted season name."""
        season_type = 'Spring' if self.is_spring else 'Fall'
        return f"{season_type} {self.season_year}"


class CoachSeason(db.Model):
    """Coach assignment to a team for a season.

    Stores coach contact information for emergency notifications
    (e.g., when umpire is missing).
    """
    __tablename__ = 'sdll_coach_seasons'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID',
                                                      ondelete='CASCADE'), nullable=False)

    # Coach info (encrypted)
    _name = db.Column('name', db.String(500), nullable=False)
    _email = db.Column('email', db.String(500))
    email_hash = db.Column(db.String(64))
    _phone = db.Column('phone', db.String(500))

    # Role
    role = db.Column(db.String(20), default='head')  # 'head', 'assistant'

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    team = db.relationship('TeamSeason', backref='coaches')

    # Role constants
    ROLE_HEAD = 'head'
    ROLE_ASSISTANT = 'assistant'
    ROLES = [ROLE_HEAD, ROLE_ASSISTANT]

    def __repr__(self):
        return f'<CoachSeason {self.id}: team={self.team_id} role={self.role}>'

    # Name property with encryption
    @property
    def name(self):
        return decrypt_value(self._name) if self._name else None

    @name.setter
    def name(self, value):
        self._name = encrypt_value(value) if value else None

    # Email property with encryption
    @property
    def email(self):
        return decrypt_value(self._email) if self._email else None

    @email.setter
    def email(self, value):
        if value:
            self._email = encrypt_value(value)
            self.email_hash = hash_for_lookup(value)
        else:
            self._email = None
            self.email_hash = None

    # Phone property with encryption
    @property
    def phone(self):
        return decrypt_value(self._phone) if self._phone else None

    @phone.setter
    def phone(self, value):
        self._phone = encrypt_value(value) if value else None

    @property
    def is_head_coach(self):
        """Check if this is the head coach."""
        return self.role == self.ROLE_HEAD

    @classmethod
    def get_for_team(cls, team_id):
        """Get all coaches for a team."""
        return cls.query.filter_by(team_id=team_id).order_by(cls.role).all()

    @classmethod
    def get_head_coach(cls, team_id):
        """Get head coach for a team."""
        return cls.query.filter_by(team_id=team_id, role=cls.ROLE_HEAD).first()
