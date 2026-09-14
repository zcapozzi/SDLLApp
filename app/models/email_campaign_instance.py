"""Email Campaign Instance model - per-season campaign with editable content."""

import json
from datetime import datetime
from app.extensions import db


class EmailCampaignInstance(db.Model):
    """A specific campaign instance for a season.

    Each instance is generated from a template with variables injected
    and recipients resolved. The coordinator can edit the content before sending.
    """
    __tablename__ = 'sdll_email_campaign_instances'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('sdll_email_campaign_templates.id',
                                                       ondelete='CASCADE'), nullable=False)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID',
                                                            ondelete='CASCADE'), nullable=False)

    trigger_date = db.Column(db.Date, nullable=False)
    trigger_date_override = db.Column(db.SmallInteger, default=0)

    # Editable content (variables already injected)
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    body_text = db.Column(db.Text)

    # Recipients as JSON array
    _recipients = db.Column('recipients', db.Text, nullable=False)

    # Workflow status
    status = db.Column(db.Enum('pending', 'draft', 'ready', 'sent', 'skipped'), default='pending')
    reminder_sent_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.BigInteger)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    template = db.relationship('EmailCampaignTemplate', back_populates='instances')
    org_season = db.relationship('OrgSeason', backref='campaign_instances')

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_DRAFT = 'draft'
    STATUS_READY = 'ready'
    STATUS_SENT = 'sent'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_DRAFT, 'Draft Ready'),
        (STATUS_READY, 'Ready to Send'),
        (STATUS_SENT, 'Sent'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    def __repr__(self):
        return f'<EmailCampaignInstance {self.id} template={self.template_id}>'

    @property
    def recipients(self):
        """Parse recipients JSON into list of dicts."""
        if not self._recipients:
            return []
        try:
            return json.loads(self._recipients)
        except (json.JSONDecodeError, TypeError):
            return []

    @recipients.setter
    def recipients(self, value):
        """Store recipients list as JSON."""
        if value is None:
            self._recipients = '[]'
        elif isinstance(value, str):
            self._recipients = value
        else:
            self._recipients = json.dumps(value)

    @property
    def recipient_count(self):
        """Number of recipients."""
        return len(self.recipients)

    @property
    def recipient_emails(self):
        """Extract just the email addresses."""
        return [r.get('email') for r in self.recipients if r.get('email')]

    @property
    def status_display(self):
        """Human-readable status."""
        for code, label in self.STATUSES:
            if code == self.status:
                return label
        return self.status

    @property
    def is_due(self):
        """Check if campaign is due (trigger_date <= today)."""
        from datetime import date
        return self.trigger_date <= date.today()

    @property
    def is_editable(self):
        """Check if campaign can still be edited."""
        return self.status in (self.STATUS_PENDING, self.STATUS_DRAFT, self.STATUS_READY)

    @property
    def is_sendable(self):
        """Check if campaign can be sent."""
        return self.status in (self.STATUS_DRAFT, self.STATUS_READY) and self.recipient_count > 0

    @property
    def trigger_date_was_overridden(self):
        """Check if coordinator changed the trigger date."""
        return self.trigger_date_override == 1

    def update_trigger_date(self, new_date):
        """Update trigger date and mark as overridden."""
        self.trigger_date = new_date
        self.trigger_date_override = 1
        db.session.commit()

    def mark_draft_ready(self):
        """Transition from pending to draft (content generated)."""
        self.status = self.STATUS_DRAFT
        db.session.commit()

    def mark_ready(self):
        """Mark as ready to send (coordinator approved)."""
        self.status = self.STATUS_READY
        db.session.commit()

    def mark_sent(self, user_id, sent_count=0, failed_count=0):
        """Mark as sent with results."""
        self.status = self.STATUS_SENT
        self.sent_at = datetime.utcnow()
        self.sent_by = user_id
        self.sent_count = sent_count
        self.failed_count = failed_count
        db.session.commit()

    def mark_skipped(self):
        """Skip this campaign."""
        self.status = self.STATUS_SKIPPED
        db.session.commit()

    def update_content(self, subject=None, body_html=None, body_text=None):
        """Update the campaign content."""
        if subject is not None:
            self.subject = subject
        if body_html is not None:
            self.body_html = body_html
        if body_text is not None:
            self.body_text = body_text
        db.session.commit()

    @classmethod
    def get_for_season(cls, org_season_id):
        """Get all campaign instances for a season."""
        return cls.query.filter_by(org_season_id=org_season_id).order_by(
            cls.trigger_date
        ).all()

    @classmethod
    def get_pending_for_season(cls, org_season_id):
        """Get pending campaigns that haven't been actioned yet."""
        return cls.query.filter_by(
            org_season_id=org_season_id,
            status=cls.STATUS_PENDING
        ).order_by(cls.trigger_date).all()

    @classmethod
    def get_due_campaigns(cls):
        """Get all campaigns that are due (trigger_date <= today) and pending."""
        from datetime import date
        return cls.query.filter(
            cls.trigger_date <= date.today(),
            cls.status == cls.STATUS_PENDING
        ).all()

    @classmethod
    def get_or_create(cls, template_id, org_season_id, trigger_date, subject, body_html, body_text, recipients):
        """Get existing instance or create new one.

        Used during campaign generation to avoid duplicates.
        """
        existing = cls.query.filter_by(
            template_id=template_id,
            org_season_id=org_season_id
        ).first()

        if existing:
            return existing, False

        instance = cls(
            template_id=template_id,
            org_season_id=org_season_id,
            trigger_date=trigger_date,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            recipients=recipients,
            status=cls.STATUS_PENDING
        )
        db.session.add(instance)
        db.session.commit()
        return instance, True

    @classmethod
    def exists_for_template_and_season(cls, template_id, org_season_id):
        """Check if a campaign instance already exists."""
        return cls.query.filter_by(
            template_id=template_id,
            org_season_id=org_season_id
        ).count() > 0
