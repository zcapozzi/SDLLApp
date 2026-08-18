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

    def update_game(self, game_id, new_field=None, new_time=None, new_date=None):
        """Update a game in the proposal.

        Args:
            game_id: ID of the game to update
            new_field: New field name (optional)
            new_time: New time as 'HH:MM' string (optional)
            new_date: New date as 'YYYY-MM-DD' string (optional)

        Returns:
            True if game was found and updated, False otherwise
        """
        if not self.data or 'games' not in self.data:
            return False

        games = self.data['games']
        for game in games:
            if game.get('id') == game_id:
                # Update field
                if new_field is not None:
                    game['field_name'] = new_field

                # Update date/time
                if new_date is not None or new_time is not None:
                    # Parse existing datetime
                    existing_dt = game.get('game_date', '')
                    if existing_dt:
                        existing_date = existing_dt[:10]  # YYYY-MM-DD
                        existing_time = existing_dt[11:16] if len(existing_dt) > 11 else '00:00'  # HH:MM
                    else:
                        existing_date = None
                        existing_time = '00:00'

                    # Apply new values
                    final_date = new_date if new_date is not None else existing_date
                    final_time = new_time if new_time is not None else existing_time

                    if final_date and final_time:
                        game['game_date'] = f'{final_date}T{final_time}:00'

                # Mark the data as modified (needed for SQLAlchemy to detect JSON changes)
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(self, 'data')

                db.session.commit()
                return True

        return False

    def find_game(self, game_id):
        """Find a game in the proposal by ID.

        Returns:
            The game dict if found, None otherwise
        """
        if not self.data or 'games' not in self.data:
            return None

        for game in self.data['games']:
            if game.get('id') == game_id:
                return game
        return None
