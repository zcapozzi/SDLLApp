"""ScheduleProposal model for persistent schedule proposals."""

import json
from datetime import datetime
from app.extensions import db


class ScheduleProposal(db.Model):
    """Stores schedule proposals in the database for persistence and sharing.

    Replaces session-based storage which was:
    - Per-user (not shared)
    - Lost on server restart
    - Subject to session expiration
    """

    __tablename__ = 'sdll_schedule_proposals'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data = db.Column(db.JSON, nullable=False)

    # Status constants
    STATUS_DRAFT = 'draft'
    STATUS_REVIEW = 'review'
    STATUS_ACCEPTED = 'accepted'

    @classmethod
    def get_for_season(cls, year, is_spring):
        """Get the current proposal for a season.

        Returns the most recent draft/review proposal, or None if no active proposal.
        Uses a two-step query to avoid sorting large JSON data in memory.
        """
        # First get just the ID (small column, efficient sort)
        result = db.session.execute(
            db.text("""
                SELECT ID FROM sdll_schedule_proposals
                WHERE year = :year AND is_spring = :is_spring
                AND status IN ('draft', 'review')
                ORDER BY updated_at DESC
                LIMIT 1
            """),
            {'year': year, 'is_spring': is_spring}
        ).fetchone()

        if not result:
            return None

        # Then load the full row by ID (no sorting needed)
        return cls.query.get(result[0])

    @classmethod
    def create_or_update(cls, year, is_spring, data, user_id=None):
        """Create or update the proposal for a season.

        If a draft/review proposal exists, it will be updated.
        Otherwise, a new proposal is created.
        """
        proposal = cls.get_for_season(year, is_spring)

        if proposal:
            # Update existing proposal
            proposal.data = data
            proposal.updated_at = datetime.utcnow()
            if user_id:
                proposal.created_by = user_id
        else:
            # Create new proposal
            proposal = cls(
                year=year,
                is_spring=is_spring,
                status=cls.STATUS_REVIEW,
                created_by=user_id,
                data=data
            )
            db.session.add(proposal)

        db.session.commit()
        return proposal

    @classmethod
    def delete_for_season(cls, year, is_spring):
        """Delete all draft/review proposals for a season."""
        cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).filter(
            cls.status.in_([cls.STATUS_DRAFT, cls.STATUS_REVIEW])
        ).delete()
        db.session.commit()

    @classmethod
    def mark_accepted(cls, year, is_spring):
        """Mark the proposal as accepted (schedule was saved)."""
        proposal = cls.get_for_season(year, is_spring)
        if proposal:
            proposal.status = cls.STATUS_ACCEPTED
            db.session.commit()

    @property
    def games(self):
        """Get games from the proposal data."""
        return self.data.get('games', []) if self.data else []

    @property
    def violations(self):
        """Get violations from the proposal data."""
        return self.data.get('violations', []) if self.data else []

    @property
    def warnings(self):
        """Get warnings from the proposal data."""
        return self.data.get('warnings', []) if self.data else []

    @property
    def summary(self):
        """Get summary from the proposal data."""
        return self.data.get('summary', {}) if self.data else {}

    @property
    def assignments(self):
        """Get assignments from the proposal data."""
        return self.data.get('assignments', {}) if self.data else {}
