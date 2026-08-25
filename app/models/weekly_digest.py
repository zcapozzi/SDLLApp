"""WeeklyDigest model - weekly umpire partner email digests."""

import json
from datetime import datetime
from app.extensions import db


class WeeklyDigest(db.Model):
    """Weekly digest email for umpire partners.

    Tracks the generation, review, and sending of weekly game schedules
    to external umpire partners (Diamond, Dynamic, SDLL Academy).
    """
    __tablename__ = 'sdll_weekly_digests'

    # Status constants
    STATUS_DRAFT = 'draft'
    STATUS_READY = 'ready'
    STATUS_SENT = 'sent'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [STATUS_DRAFT, STATUS_READY, STATUS_SENT, STATUS_SKIPPED]

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Targeting
    partner_code = db.Column(db.String(10), nullable=False)  # 'DIA', 'DYN', 'SDL'
    partner_name = db.Column(db.String(100), nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # Monday of the target week
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)

    # Recipients (JSON array of email addresses)
    recipient_emails = db.Column(db.Text, nullable=False)

    # Content
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    game_count = db.Column(db.Integer, nullable=False, default=0)

    # Workflow
    status = db.Column(db.Enum('draft', 'ready', 'sent', 'skipped'),
                       nullable=False, default='draft')
    reviewed_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID',
                            ondelete='SET NULL'))
    reviewed_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID',
                        ondelete='SET NULL'))

    # Reminders
    reminder_sent = db.Column(db.Boolean, default=False)

    # Relationships
    reviewer = db.relationship('User', foreign_keys=[reviewed_by],
                               backref='reviewed_digests')
    sender = db.relationship('User', foreign_keys=[sent_by],
                             backref='sent_digests')

    def __repr__(self):
        return f'<WeeklyDigest {self.partner_code} {self.week_start}>'

    @property
    def recipient_emails_list(self):
        """Parse recipient_emails JSON to list."""
        if not self.recipient_emails:
            return []
        try:
            return json.loads(self.recipient_emails)
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat as comma-separated string
            return [e.strip() for e in self.recipient_emails.split(',') if e.strip()]

    @recipient_emails_list.setter
    def recipient_emails_list(self, emails):
        """Set recipient_emails from a list."""
        self.recipient_emails = json.dumps(emails) if emails else '[]'

    @property
    def season_name(self):
        """Return formatted season name."""
        season = 'Spring' if self.is_spring else 'Fall'
        return f'{season} {self.year}'

    @property
    def week_display(self):
        """Return formatted week display."""
        if self.week_start:
            return self.week_start.strftime('%B %d, %Y')
        return ''

    @property
    def is_draft(self):
        return self.status == self.STATUS_DRAFT

    @property
    def is_ready(self):
        return self.status == self.STATUS_READY

    @property
    def is_sent(self):
        return self.status == self.STATUS_SENT

    @property
    def is_skipped(self):
        return self.status == self.STATUS_SKIPPED

    @property
    def can_send(self):
        """Check if digest can be sent."""
        return self.status in (self.STATUS_DRAFT, self.STATUS_READY) and self.game_count > 0

    def approve(self, user_id):
        """Mark digest as reviewed and ready to send."""
        self.status = self.STATUS_READY
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        db.session.commit()

    def mark_sent(self, user_id):
        """Mark digest as sent."""
        self.status = self.STATUS_SENT
        self.sent_at = datetime.utcnow()
        self.sent_by = user_id
        db.session.commit()

    def mark_skipped(self, user_id=None):
        """Mark digest as skipped (no games or admin decision)."""
        self.status = self.STATUS_SKIPPED
        if user_id:
            self.reviewed_by = user_id
            self.reviewed_at = datetime.utcnow()
        db.session.commit()

    def revert_to_draft(self):
        """Revert digest back to draft status for re-editing."""
        self.status = self.STATUS_DRAFT
        db.session.commit()

    @classmethod
    def get_ready_to_send(cls):
        """Get all digests ready to be sent."""
        return cls.query.filter_by(status=cls.STATUS_READY).all()

    @classmethod
    def get_pending_reminders(cls):
        """Get draft digests that haven't had reminders sent."""
        return cls.query.filter(
            cls.status == cls.STATUS_DRAFT,
            cls.reminder_sent == False,
            cls.game_count > 0
        ).all()

    @classmethod
    def get_for_week(cls, week_start):
        """Get all digests for a specific week."""
        return cls.query.filter_by(week_start=week_start).all()

    @classmethod
    def get_for_partner_week(cls, partner_code, week_start):
        """Get digest for specific partner and week."""
        return cls.query.filter_by(
            partner_code=partner_code,
            week_start=week_start
        ).first()

    @classmethod
    def get_for_season(cls, year, is_spring, limit=50):
        """Get all digests for a season, ordered by week descending."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).order_by(cls.week_start.desc()).limit(limit).all()

    @classmethod
    def get_recent(cls, limit=20):
        """Get recent digests across all seasons."""
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()
