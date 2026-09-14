"""Training Completion model - tracks who has completed which trainings."""

from datetime import datetime, date, timedelta
from app.extensions import db


class TrainingCompletion(db.Model):
    """Tracks completion of required trainings by users and umpires.

    Supports both:
    - Users with accounts (user_id set)
    - Managed umpires without accounts (umpire_profile_id set)
    """
    __tablename__ = 'sdll_training_completions'

    id = db.Column(db.Integer, primary_key=True)
    training_type_id = db.Column(db.Integer, db.ForeignKey('sdll_training_types.id',
                                                           ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'))
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id',
                                                             ondelete='CASCADE'))

    completed_at = db.Column(db.Date, nullable=False)
    expires_at = db.Column(db.Date)  # Computed from training_type.expires_after_days
    verification_notes = db.Column(db.Text)  # Certificate number, etc.
    verified_by = db.Column(db.BigInteger)  # User ID who recorded this

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    training_type = db.relationship('TrainingType', back_populates='completions')
    user = db.relationship('User', backref='training_completions')
    umpire_profile = db.relationship('UmpireProfile', backref='training_completions')

    def __repr__(self):
        target = f'user={self.user_id}' if self.user_id else f'umpire={self.umpire_profile_id}'
        return f'<TrainingCompletion {self.training_type_id} {target}>'

    @property
    def is_expired(self):
        """Check if this training completion has expired."""
        if not self.expires_at:
            return False
        return date.today() > self.expires_at

    @property
    def is_valid(self):
        """Check if training is currently valid (completed and not expired)."""
        return not self.is_expired

    @property
    def days_until_expiry(self):
        """Days until expiration, or None if never expires."""
        if not self.expires_at:
            return None
        delta = self.expires_at - date.today()
        return delta.days

    @property
    def expiry_status(self):
        """Human-readable expiry status."""
        if not self.expires_at:
            return 'Never expires'
        days = self.days_until_expiry
        if days < 0:
            return f'Expired {abs(days)} days ago'
        elif days == 0:
            return 'Expires today'
        elif days <= 30:
            return f'Expires in {days} days'
        elif days <= 90:
            return f'Expires in {days // 7} weeks'
        else:
            return f'Expires {self.expires_at.strftime("%b %d, %Y")}'

    @property
    def person_name(self):
        """Get name of person who completed the training."""
        if self.user:
            return self.user.name
        if self.umpire_profile:
            return self.umpire_profile.name
        return 'Unknown'

    def compute_expiry(self):
        """Calculate and set expires_at based on training type."""
        if self.training_type and self.training_type.expires_after_days:
            self.expires_at = self.completed_at + timedelta(days=self.training_type.expires_after_days)
        else:
            self.expires_at = None

    @classmethod
    def record_completion(cls, training_type_id, completed_at, user_id=None, umpire_profile_id=None,
                          verification_notes=None, verified_by=None):
        """Record a training completion.

        Updates existing record if found, creates new one otherwise.
        """
        if not user_id and not umpire_profile_id:
            raise ValueError("Either user_id or umpire_profile_id must be provided")

        # Look for existing
        query = cls.query.filter_by(training_type_id=training_type_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        else:
            query = query.filter_by(umpire_profile_id=umpire_profile_id)

        existing = query.first()

        if existing:
            existing.completed_at = completed_at
            existing.verification_notes = verification_notes
            existing.verified_by = verified_by
            existing.compute_expiry()
            db.session.commit()
            return existing

        # Create new
        completion = cls(
            training_type_id=training_type_id,
            user_id=user_id,
            umpire_profile_id=umpire_profile_id,
            completed_at=completed_at,
            verification_notes=verification_notes,
            verified_by=verified_by
        )
        completion.compute_expiry()
        db.session.add(completion)
        db.session.commit()
        return completion

    @classmethod
    def get_for_user(cls, user_id):
        """Get all training completions for a user."""
        return cls.query.filter_by(user_id=user_id).all()

    @classmethod
    def get_for_umpire(cls, umpire_profile_id):
        """Get all training completions for an umpire profile."""
        return cls.query.filter_by(umpire_profile_id=umpire_profile_id).all()

    @classmethod
    def get_valid_for_user(cls, user_id):
        """Get valid (non-expired) completions for a user."""
        today = date.today()
        return cls.query.filter(
            cls.user_id == user_id,
            db.or_(cls.expires_at.is_(None), cls.expires_at >= today)
        ).all()

    @classmethod
    def get_valid_for_umpire(cls, umpire_profile_id):
        """Get valid (non-expired) completions for an umpire profile."""
        today = date.today()
        return cls.query.filter(
            cls.umpire_profile_id == umpire_profile_id,
            db.or_(cls.expires_at.is_(None), cls.expires_at >= today)
        ).all()

    @classmethod
    def has_valid_training(cls, training_type_id, user_id=None, umpire_profile_id=None):
        """Check if person has valid completion for a training type."""
        today = date.today()
        query = cls.query.filter(
            cls.training_type_id == training_type_id,
            db.or_(cls.expires_at.is_(None), cls.expires_at >= today)
        )
        if user_id:
            query = query.filter(cls.user_id == user_id)
        elif umpire_profile_id:
            query = query.filter(cls.umpire_profile_id == umpire_profile_id)
        else:
            return False

        return query.count() > 0

    @classmethod
    def get_expiring_soon(cls, days=30):
        """Get completions expiring within the specified days."""
        today = date.today()
        cutoff = today + timedelta(days=days)
        return cls.query.filter(
            cls.expires_at.isnot(None),
            cls.expires_at >= today,
            cls.expires_at <= cutoff
        ).order_by(cls.expires_at).all()
