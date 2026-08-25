"""ScheduledEmail model - stores scheduled/sent email blasts."""

import json
from datetime import datetime
from app.extensions import db


class ScheduledEmail(db.Model):
    """Scheduled or sent email blast record."""
    __tablename__ = 'sdll_scheduled_emails'

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_PARTIAL = 'partial'  # Some succeeded, some failed
    STATUS_FAILED = 'failed'

    # Send mode constants
    MODE_CC = 'cc'
    MODE_BCC = 'bcc'
    MODE_INDIVIDUAL = 'individual'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'), nullable=False)

    # Email type for flexibility
    email_type = db.Column(db.String(50), nullable=False, default='coach_blast')

    # Targeting (for coach_blast type)
    year = db.Column(db.Integer, nullable=True)
    is_spring = db.Column(db.SmallInteger, nullable=True)
    _leagues = db.Column('leagues', db.Text, nullable=True)

    # Recipients (JSON)
    _recipients = db.Column('recipients', db.Text, nullable=False)
    _manual_recipients = db.Column('manual_recipients', db.Text, nullable=True)

    # Send mode
    send_mode = db.Column(db.Enum('cc', 'bcc', 'individual'), nullable=False, default='cc')

    # Content
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    body_text = db.Column(db.Text, nullable=False)
    reply_to = db.Column(db.String(255), nullable=False)

    # Scheduling
    scheduled_for = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum('pending', 'sending', 'sent', 'partial', 'failed'),
                       nullable=False, default='pending')
    sent_at = db.Column(db.DateTime, nullable=True)
    attempted_at = db.Column(db.DateTime, nullable=True)

    # Results
    recipient_count = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    failure_notified = db.Column(db.SmallInteger, default=0)

    # Relationships
    creator = db.relationship('User', backref=db.backref('scheduled_emails', lazy='dynamic'))

    def __repr__(self):
        return f'<ScheduledEmail {self.id}: {self.subject[:30]}... ({self.status})>'

    # JSON property: leagues
    @property
    def leagues(self):
        """Get leagues as a list."""
        if not self._leagues:
            return []
        try:
            return json.loads(self._leagues)
        except (json.JSONDecodeError, TypeError):
            return []

    @leagues.setter
    def leagues(self, value):
        """Set leagues from a list."""
        if value is None:
            self._leagues = None
        else:
            self._leagues = json.dumps(value)

    # JSON property: recipients
    @property
    def recipients(self):
        """Get recipients as a list of dicts."""
        if not self._recipients:
            return []
        try:
            return json.loads(self._recipients)
        except (json.JSONDecodeError, TypeError):
            return []

    @recipients.setter
    def recipients(self, value):
        """Set recipients from a list."""
        if value is None:
            self._recipients = '[]'
        else:
            self._recipients = json.dumps(value)

    # JSON property: manual_recipients
    @property
    def manual_recipients(self):
        """Get manual recipients as a list."""
        if not self._manual_recipients:
            return []
        try:
            return json.loads(self._manual_recipients)
        except (json.JSONDecodeError, TypeError):
            return []

    @manual_recipients.setter
    def manual_recipients(self, value):
        """Set manual recipients from a list."""
        if value is None:
            self._manual_recipients = None
        else:
            self._manual_recipients = json.dumps(value)

    @property
    def all_recipient_emails(self):
        """Get all recipient emails (coach + manual)."""
        emails = set()
        for r in self.recipients:
            if r.get('email'):
                emails.add(r['email'])
        for email in self.manual_recipients:
            if email:
                emails.add(email)
        return list(emails)

    @property
    def is_scheduled(self):
        """Check if this is a scheduled (not immediate) send."""
        return self.scheduled_for is not None

    @property
    def is_ready_to_send(self):
        """Check if this email is ready to be sent now."""
        if self.status != self.STATUS_PENDING:
            return False
        if self.attempted_at is not None:
            return False  # Already attempted
        if self.scheduled_for is None:
            return True  # Immediate send
        return self.scheduled_for <= datetime.utcnow()

    @property
    def season_name(self):
        """Get human-readable season name."""
        if self.year is None:
            return None
        season = 'Spring' if self.is_spring else 'Fall'
        return f'{season} {self.year}'

    @property
    def status_display(self):
        """Get human-readable status."""
        display = {
            'pending': 'Pending',
            'sending': 'Sending...',
            'sent': 'Sent',
            'partial': 'Partially Sent',
            'failed': 'Failed'
        }
        return display.get(self.status, self.status)

    @property
    def send_mode_display(self):
        """Get human-readable send mode."""
        display = {
            'cc': 'CC (visible)',
            'bcc': 'BCC (hidden)',
            'individual': 'Individual (per team)'
        }
        return display.get(self.send_mode, self.send_mode)

    def mark_attempted(self):
        """Mark as attempted (one-time only)."""
        self.attempted_at = datetime.utcnow()
        self.status = self.STATUS_SENDING
        db.session.commit()

    def mark_sent(self, sent_count, failed_count=0):
        """Mark as sent with results."""
        self.sent_at = datetime.utcnow()
        self.sent_count = sent_count
        self.failed_count = failed_count

        if failed_count == 0:
            self.status = self.STATUS_SENT
        elif sent_count > 0:
            self.status = self.STATUS_PARTIAL
        else:
            self.status = self.STATUS_FAILED

        db.session.commit()

    def mark_failed(self, error_message):
        """Mark as failed with error."""
        self.status = self.STATUS_FAILED
        self.error_message = error_message
        self.sent_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def get_ready_to_send(cls):
        """Get emails ready to send (not yet attempted)."""
        return cls.query.filter(
            cls.status == cls.STATUS_PENDING,
            cls.attempted_at.is_(None),  # Never attempted
            db.or_(
                cls.scheduled_for.is_(None),
                cls.scheduled_for <= datetime.utcnow()
            )
        ).all()

    @classmethod
    def get_history(cls, limit=50):
        """Get recent email history."""
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def get_pending(cls):
        """Get all pending emails."""
        return cls.query.filter_by(status=cls.STATUS_PENDING).order_by(cls.scheduled_for.asc()).all()

    @classmethod
    def create_coach_blast(cls, user_id, year, is_spring, leagues, recipients,
                           subject, body_html, body_text, reply_to,
                           send_mode='cc', manual_recipients=None, scheduled_for=None):
        """Create a new coach email blast."""
        email = cls(
            created_by=user_id,
            email_type='coach_blast',
            year=year,
            is_spring=is_spring,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            reply_to=reply_to,
            send_mode=send_mode,
            scheduled_for=scheduled_for,
            recipient_count=len(recipients) + (len(manual_recipients) if manual_recipients else 0)
        )
        email.leagues = leagues
        email.recipients = recipients
        email.manual_recipients = manual_recipients or []

        db.session.add(email)
        db.session.commit()
        return email
