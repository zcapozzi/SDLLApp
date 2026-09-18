"""UmpireBlockout model - dates when umpires are unavailable."""

from datetime import datetime, date
from app.extensions import db


class UmpireBlockout(db.Model):
    """Tracks dates when an umpire is NOT available to work.

    Umpires manage their own blockouts via the availability page.
    This helps the umpire coordinator know who might be able to
    pick up open games.
    """
    __tablename__ = 'sdll_umpire_blockouts'

    id = db.Column(db.Integer, primary_key=True)
    umpire_profile_id = db.Column(
        db.Integer,
        db.ForeignKey('sdll_umpire_profiles.id', ondelete='CASCADE'),
        nullable=False
    )
    blocked_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(100))  # Optional note
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    profile = db.relationship('UmpireProfile', backref=db.backref(
        'blockout_dates',
        lazy='dynamic',
        cascade='all, delete-orphan'
    ))

    def __repr__(self):
        return f'<UmpireBlockout {self.umpire_profile_id} blocked on {self.blocked_date}>'

    @classmethod
    def get_for_profile(cls, profile_id, start_date=None, end_date=None):
        """Get blockouts for a profile within optional date range.

        Args:
            profile_id: The umpire profile ID
            start_date: Optional start of range (inclusive)
            end_date: Optional end of range (inclusive)

        Returns:
            List of UmpireBlockout objects
        """
        query = cls.query.filter_by(umpire_profile_id=profile_id)

        if start_date:
            query = query.filter(cls.blocked_date >= start_date)
        if end_date:
            query = query.filter(cls.blocked_date <= end_date)

        return query.order_by(cls.blocked_date).all()

    @classmethod
    def get_blocked_dates(cls, profile_id, start_date=None, end_date=None):
        """Get just the dates (not full objects) for a profile.

        Args:
            profile_id: The umpire profile ID
            start_date: Optional start of range
            end_date: Optional end of range

        Returns:
            Set of date objects
        """
        blockouts = cls.get_for_profile(profile_id, start_date, end_date)
        return {b.blocked_date for b in blockouts}

    @classmethod
    def is_blocked(cls, profile_id, check_date):
        """Check if a specific date is blocked for an umpire.

        Args:
            profile_id: The umpire profile ID
            check_date: Date to check

        Returns:
            True if blocked, False otherwise
        """
        return cls.query.filter_by(
            umpire_profile_id=profile_id,
            blocked_date=check_date
        ).first() is not None

    @classmethod
    def set_blocked(cls, profile_id, block_date, reason=None):
        """Add a blockout date for an umpire.

        Args:
            profile_id: The umpire profile ID
            block_date: Date to block
            reason: Optional reason/note

        Returns:
            The UmpireBlockout object (created or existing)
        """
        existing = cls.query.filter_by(
            umpire_profile_id=profile_id,
            blocked_date=block_date
        ).first()

        if existing:
            # Update reason if provided
            if reason is not None:
                existing.reason = reason
                db.session.commit()
            return existing

        blockout = cls(
            umpire_profile_id=profile_id,
            blocked_date=block_date,
            reason=reason
        )
        db.session.add(blockout)
        db.session.commit()
        return blockout

    @classmethod
    def clear_blocked(cls, profile_id, block_date):
        """Remove a blockout date for an umpire.

        Args:
            profile_id: The umpire profile ID
            block_date: Date to unblock

        Returns:
            True if removed, False if wasn't blocked
        """
        blockout = cls.query.filter_by(
            umpire_profile_id=profile_id,
            blocked_date=block_date
        ).first()

        if blockout:
            db.session.delete(blockout)
            db.session.commit()
            return True
        return False

    @classmethod
    def set_blocked_range(cls, profile_id, start_date, end_date, reason=None):
        """Block a range of dates for an umpire.

        Args:
            profile_id: The umpire profile ID
            start_date: First date to block
            end_date: Last date to block (inclusive)
            reason: Optional reason for all dates

        Returns:
            Number of dates blocked
        """
        from datetime import timedelta

        count = 0
        current = start_date
        while current <= end_date:
            cls.set_blocked(profile_id, current, reason)
            count += 1
            current += timedelta(days=1)

        return count

    @classmethod
    def clear_blocked_range(cls, profile_id, start_date, end_date):
        """Clear blockouts for a range of dates.

        Args:
            profile_id: The umpire profile ID
            start_date: First date of range
            end_date: Last date of range (inclusive)

        Returns:
            Number of blockouts removed
        """
        result = cls.query.filter(
            cls.umpire_profile_id == profile_id,
            cls.blocked_date >= start_date,
            cls.blocked_date <= end_date
        ).delete()

        db.session.commit()
        return result

    @classmethod
    def get_available_umpires(cls, check_date, profile_ids=None):
        """Get umpire profile IDs that are NOT blocked on a date.

        Args:
            check_date: Date to check availability
            profile_ids: Optional list of profile IDs to check (default: all active)

        Returns:
            List of profile IDs that are available
        """
        from app.models.umpire_profile import UmpireProfile

        if profile_ids is None:
            # Get all active umpires
            active = UmpireProfile.query.filter_by(status='active').all()
            profile_ids = [p.id for p in active]

        # Find who is blocked
        blocked = cls.query.filter(
            cls.umpire_profile_id.in_(profile_ids),
            cls.blocked_date == check_date
        ).all()
        blocked_ids = {b.umpire_profile_id for b in blocked}

        # Return those not blocked
        return [pid for pid in profile_ids if pid not in blocked_ids]

    @classmethod
    def get_blocked_umpires(cls, check_date, profile_ids=None):
        """Get umpire profile IDs that ARE blocked on a date.

        Args:
            check_date: Date to check
            profile_ids: Optional list of profile IDs to check

        Returns:
            List of profile IDs that are blocked
        """
        query = cls.query.filter(cls.blocked_date == check_date)

        if profile_ids:
            query = query.filter(cls.umpire_profile_id.in_(profile_ids))

        return [b.umpire_profile_id for b in query.all()]
