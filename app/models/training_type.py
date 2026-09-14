"""Training Type model - lookup table for required trainings."""

from datetime import datetime
from app.extensions import db


class TrainingType(db.Model):
    """Defines types of training that can be required.

    Examples: Abuse Awareness, Background Check, First Aid, etc.
    """
    __tablename__ = 'sdll_training_types'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    required_for = db.Column(db.String(50), default='all')  # all, umpire, coach, volunteer
    expires_after_days = db.Column(db.Integer)  # NULL = never expires
    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    completions = db.relationship('TrainingCompletion', back_populates='training_type',
                                  cascade='all, delete-orphan')

    # Required for constants
    REQUIRED_FOR_ALL = 'all'
    REQUIRED_FOR_UMPIRE = 'umpire'
    REQUIRED_FOR_COACH = 'coach'
    REQUIRED_FOR_VOLUNTEER = 'volunteer'

    REQUIRED_FOR_OPTIONS = [
        (REQUIRED_FOR_ALL, 'All Volunteers'),
        (REQUIRED_FOR_UMPIRE, 'Umpires Only'),
        (REQUIRED_FOR_COACH, 'Coaches Only'),
        (REQUIRED_FOR_VOLUNTEER, 'General Volunteers'),
    ]

    def __repr__(self):
        return f'<TrainingType {self.code}>'

    @property
    def is_active(self):
        return self.active == 1

    @property
    def expires(self):
        """Check if this training type expires."""
        return self.expires_after_days is not None

    @property
    def expiration_display(self):
        """Human-readable expiration description."""
        if not self.expires_after_days:
            return 'Never expires'
        if self.expires_after_days == 365:
            return 'Expires after 1 year'
        if self.expires_after_days == 730:
            return 'Expires after 2 years'
        return f'Expires after {self.expires_after_days} days'

    @property
    def required_for_display(self):
        """Human-readable required_for value."""
        for code, label in self.REQUIRED_FOR_OPTIONS:
            if code == self.required_for:
                return label
        return self.required_for

    def is_required_for_role(self, role):
        """Check if training is required for a specific role."""
        if self.required_for == self.REQUIRED_FOR_ALL:
            return True
        return self.required_for == role

    @classmethod
    def get_active(cls):
        """Get all active training types."""
        return cls.query.filter_by(active=1).order_by(cls.name).all()

    @classmethod
    def get_by_code(cls, code):
        """Find training type by code."""
        return cls.query.filter_by(code=code).first()

    @classmethod
    def get_required_for_umpires(cls):
        """Get all trainings required for umpires."""
        return cls.query.filter(
            cls.active == 1,
            cls.required_for.in_([cls.REQUIRED_FOR_ALL, cls.REQUIRED_FOR_UMPIRE])
        ).order_by(cls.name).all()

    @classmethod
    def get_required_for_coaches(cls):
        """Get all trainings required for coaches."""
        return cls.query.filter(
            cls.active == 1,
            cls.required_for.in_([cls.REQUIRED_FOR_ALL, cls.REQUIRED_FOR_COACH])
        ).order_by(cls.name).all()
