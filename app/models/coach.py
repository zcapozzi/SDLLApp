"""Coach model - coach contact information per team per season."""

from datetime import datetime
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


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
