"""UmpireDigest model - weekly digest emails for individual umpires."""

import json
from datetime import datetime
from app.extensions import db


class UmpireDigest(db.Model):
    """Weekly digest email for individual umpires (Academy umpires).

    Tracks the generation and sending of weekly game schedules
    to individual umpires and their parents/guardians.
    """
    __tablename__ = 'sdll_umpire_digests'

    # Status constants
    STATUS_DRAFT = 'draft'
    STATUS_READY = 'ready'
    STATUS_SENT = 'sent'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [STATUS_DRAFT, STATUS_READY, STATUS_SENT, STATUS_SKIPPED]

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Targeting - identify umpire by Assignr ID
    assignr_official_id = db.Column(db.Integer, nullable=False)
    umpire_name = db.Column(db.String(200), nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # Monday of the target week
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)

    # Optional link to local profile
    umpire_profile_id = db.Column(db.Integer,
                                   db.ForeignKey('sdll_umpire_profiles.id',
                                                 ondelete='SET NULL'))

    # Recipients (JSON array of email addresses - umpire + parents)
    recipient_emails = db.Column(db.Text, nullable=False)

    # Content
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    game_count = db.Column(db.Integer, nullable=False, default=0)

    # Workflow
    status = db.Column(db.Enum('draft', 'ready', 'sent', 'skipped'),
                       nullable=False, default='draft')
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID',
                        ondelete='SET NULL'))

    # Relationships
    umpire_profile = db.relationship('UmpireProfile',
                                      backref='digests',
                                      foreign_keys=[umpire_profile_id])
    sender = db.relationship('User', foreign_keys=[sent_by])

    # Unique constraint: one digest per umpire per week
    __table_args__ = (
        db.UniqueConstraint('assignr_official_id', 'week_start',
                           name='uq_umpire_digest_official_week'),
    )

    def __repr__(self):
        return f'<UmpireDigest {self.umpire_name} {self.week_start}>'

    @property
    def recipient_emails_list(self):
        """Parse recipient_emails JSON to list."""
        if not self.recipient_emails:
            return []
        try:
            return json.loads(self.recipient_emails)
        except (json.JSONDecodeError, TypeError):
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

    def mark_sent(self, user_id=None):
        """Mark digest as sent."""
        self.status = self.STATUS_SENT
        self.sent_at = datetime.utcnow()
        self.sent_by = user_id
        db.session.commit()

    def mark_skipped(self):
        """Mark digest as skipped (no games)."""
        self.status = self.STATUS_SKIPPED
        db.session.commit()

    @classmethod
    def get_for_week(cls, week_start):
        """Get all umpire digests for a specific week."""
        return cls.query.filter_by(week_start=week_start).order_by(cls.umpire_name).all()

    @classmethod
    def get_for_umpire_week(cls, assignr_official_id, week_start):
        """Get digest for specific umpire and week."""
        return cls.query.filter_by(
            assignr_official_id=assignr_official_id,
            week_start=week_start
        ).first()

    @classmethod
    def get_for_season(cls, year, is_spring, limit=100):
        """Get all umpire digests for a season."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).order_by(cls.week_start.desc(), cls.umpire_name).limit(limit).all()

    @classmethod
    def get_pending_for_week(cls, week_start):
        """Get draft digests for a week that can still be sent."""
        return cls.query.filter(
            cls.week_start == week_start,
            cls.status.in_([cls.STATUS_DRAFT, cls.STATUS_READY]),
            cls.game_count > 0
        ).order_by(cls.umpire_name).all()
