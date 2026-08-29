"""UmpireGuardian model - links guardians (parents) to umpire profiles they manage.

This enables a parent to manage multiple children's umpire profiles from a single
account, without each child needing their own email address.
"""

from datetime import datetime
from app.extensions import db


class UmpireGuardian(db.Model):
    """Links a guardian (parent) user to umpire profiles they manage.

    A guardian can manage multiple umpire profiles (multiple children).
    An umpire profile can have multiple guardians (both parents).
    """
    __tablename__ = 'sdll_umpire_guardians'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    guardian_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'),
                                  nullable=False)
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id', ondelete='CASCADE'),
                                   nullable=False)
    relationship = db.Column(db.String(50), default='parent')  # parent, guardian, other
    is_primary = db.Column(db.SmallInteger, default=1)  # Primary contact for notifications
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    guardian = db.relationship('User', backref=db.backref('managed_umpires', lazy='dynamic'))
    umpire_profile = db.relationship('UmpireProfile', backref=db.backref('guardians', lazy='dynamic'))

    # Relationship types
    REL_PARENT = 'parent'
    REL_GUARDIAN = 'guardian'
    REL_OTHER = 'other'
    RELATIONSHIPS = [REL_PARENT, REL_GUARDIAN, REL_OTHER]

    def __repr__(self):
        return f'<UmpireGuardian user={self.guardian_user_id} profile={self.umpire_profile_id}>'

    @classmethod
    def get_managed_profiles(cls, user_id):
        """Get all umpire profiles managed by a user.

        Args:
            user_id: The guardian's user ID

        Returns:
            List of UmpireProfile objects
        """
        from app.models.umpire_profile import UmpireProfile
        guardianships = cls.query.filter_by(guardian_user_id=user_id).all()
        profile_ids = [g.umpire_profile_id for g in guardianships]
        if not profile_ids:
            return []
        return UmpireProfile.query.filter(UmpireProfile.id.in_(profile_ids)).all()

    @classmethod
    def get_guardians_for_profile(cls, profile_id):
        """Get all guardians for an umpire profile.

        Args:
            profile_id: The umpire profile ID

        Returns:
            List of User objects
        """
        from app.models.user import User
        guardianships = cls.query.filter_by(umpire_profile_id=profile_id).all()
        user_ids = [g.guardian_user_id for g in guardianships]
        if not user_ids:
            return []
        return User.query.filter(User.ID.in_(user_ids)).all()

    @classmethod
    def add_guardian(cls, user_id, profile_id, relationship='parent', is_primary=True):
        """Add a guardian relationship.

        Args:
            user_id: The guardian's user ID
            profile_id: The umpire profile ID
            relationship: Type of relationship (parent, guardian, other)
            is_primary: Whether this is the primary contact

        Returns:
            UmpireGuardian object or None if already exists
        """
        existing = cls.query.filter_by(
            guardian_user_id=user_id,
            umpire_profile_id=profile_id
        ).first()

        if existing:
            return None

        guardian = cls(
            guardian_user_id=user_id,
            umpire_profile_id=profile_id,
            relationship=relationship,
            is_primary=1 if is_primary else 0
        )
        db.session.add(guardian)
        db.session.commit()
        return guardian

    @classmethod
    def remove_guardian(cls, user_id, profile_id):
        """Remove a guardian relationship.

        Args:
            user_id: The guardian's user ID
            profile_id: The umpire profile ID

        Returns:
            True if removed, False if not found
        """
        existing = cls.query.filter_by(
            guardian_user_id=user_id,
            umpire_profile_id=profile_id
        ).first()

        if not existing:
            return False

        db.session.delete(existing)
        db.session.commit()
        return True

    @classmethod
    def is_guardian_of(cls, user_id, profile_id):
        """Check if a user is a guardian of an umpire profile.

        Args:
            user_id: The user ID to check
            profile_id: The umpire profile ID

        Returns:
            True if user is a guardian of the profile
        """
        return cls.query.filter_by(
            guardian_user_id=user_id,
            umpire_profile_id=profile_id
        ).first() is not None
