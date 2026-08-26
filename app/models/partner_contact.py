"""PartnerContact model - contacts for umpire partner organizations."""

from datetime import datetime
from app.extensions import db


class PartnerContact(db.Model):
    """Contact person for an umpire partner organization.

    Each partner can have multiple contacts, each subscribed to different
    message types (weeklyDigest, recentChanges, etc.).
    """
    __tablename__ = 'sdll_partner_contacts'

    # Message type constants
    MSG_WEEKLY_DIGEST = 'weeklyDigest'
    MSG_RECENT_CHANGES = 'recentChanges'

    ALL_MESSAGE_TYPES = [MSG_WEEKLY_DIGEST, MSG_RECENT_CHANGES]

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'), nullable=True)

    # Contact info (used if not linked to a user)
    name = db.Column(db.String(200))
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50))

    # Message type subscriptions (pipe-delimited)
    message_types = db.Column(db.String(255), nullable=False, default='weeklyDigest|recentChanges')

    # Primary contact for display purposes
    is_primary = db.Column(db.Boolean, default=False)

    # Status
    active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    partner = db.relationship('UmpirePartner', back_populates='contacts')
    user = db.relationship('User', backref='partner_contacts')

    def __repr__(self):
        return f'<PartnerContact {self.email} for partner_id={self.partner_id}>'

    @property
    def display_name(self):
        """Get display name from linked user or stored name."""
        if self.user:
            return self.user.name
        return self.name or self.email

    @property
    def display_email(self):
        """Get email from linked user or stored email."""
        if self.user:
            return self.user.decrypted_email
        return self.email

    @property
    def message_types_list(self):
        """Get message types as a list."""
        if not self.message_types:
            return []
        return [t.strip() for t in self.message_types.split('|') if t.strip()]

    @message_types_list.setter
    def message_types_list(self, types):
        """Set message types from a list."""
        self.message_types = '|'.join(types) if types else ''

    def receives_message_type(self, msg_type):
        """Check if this contact receives a specific message type."""
        return msg_type in self.message_types_list

    @classmethod
    def get_for_partner(cls, partner_id, active_only=True):
        """Get all contacts for a partner.

        Args:
            partner_id: Partner ID
            active_only: Only return active contacts (default True)

        Returns:
            List of PartnerContact objects
        """
        query = cls.query.filter_by(partner_id=partner_id)
        if active_only:
            query = query.filter_by(active=True)
        # Sort primary contacts first, then by name
        return query.order_by(db.desc('is_primary'), 'name').all()

    @classmethod
    def get_for_message_type(cls, partner_id, msg_type, active_only=True):
        """Get contacts for a partner that receive a specific message type.

        Args:
            partner_id: Partner ID
            msg_type: Message type (e.g., 'weeklyDigest')
            active_only: Only return active contacts (default True)

        Returns:
            List of PartnerContact objects
        """
        query = cls.query.filter_by(partner_id=partner_id)
        if active_only:
            query = query.filter_by(active=True)
        # Filter by message type using LIKE for pipe-delimited field
        query = query.filter(
            db.or_(
                cls.message_types.like(f'{msg_type}|%'),
                cls.message_types.like(f'%|{msg_type}|%'),
                cls.message_types.like(f'%|{msg_type}'),
                cls.message_types == msg_type
            )
        )
        return query.all()

    @classmethod
    def get_emails_for_message_type(cls, partner_id, msg_type):
        """Get email addresses for a partner's contacts that receive a message type.

        Args:
            partner_id: Partner ID
            msg_type: Message type

        Returns:
            List of email addresses
        """
        contacts = cls.get_for_message_type(partner_id, msg_type)
        return [c.display_email for c in contacts if c.display_email]

    @classmethod
    def get_primary_contact(cls, partner_id):
        """Get the primary contact for a partner.

        Args:
            partner_id: Partner ID

        Returns:
            PartnerContact or None
        """
        return cls.query.filter_by(
            partner_id=partner_id,
            is_primary=True,
            active=True
        ).first()
