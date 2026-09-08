"""UmpireGroupAssignment model - tracks Assignr group memberships for umpires."""

from datetime import datetime
from app.extensions import db


class UmpireGroupAssignment(db.Model):
    """Tracks which Assignr groups an umpire belongs to.

    This allows flexible tracking of any Assignr group, not just predefined ones.
    Groups are synced bidirectionally with the Assignr API.
    """
    __tablename__ = 'sdll_umpire_group_assignments'

    id = db.Column(db.Integer, primary_key=True)
    umpire_profile_id = db.Column(
        db.Integer,
        db.ForeignKey('sdll_umpire_profiles.id', ondelete='CASCADE'),
        nullable=False
    )
    assignr_group_id = db.Column(db.Integer, nullable=False)
    assignr_group_name = db.Column(db.String(100))  # Cached for display
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    umpire_profile = db.relationship(
        'UmpireProfile',
        backref=db.backref('group_assignments', lazy='dynamic', cascade='all, delete-orphan')
    )

    # Unique constraint - one assignment per profile/group combo
    __table_args__ = (
        db.UniqueConstraint('umpire_profile_id', 'assignr_group_id', name='uq_umpire_group'),
    )

    def __repr__(self):
        return f'<UmpireGroupAssignment profile={self.umpire_profile_id} group={self.assignr_group_id}>'

    @classmethod
    def get_for_profile(cls, profile_id):
        """Get all group assignments for an umpire profile."""
        return cls.query.filter_by(umpire_profile_id=profile_id).all()

    @classmethod
    def get_group_ids_for_profile(cls, profile_id):
        """Get list of group IDs for an umpire profile."""
        assignments = cls.query.filter_by(umpire_profile_id=profile_id).all()
        return [a.assignr_group_id for a in assignments]

    @classmethod
    def has_group(cls, profile_id, group_id):
        """Check if a profile has a specific group assignment."""
        return cls.query.filter_by(
            umpire_profile_id=profile_id,
            assignr_group_id=group_id
        ).first() is not None

    @classmethod
    def add_group(cls, profile_id, group_id, group_name=None):
        """Add a group assignment for an umpire profile.

        Returns:
            Tuple of (assignment, created) where created is True if new
        """
        existing = cls.query.filter_by(
            umpire_profile_id=profile_id,
            assignr_group_id=group_id
        ).first()

        if existing:
            # Update name if provided
            if group_name and existing.assignr_group_name != group_name:
                existing.assignr_group_name = group_name
                db.session.commit()
            return existing, False

        assignment = cls(
            umpire_profile_id=profile_id,
            assignr_group_id=group_id,
            assignr_group_name=group_name
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment, True

    @classmethod
    def remove_group(cls, profile_id, group_id):
        """Remove a group assignment for an umpire profile.

        Returns:
            True if removed, False if didn't exist
        """
        assignment = cls.query.filter_by(
            umpire_profile_id=profile_id,
            assignr_group_id=group_id
        ).first()

        if assignment:
            db.session.delete(assignment)
            db.session.commit()
            return True
        return False

    @classmethod
    def sync_from_list(cls, profile_id, group_ids, group_lookup=None):
        """Sync a profile's groups to match a list of group IDs.

        Args:
            profile_id: The umpire profile ID
            group_ids: List of Assignr group IDs the profile should have
            group_lookup: Optional dict of group_id -> group_name for caching names

        Returns:
            Tuple of (added_count, removed_count)
        """
        group_lookup = group_lookup or {}
        current = set(cls.get_group_ids_for_profile(profile_id))
        target = set(group_ids)

        added = 0
        removed = 0

        # Add missing groups
        for gid in target - current:
            cls.add_group(profile_id, gid, group_lookup.get(gid))
            added += 1

        # Remove extra groups
        for gid in current - target:
            cls.remove_group(profile_id, gid)
            removed += 1

        return added, removed
