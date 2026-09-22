"""Coach models - coach users and team assignments."""

from datetime import datetime
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class CoachUser(db.Model):
    """Links a user to coaching role with sport affiliation.

    This table tracks which users are registered as coaches and what
    sport(s) they coach (baseball, softball, or both).

    Season assignments are handled via sdll_coach_seasons which links
    coaches to specific team seasons.
    """
    __tablename__ = 'sdll_coaches'

    # Status values
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_PENDING = 'pending'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=False)
    sport = db.Column(db.Enum('baseball', 'softball', 'both'), nullable=False)
    status = db.Column(db.String(15), default=STATUS_ACTIVE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to User
    user = db.relationship('User', backref=db.backref('coach_records', lazy='dynamic'))

    def __repr__(self):
        return f'<CoachUser {self.id} user={self.user_id} sport={self.sport}>'

    @property
    def is_active(self):
        """Check if coach is active."""
        return self.status == self.STATUS_ACTIVE

    @classmethod
    def get_active_coaches(cls, sport=None):
        """Get all active coaches, optionally filtered by sport."""
        query = cls.query.filter_by(status=cls.STATUS_ACTIVE)

        if sport:
            query = query.filter(
                (cls.sport == sport) | (cls.sport == 'both')
            )

        return query.all()

    @classmethod
    def get_by_user(cls, user_id):
        """Get coach record for a specific user."""
        return cls.query.filter_by(user_id=user_id).first()


class CoachSeason(db.Model):
    """Coach assignment to a team for a season.

    Links a coach (from sdll_coaches) to a team season.
    Contact info (email, phone) should be retrieved from the linked User account
    via coach.coach.user.email / coach.coach.user.phone.
    """
    __tablename__ = 'sdll_coach_seasons'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID',
                                                      ondelete='CASCADE'), nullable=False)
    coach_id = db.Column(db.BigInteger, db.ForeignKey('sdll_coaches.id',
                                                       ondelete='SET NULL'), nullable=True)

    # Coach name for display (encrypted)
    _name = db.Column('name', db.String(500), nullable=False)

    # DEPRECATED: email/phone columns exist in DB but are no longer used.
    # Contact info should be fetched from User via coach.coach.user.email
    # These columns can be dropped from the database.
    # _email = db.Column('email', db.String(500))
    # email_hash = db.Column(db.String(64))
    # _phone = db.Column('phone', db.String(500))

    # Role
    role = db.Column(db.String(20), default='head')  # 'head', 'assistant'

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    team = db.relationship('TeamSeason', backref='coaches')
    coach = db.relationship('CoachUser', backref=db.backref('team_assignments', lazy='dynamic'))

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
