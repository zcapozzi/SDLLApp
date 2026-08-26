"""UmpirePartner model - external umpire service providers (Dynamic, Diamond, etc.)."""

from datetime import datetime
import secrets
from app.extensions import db


class UmpirePartner(db.Model):
    """External umpire service provider.

    Partners like Dynamic and Diamond provide umpires for games.
    We track assignments at the organization level, not individual umpires.
    """
    __tablename__ = 'sdll_umpire_partners'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # Partner identification
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(20))  # "DIA", "DYN" for quick reference

    # Notification preferences
    notification_preference = db.Column(db.String(20), default='weekly')
    # Options: 'daily', 'weekly', 'per_game'

    # Status
    active = db.Column(db.Boolean, default=True)

    # Per-game rates (cost per umpire)
    rate_normal = db.Column(db.Numeric(6, 2))  # Rate for normal games (per umpire)
    rate_ntl = db.Column(db.Numeric(6, 2))     # Rate for no-time-limit games (per umpire)

    # Schedule token for public schedule URL
    schedule_token = db.Column(db.String(32), unique=True, nullable=True, index=True)

    # Weekly digest settings
    auto_send_digest = db.Column(db.Boolean, default=False)  # Auto-send weekly digests without review

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    organization = db.relationship('Organization', backref='umpire_partners')
    game_assignments = db.relationship('GameUmpire', back_populates='partner',
                                       foreign_keys='GameUmpire.partner_id')
    contacts = db.relationship('PartnerContact', back_populates='partner',
                               cascade='all, delete-orphan', lazy='dynamic')

    # Notification preference constants
    NOTIFY_DAILY = 'daily'
    NOTIFY_WEEKLY = 'weekly'
    NOTIFY_PER_GAME = 'per_game'
    NOTIFICATION_PREFERENCES = [NOTIFY_DAILY, NOTIFY_WEEKLY, NOTIFY_PER_GAME]

    def __repr__(self):
        return f'<UmpirePartner {self.name} ({self.short_code})>'

    @property
    def is_active(self):
        """Check if partner is active."""
        return self.active

    @property
    def code(self):
        """Alias for short_code."""
        return self.short_code

    def get_upcoming_games(self, days=7):
        """Get games assigned to this partner in the next N days.

        Args:
            days: Number of days to look ahead.

        Returns:
            List of GameUmpire assignments.
        """
        from datetime import timedelta
        from app.models.game import Game

        cutoff = datetime.utcnow() + timedelta(days=days)
        return [
            assignment for assignment in self.game_assignments
            if assignment.game.game_date and
               assignment.game.game_date <= cutoff and
               assignment.status != 'cancelled'
        ]

    @classmethod
    def get_active(cls, org_id=1):
        """Get all active partners for an organization."""
        return cls.query.filter_by(org_id=org_id, active=True).all()

    @classmethod
    def get_by_code(cls, short_code, org_id=1):
        """Get partner by short code.

        Args:
            short_code: Partner's short code (e.g., 'DIA', 'DYN')
            org_id: Organization ID (default 1 for SDLL)

        Returns:
            UmpirePartner or None
        """
        return cls.query.filter_by(
            short_code=short_code.upper(),
            org_id=org_id,
            active=True
        ).first()

    @classmethod
    def get_by_name(cls, name, org_id=1):
        """Get partner by name."""
        return cls.query.filter_by(
            name=name,
            org_id=org_id,
            active=True
        ).first()

    def generate_schedule_token(self):
        """Generate a unique schedule token for public URL access."""
        self.schedule_token = secrets.token_urlsafe(16)
        return self.schedule_token

    @classmethod
    def get_by_schedule_token(cls, token):
        """Get partner by schedule token.

        Args:
            token: The schedule token from the URL

        Returns:
            UmpirePartner or None
        """
        if not token:
            return None
        return cls.query.filter_by(
            schedule_token=token,
            active=True
        ).first()

    def get_contacts_for_message_type(self, msg_type):
        """Get contacts that receive a specific message type.

        Args:
            msg_type: Message type (e.g., 'weeklyDigest', 'recentChanges')

        Returns:
            List of PartnerContact objects
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_for_message_type(self.id, msg_type)

    def get_emails_for_message_type(self, msg_type):
        """Get email addresses for contacts that receive a message type.

        Args:
            msg_type: Message type

        Returns:
            List of email addresses
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_emails_for_message_type(self.id, msg_type)

    def get_active_contacts(self):
        """Get all active contacts for this partner.

        Returns:
            List of PartnerContact objects
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_for_partner(self.id)

    @property
    def primary_contact(self):
        """Get the primary contact for display purposes."""
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_primary_contact(self.id)
