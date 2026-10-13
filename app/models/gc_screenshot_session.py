"""GC Screenshot Session model - tracks GameChanger screenshot parsing for post-game reports."""

import json
from datetime import datetime
from app.extensions import db


class GCScreenshotSession(db.Model):
    """Tracks GameChanger screenshot upload and parsing sessions.

    Each upload attempt is recorded for audit and QC purposes.
    Multiple attempts for the same game/team share a session_uuid.

    Status flow: pending -> parsing -> parsed|error -> submitted|abandoned
    """
    __tablename__ = 'sdll_gc_screenshot_sessions'

    # Status values
    STATUS_PENDING = 'pending'
    STATUS_PARSING = 'parsing'
    STATUS_PARSED = 'parsed'
    STATUS_ERROR = 'error'
    STATUS_SUBMITTED = 'submitted'
    STATUS_ABANDONED = 'abandoned'

    id = db.Column(db.Integer, primary_key=True)

    # Session grouping (multiple attempts share same uuid)
    session_uuid = db.Column(db.String(36), nullable=False, index=True)
    attempt_number = db.Column(db.SmallInteger, nullable=False, default=1)

    # Context
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'),
                        nullable=False, index=True)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID', ondelete='CASCADE'),
                        nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'),
                        nullable=False, index=True)

    # Image storage (base64)
    image_data = db.Column(db.Text)  # MEDIUMTEXT in MySQL
    image_filename = db.Column(db.String(255))
    image_content_type = db.Column(db.String(50))

    # LLM interaction
    prompt_sent = db.Column(db.Text)
    llm_response = db.Column(db.Text)
    parsed_json = db.Column(db.JSON)

    # Final outcome
    final_submitted_json = db.Column(db.JSON)
    was_edited = db.Column(db.SmallInteger, default=0)
    edit_diff = db.Column(db.JSON)  # Field-level diff
    submission_successful = db.Column(db.SmallInteger, default=0)

    # Status
    status = db.Column(db.String(20), default=STATUS_PENDING, index=True)
    error_message = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    parsed_at = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime)

    # Relationships
    game = db.relationship('Game', backref=db.backref('gc_screenshot_sessions', lazy='dynamic'))
    team = db.relationship('TeamSeason', backref=db.backref('gc_screenshot_sessions', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('gc_screenshot_sessions', lazy='dynamic'))

    def __repr__(self):
        return f'<GCScreenshotSession {self.id}: game={self.game_id} status={self.status}>'

    @property
    def is_retryable(self):
        """Check if this session can be retried (max 2 attempts)."""
        return self.status == self.STATUS_ERROR and self.attempt_number < 2

    @property
    def was_edited_bool(self):
        """Return was_edited as boolean."""
        return self.was_edited == 1

    @property
    def edit_summary(self):
        """Get summary of what was edited."""
        if not self.edit_diff:
            return None
        summary = self.edit_diff.get('summary', {})
        return summary

    def get_parsed_data(self):
        """Get parsed data as dict."""
        if isinstance(self.parsed_json, str):
            return json.loads(self.parsed_json)
        return self.parsed_json or {}

    def get_final_data(self):
        """Get final submitted data as dict."""
        if isinstance(self.final_submitted_json, str):
            return json.loads(self.final_submitted_json)
        return self.final_submitted_json or {}

    def get_edit_diff(self):
        """Get edit diff as dict."""
        if isinstance(self.edit_diff, str):
            return json.loads(self.edit_diff)
        return self.edit_diff or {}

    @classmethod
    def get_for_game_team(cls, game_id, team_id, status=None):
        """Get sessions for a specific game/team."""
        query = cls.query.filter_by(game_id=game_id, team_id=team_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def get_latest_for_game_team(cls, game_id, team_id):
        """Get most recent session for a game/team."""
        return cls.query.filter_by(
            game_id=game_id,
            team_id=team_id
        ).order_by(cls.created_at.desc()).first()

    @classmethod
    def get_by_session_uuid(cls, session_uuid):
        """Get all attempts for a session UUID."""
        return cls.query.filter_by(
            session_uuid=session_uuid
        ).order_by(cls.attempt_number).all()

    @classmethod
    def get_recent(cls, days=30, limit=100):
        """Get recent sessions for audit view."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        return cls.query.filter(
            cls.created_at >= cutoff
        ).order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def get_audit_stats(cls, days=30):
        """Get aggregate statistics for audit dashboard."""
        from datetime import timedelta
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=days)

        # Total sessions and submissions
        total = cls.query.filter(cls.created_at >= cutoff).count()
        submitted = cls.query.filter(
            cls.created_at >= cutoff,
            cls.status == cls.STATUS_SUBMITTED
        ).count()

        # Edit rate (of submitted)
        edited = cls.query.filter(
            cls.created_at >= cutoff,
            cls.status == cls.STATUS_SUBMITTED,
            cls.was_edited == 1
        ).count()

        # Error rate
        errors = cls.query.filter(
            cls.created_at >= cutoff,
            cls.status == cls.STATUS_ERROR
        ).count()

        return {
            'total_sessions': total,
            'submitted': submitted,
            'edited': edited,
            'edit_rate': round(edited / submitted * 100, 1) if submitted > 0 else 0,
            'errors': errors,
            'error_rate': round(errors / total * 100, 1) if total > 0 else 0
        }
