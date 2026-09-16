"""Email Routing Configuration model - per-email-type routing settings."""

from datetime import datetime
from app.extensions import db


class EmailRoutingConfig(db.Model):
    """Configuration for email routing per email type.

    Allows admins to configure reply-to, CC, and BCC addresses
    for different types of system emails. Supports both explicit
    email addresses and role-based routing.
    """
    __tablename__ = 'sdll_email_routing_configs'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # Which email type this applies to
    email_type = db.Column(db.String(50), nullable=False)

    # Routing configuration
    from_name = db.Column(db.String(100))
    from_email = db.Column(db.String(255))
    reply_to_email = db.Column(db.String(255))
    cc_emails = db.Column(db.Text)  # Comma-separated
    bcc_emails = db.Column(db.Text)  # Comma-separated

    # Role-based routing (auto-resolves to current role holder)
    reply_to_role = db.Column(db.String(50))
    cc_roles = db.Column(db.String(255))  # Pipe-separated roles

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Unique constraint: one config per org per email type
    __table_args__ = (
        db.UniqueConstraint('org_id', 'email_type', name='uq_email_routing_org_type'),
    )

    # Email type constants
    TYPE_WEEKLY_DIGEST = 'weekly_digest'
    TYPE_POSTGAME_REMINDER = 'postgame_reminder'
    TYPE_UMPIRE_ASSIGNMENT = 'umpire_assignment'
    TYPE_UMPIRE_CAMPAIGN = 'umpire_campaign'
    TYPE_COACH_WELCOME = 'coach_welcome'
    TYPE_RAINOUT_NOTIFICATION = 'rainout_notification'
    TYPE_ACCESS_REQUEST = 'access_request'

    EMAIL_TYPES = [
        (TYPE_WEEKLY_DIGEST, 'Weekly Digest'),
        (TYPE_POSTGAME_REMINDER, 'Post-Game Reminder'),
        (TYPE_UMPIRE_ASSIGNMENT, 'Umpire Assignment'),
        (TYPE_UMPIRE_CAMPAIGN, 'Umpire Campaign'),
        (TYPE_COACH_WELCOME, 'Coach Welcome'),
        (TYPE_RAINOUT_NOTIFICATION, 'Rainout Notification'),
        (TYPE_ACCESS_REQUEST, 'Access Request'),
    ]

    def __repr__(self):
        return f'<EmailRoutingConfig {self.email_type}>'

    @property
    def email_type_display(self):
        """Human-readable email type name."""
        for code, label in self.EMAIL_TYPES:
            if code == self.email_type:
                return label
        return self.email_type

    @property
    def cc_email_list(self):
        """Parse CC emails into list."""
        if not self.cc_emails:
            return []
        return [e.strip() for e in self.cc_emails.split(',') if e.strip()]

    @property
    def bcc_email_list(self):
        """Parse BCC emails into list."""
        if not self.bcc_emails:
            return []
        return [e.strip() for e in self.bcc_emails.split(',') if e.strip()]

    @property
    def cc_role_list(self):
        """Parse CC roles into list."""
        if not self.cc_roles:
            return []
        return [r.strip() for r in self.cc_roles.split('|') if r.strip()]

    @classmethod
    def get_for_email_type(cls, email_type, org_id=1):
        """Get routing config for an email type.

        Args:
            email_type: The email type constant
            org_id: Organization ID (defaults to SDLL)

        Returns:
            EmailRoutingConfig or None
        """
        return cls.query.filter_by(
            email_type=email_type,
            org_id=org_id,
            active=True
        ).first()

    @classmethod
    def get_all_for_org(cls, org_id=1):
        """Get all routing configs for an org."""
        return cls.query.filter_by(org_id=org_id).order_by(cls.email_type).all()

    @classmethod
    def ensure_defaults(cls, org_id=1):
        """Ensure all email types have a config entry.

        Creates missing configs with default values.
        """
        existing = {c.email_type for c in cls.get_all_for_org(org_id)}

        defaults = {
            cls.TYPE_WEEKLY_DIGEST: 'scheduler',
            cls.TYPE_UMPIRE_ASSIGNMENT: 'umpire_coordinator',
            cls.TYPE_UMPIRE_CAMPAIGN: 'umpire_coordinator',
            cls.TYPE_COACH_WELCOME: 'coaching_coordinator',
            cls.TYPE_RAINOUT_NOTIFICATION: 'scheduler',
            cls.TYPE_ACCESS_REQUEST: 'admin',
            cls.TYPE_POSTGAME_REMINDER: None,
        }

        for email_type, default_role in defaults.items():
            if email_type not in existing:
                config = cls(
                    org_id=org_id,
                    email_type=email_type,
                    reply_to_role=default_role,
                    active=True
                )
                db.session.add(config)

        db.session.commit()
