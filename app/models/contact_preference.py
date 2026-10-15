"""ContactPreference model - manages communication opt-in/opt-out preferences.

Supports:
- Multiple channels (SMS, email)
- Multiple message categories (rainout, postgame, schedule_change, etc.)
- Per-contact, per-channel, per-category preferences
- Toggle on/off with history tracking
"""

from datetime import datetime
from app.extensions import db


class ContactPreference(db.Model):
    """Stores communication preferences for phone numbers and emails.

    A single contact (phone/email) can have multiple records - one for each
    message_category + channel combination. This allows fine-grained control
    like "text me about rainouts but not post-game reports".
    """
    __tablename__ = 'sdll_contact_preferences'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Organization context (for multi-org support if needed)
    org_id = db.Column(db.BigInteger, default=1, nullable=False)

    # Optional link to user (if contact is a registered user)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=True)

    # Contact info
    contact_value = db.Column(db.String(255), nullable=False)  # Phone (E.164) or email
    contact_type = db.Column(db.Enum('sms', 'email'), nullable=False)

    # Message category this preference applies to
    # Examples: rainout, postgame, schedule_change, game_reminder, weekly_digest, general
    message_category = db.Column(db.String(50), nullable=False)

    # Current opt-in status
    opted_in = db.Column(db.SmallInteger, nullable=False, default=1)  # 1=in, 0=out

    # Timestamps for tracking preference changes
    opted_in_at = db.Column(db.DateTime, nullable=True)
    opted_out_at = db.Column(db.DateTime, nullable=True)

    # Audit timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Source of the preference (how they opted in/out)
    # e.g., 'registration_form', 'sms_stop', 'web_settings', 'admin', 'import'
    source = db.Column(db.String(50), nullable=True)

    # Relationships
    user = db.relationship('User', backref=db.backref('contact_preferences', lazy='dynamic'))

    # Message category constants
    CAT_RAINOUT = 'rainout'
    CAT_POSTGAME = 'postgame'
    CAT_SCHEDULE_CHANGE = 'schedule_change'
    CAT_GAME_REMINDER = 'game_reminder'
    CAT_WEEKLY_DIGEST = 'weekly_digest'
    CAT_GENERAL = 'general'

    ALL_CATEGORIES = [
        CAT_RAINOUT,
        CAT_POSTGAME,
        CAT_SCHEDULE_CHANGE,
        CAT_GAME_REMINDER,
        CAT_WEEKLY_DIGEST,
        CAT_GENERAL
    ]

    CATEGORY_LABELS = {
        CAT_RAINOUT: 'Rainout Notifications',
        CAT_POSTGAME: 'Post-Game Report Reminders',
        CAT_SCHEDULE_CHANGE: 'Schedule Changes',
        CAT_GAME_REMINDER: 'Game Day Reminders',
        CAT_WEEKLY_DIGEST: 'Weekly Schedule Digest',
        CAT_GENERAL: 'General Announcements'
    }

    # Channel constants
    CHANNEL_SMS = 'sms'
    CHANNEL_EMAIL = 'email'

    def __repr__(self):
        status = 'in' if self.opted_in else 'out'
        return f'<ContactPreference {self.contact_type}:{self.contact_value} {self.message_category}={status}>'

    def opt_in(self, source=None):
        """Opt this contact in for this category/channel."""
        self.opted_in = 1
        self.opted_in_at = datetime.utcnow()
        if source:
            self.source = source
        db.session.commit()

    def opt_out(self, source=None):
        """Opt this contact out for this category/channel."""
        self.opted_in = 0
        self.opted_out_at = datetime.utcnow()
        if source:
            self.source = source
        db.session.commit()

    def toggle(self, source=None):
        """Toggle the opt-in status."""
        if self.opted_in:
            self.opt_out(source)
        else:
            self.opt_in(source)

    @classmethod
    def normalize_phone(cls, phone):
        """Normalize phone number to E.164 format for consistent storage.

        Args:
            phone: Phone number in any format

        Returns:
            str: Phone in E.164 format (e.g., +19195551234)
        """
        import re
        # Strip all non-digits
        digits = re.sub(r'\D', '', phone)

        # Add US country code if not present
        if len(digits) == 10:
            digits = '1' + digits

        # Add + prefix
        if not digits.startswith('+'):
            digits = '+' + digits

        return digits

    @classmethod
    def get_preference(cls, contact_value, contact_type, message_category, org_id=1):
        """Get or create a preference record.

        Args:
            contact_value: Phone number or email
            contact_type: 'sms' or 'email'
            message_category: Category constant
            org_id: Organization ID (default 1)

        Returns:
            ContactPreference: The preference record
        """
        # Normalize phone numbers
        if contact_type == cls.CHANNEL_SMS:
            contact_value = cls.normalize_phone(contact_value)
        else:
            contact_value = contact_value.lower().strip()

        pref = cls.query.filter_by(
            contact_value=contact_value,
            contact_type=contact_type,
            message_category=message_category,
            org_id=org_id
        ).first()

        if not pref:
            pref = cls(
                contact_value=contact_value,
                contact_type=contact_type,
                message_category=message_category,
                org_id=org_id,
                opted_in=1,  # Default to opted in
                opted_in_at=datetime.utcnow()
            )
            db.session.add(pref)
            db.session.commit()

        return pref

    @classmethod
    def is_opted_in(cls, contact_value, contact_type, message_category, org_id=1):
        """Check if a contact is opted in for a specific category/channel.

        Args:
            contact_value: Phone number or email
            contact_type: 'sms' or 'email'
            message_category: Category constant
            org_id: Organization ID (default 1)

        Returns:
            bool: True if opted in (or no preference exists, meaning default opt-in)
        """
        # Normalize
        if contact_type == cls.CHANNEL_SMS:
            contact_value = cls.normalize_phone(contact_value)
        else:
            contact_value = contact_value.lower().strip()

        pref = cls.query.filter_by(
            contact_value=contact_value,
            contact_type=contact_type,
            message_category=message_category,
            org_id=org_id
        ).first()

        # No record = opted in by default
        if not pref:
            return True

        return pref.opted_in == 1

    @classmethod
    def handle_sms_stop(cls, phone_number, org_id=1):
        """Handle a STOP message - opt out of ALL SMS categories.

        Args:
            phone_number: The phone that sent STOP
            org_id: Organization ID

        Returns:
            int: Number of categories opted out
        """
        phone = cls.normalize_phone(phone_number)
        count = 0

        for category in cls.ALL_CATEGORIES:
            pref = cls.get_preference(phone, cls.CHANNEL_SMS, category, org_id)
            if pref.opted_in:
                pref.opt_out(source='sms_stop')
                count += 1

        return count

    @classmethod
    def handle_sms_start(cls, phone_number, org_id=1):
        """Handle a START message - opt back in to ALL SMS categories.

        Args:
            phone_number: The phone that sent START
            org_id: Organization ID

        Returns:
            int: Number of categories opted in
        """
        phone = cls.normalize_phone(phone_number)
        count = 0

        for category in cls.ALL_CATEGORIES:
            pref = cls.get_preference(phone, cls.CHANNEL_SMS, category, org_id)
            if not pref.opted_in:
                pref.opt_in(source='sms_start')
                count += 1

        return count

    @classmethod
    def get_all_for_contact(cls, contact_value, contact_type, org_id=1):
        """Get all preference records for a contact.

        Args:
            contact_value: Phone number or email
            contact_type: 'sms' or 'email'
            org_id: Organization ID

        Returns:
            list: List of ContactPreference records
        """
        if contact_type == cls.CHANNEL_SMS:
            contact_value = cls.normalize_phone(contact_value)
        else:
            contact_value = contact_value.lower().strip()

        return cls.query.filter_by(
            contact_value=contact_value,
            contact_type=contact_type,
            org_id=org_id
        ).all()

    @classmethod
    def get_opted_in_contacts(cls, contact_type, message_category, org_id=1):
        """Get all contacts opted in for a specific category/channel.

        Note: This returns contacts who have explicitly opted in OR have no
        preference record (default opt-in). For SMS, you should cross-reference
        with your contact list.

        Args:
            contact_type: 'sms' or 'email'
            message_category: Category constant
            org_id: Organization ID

        Returns:
            list: List of ContactPreference records with opted_in=1
        """
        return cls.query.filter_by(
            contact_type=contact_type,
            message_category=message_category,
            org_id=org_id,
            opted_in=1
        ).all()

    @classmethod
    def get_opted_out_contacts(cls, contact_type, message_category, org_id=1):
        """Get all contacts opted OUT for a specific category/channel.

        Useful for filtering a contact list before sending.

        Args:
            contact_type: 'sms' or 'email'
            message_category: Category constant
            org_id: Organization ID

        Returns:
            set: Set of contact values that are opted out
        """
        prefs = cls.query.filter_by(
            contact_type=contact_type,
            message_category=message_category,
            org_id=org_id,
            opted_in=0
        ).all()

        return {p.contact_value for p in prefs}
