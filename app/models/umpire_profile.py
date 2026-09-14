"""UmpireProfile model - umpire-specific data linked to User accounts."""

from datetime import datetime, date
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class UmpireProfile(db.Model):
    """Umpire-specific data, optionally linked to a user account.

    This is a profile table - if user_id is set, the User handles authentication.
    For managed umpires (youth without their own email), user_id is NULL and
    a guardian manages the profile via the UmpireGuardian relationship.
    """
    __tablename__ = 'sdll_umpire_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'),
                        nullable=True)  # NULL for managed umpires

    # Name for managed umpires (those without their own User account)
    # Stored separately like sdll_users for consistency
    _first_name = db.Column('_first_name', db.String(500))
    _last_name = db.Column('_last_name', db.String(500))

    # Age tracking (important for youth umpires)
    birth_date = db.Column(db.Date)

    # Umpire's own contact info (for leads/managed profiles without user account)
    _umpire_email = db.Column('umpire_email', db.String(500))
    umpire_email_hash = db.Column(db.String(64))
    _umpire_phone = db.Column('umpire_phone', db.String(500))

    # Parent/guardian contacts (encrypted, for minors)
    _parent_name = db.Column('parent_name', db.String(500))
    _parent_email = db.Column('parent_email', db.String(500))
    parent_email_hash = db.Column(db.String(64))
    _parent_phone = db.Column('parent_phone', db.String(500))

    # Status and qualifications
    # Status values: prospective, contacted, declined (leads) | active, inactive, retired (confirmed)
    status = db.Column(db.String(20), default='active')
    is_kid_pitch_eligible = db.Column(db.Boolean, default=False)  # Legacy - use age_rank fields
    pay_scale = db.Column(db.String(50))  # 'standard', 'machine_pitch_only', etc.

    # Lead tracking fields (used when status = prospective/contacted)
    lead_source = db.Column(db.String(50))  # website_form, referral, manual, returning
    lead_notes = db.Column(db.Text)
    target_org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID',
                                                                   ondelete='SET NULL'))
    last_contacted_at = db.Column(db.DateTime)

    # Eligibility by sport and age_rank
    # NULL = not eligible for that sport, value = max age_rank they can work
    # Example: max_baseball_age_rank=5 means eligible for Tee Ball(1) through AAA(5)
    max_baseball_age_rank = db.Column(db.SmallInteger)  # NULL = no baseball
    max_softball_age_rank = db.Column(db.SmallInteger)  # NULL = no softball

    # Excluded leagues - comma-separated league IDs they won't see as available
    excluded_leagues = db.Column(db.String(200))  # e.g., "3,7" to exclude specific leagues

    # External reference for imports
    assignr_id = db.Column(db.String(50))

    # Payment IDs (for treasurer to track payment methods)
    venmo_id = db.Column(db.String(40))
    paypal_id = db.Column(db.String(40))
    zelle_id = db.Column(db.String(40))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('umpire_profile', uselist=False))
    assignments = db.relationship('GameUmpire', back_populates='umpire',
                                  foreign_keys='GameUmpire.umpire_profile_id')
    target_org_season = db.relationship('OrgSeason', backref='prospective_umpires',
                                        foreign_keys=[target_org_season_id])

    # Status constants - Lead statuses
    STATUS_PROSPECTIVE = 'prospective'  # New lead - interested but not confirmed
    STATUS_CONTACTED = 'contacted'      # Lead has been contacted about training
    STATUS_DECLINED = 'declined'        # Lead declined to participate

    # Status constants - Confirmed umpire statuses
    STATUS_ACTIVE = 'active'            # Confirmed, trained, can be assigned games
    STATUS_INACTIVE = 'inactive'        # Temporarily not available
    STATUS_RETIRED = 'retired'          # No longer umpiring

    # All statuses grouped by type
    LEAD_STATUSES = [STATUS_PROSPECTIVE, STATUS_CONTACTED, STATUS_DECLINED]
    CONFIRMED_STATUSES = [STATUS_ACTIVE, STATUS_INACTIVE, STATUS_RETIRED]
    STATUSES = LEAD_STATUSES + CONFIRMED_STATUSES

    # Lead source constants
    LEAD_SOURCE_WEBSITE = 'website_form'
    LEAD_SOURCE_REFERRAL = 'referral'
    LEAD_SOURCE_MANUAL = 'manual'
    LEAD_SOURCE_RETURNING = 'returning'

    LEAD_SOURCES = [
        (LEAD_SOURCE_WEBSITE, 'Website Form'),
        (LEAD_SOURCE_REFERRAL, 'Referral'),
        (LEAD_SOURCE_MANUAL, 'Manual Entry'),
        (LEAD_SOURCE_RETURNING, 'Returning Umpire'),
    ]

    def __repr__(self):
        return f'<UmpireProfile {self.id}: user_id={self.user_id}>'

    # Umpire email property with encryption (for leads/managed profiles)
    @property
    def umpire_email(self):
        return decrypt_value(self._umpire_email) if self._umpire_email else None

    @umpire_email.setter
    def umpire_email(self, value):
        if value:
            self._umpire_email = encrypt_value(value)
            self.umpire_email_hash = hash_for_lookup(value)
        else:
            self._umpire_email = None
            self.umpire_email_hash = None

    # Umpire phone property with encryption (for leads/managed profiles)
    @property
    def umpire_phone(self):
        return decrypt_value(self._umpire_phone) if self._umpire_phone else None

    @umpire_phone.setter
    def umpire_phone(self, value):
        self._umpire_phone = encrypt_value(value) if value else None

    # Parent name property with encryption
    @property
    def parent_name(self):
        return decrypt_value(self._parent_name) if self._parent_name else None

    @parent_name.setter
    def parent_name(self, value):
        self._parent_name = encrypt_value(value) if value else None

    # Parent email property with encryption
    @property
    def parent_email(self):
        return decrypt_value(self._parent_email) if self._parent_email else None

    @parent_email.setter
    def parent_email(self, value):
        if value:
            self._parent_email = encrypt_value(value)
            self.parent_email_hash = hash_for_lookup(value)
        else:
            self._parent_email = None
            self.parent_email_hash = None

    # Parent phone property with encryption
    @property
    def parent_phone(self):
        return decrypt_value(self._parent_phone) if self._parent_phone else None

    @parent_phone.setter
    def parent_phone(self, value):
        self._parent_phone = encrypt_value(value) if value else None

    # First name property for managed umpires (encrypted)
    @property
    def first_name(self):
        """Get first name - from profile field (managed umpires only)."""
        if self._first_name:
            return decrypt_value(self._first_name)
        # User model doesn't have first_name, so return None for regular umpires
        return None

    @first_name.setter
    def first_name(self, value):
        """Set first name directly on profile (for managed umpires)."""
        self._first_name = encrypt_value(value) if value else None

    # Last name property for managed umpires (encrypted)
    @property
    def last_name(self):
        """Get last name - from profile field (managed umpires only)."""
        if self._last_name:
            return decrypt_value(self._last_name)
        # User model doesn't have last_name, so return None for regular umpires
        return None

    @last_name.setter
    def last_name(self, value):
        """Set last name directly on profile (for managed umpires)."""
        self._last_name = encrypt_value(value) if value else None

    @property
    def name(self):
        """Get full name - combines first and last name."""
        first = self.first_name
        last = self.last_name
        if first and last:
            return f"{first} {last}"
        return first or last or (self.user.name if self.user else None)

    @property
    def is_managed(self):
        """Check if this is a managed profile (no direct user account)."""
        return self.user_id is None

    @property
    def age(self):
        """Calculate age from birth_date.

        Returns:
            int: Age in years, or None if birth_date not set.
        """
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def full_name(self):
        """Get the umpire's full name."""
        # Use profile name if set, otherwise user name
        return self.name

    @property
    def email(self):
        """Get the umpire's email from the linked User (or None for managed)."""
        return self.user.email if self.user else None

    @property
    def phone(self):
        """Get the umpire's phone from the linked User (or None for managed)."""
        return self.user.phone if self.user else None

    @property
    def contact_email(self):
        """Get contact email - umpire's own or primary guardian's."""
        if self.user:
            return self.user.email
        # Check umpire's own email first (for leads/managed)
        if self.umpire_email:
            return self.umpire_email
        # For managed umpires, get primary guardian's email
        primary_guardian = self.guardians.filter_by(is_primary=1).first()
        if primary_guardian and primary_guardian.guardian:
            return primary_guardian.guardian.email
        # Fallback to parent_email field
        return self.parent_email

    @property
    def contact_phone(self):
        """Get contact phone - umpire's own or primary guardian's."""
        if self.user:
            return self.user.phone
        # Check umpire's own phone first (for leads/managed)
        if self.umpire_phone:
            return self.umpire_phone
        primary_guardian = self.guardians.filter_by(is_primary=1).first()
        if primary_guardian and primary_guardian.guardian:
            return primary_guardian.guardian.phone
        return self.parent_phone

    @property
    def is_minor(self):
        """Check if umpire is under 18."""
        age = self.age
        return age is not None and age < 18

    @property
    def is_active(self):
        """Check if umpire is active."""
        return self.status == self.STATUS_ACTIVE

    @property
    def is_lead(self):
        """Check if this is a prospective lead (not yet confirmed)."""
        return self.status in self.LEAD_STATUSES

    @property
    def is_confirmed(self):
        """Check if this is a confirmed umpire (not a lead)."""
        return self.status in self.CONFIRMED_STATUSES

    @property
    def lead_source_display(self):
        """Human-readable lead source."""
        if not self.lead_source:
            return None
        for code, label in self.LEAD_SOURCES:
            if code == self.lead_source:
                return label
        return self.lead_source

    @property
    def excluded_league_ids(self):
        """Get list of excluded league IDs."""
        if not self.excluded_leagues:
            return []
        return [int(x.strip()) for x in self.excluded_leagues.split(',') if x.strip().isdigit()]

    @excluded_league_ids.setter
    def excluded_league_ids(self, ids):
        """Set excluded league IDs from a list."""
        if not ids:
            self.excluded_leagues = None
        else:
            self.excluded_leagues = ','.join(str(x) for x in ids)

    def is_eligible_for_league(self, league):
        """Check if this umpire is eligible for a specific league.

        Args:
            league: League object to check eligibility for.

        Returns:
            bool: True if eligible.
        """
        if not league:
            return True

        # Check if explicitly excluded
        if league.ID in self.excluded_league_ids:
            return False

        # Check sport eligibility by age_rank
        if league.is_baseball:
            if self.max_baseball_age_rank is None:
                return False  # Not eligible for any baseball
            if league.age_rank and league.age_rank > self.max_baseball_age_rank:
                return False  # League is above their max level
        elif league.is_softball:
            if self.max_softball_age_rank is None:
                return False  # Not eligible for any softball
            if league.age_rank and league.age_rank > self.max_softball_age_rank:
                return False  # League is above their max level

        return True

    def can_umpire_game(self, game):
        """Check if this umpire is eligible to umpire a specific game.

        Args:
            game: Game object to check eligibility for.

        Returns:
            bool: True if eligible.
        """
        if not self.is_active:
            return False

        # Check league eligibility
        if hasattr(game, 'league') and game.league:
            from app.models.league import League
            league = League.get_by_name(game.league)
            if league and not self.is_eligible_for_league(league):
                return False

            # Legacy fallback: check kid-pitch eligibility
            if league and league.requires_kid_pitch and not self.is_kid_pitch_eligible:
                # Only fail if new eligibility fields aren't set
                if self.max_baseball_age_rank is None and self.max_softball_age_rank is None:
                    return False

        return True

    @property
    def eligibility_display(self):
        """Human-readable eligibility description."""
        parts = []

        if self.max_baseball_age_rank is not None:
            from app.models.league import League
            bb_leagues = League.get_baseball_leagues()
            eligible = [l for l in bb_leagues if l.age_rank and l.age_rank <= self.max_baseball_age_rank]
            if eligible:
                max_league = max(eligible, key=lambda l: l.age_rank)
                parts.append(f"BB up to {max_league.display_name.replace('BB ', '')}")

        if self.max_softball_age_rank is not None:
            from app.models.league import League
            sb_leagues = League.get_softball_leagues()
            eligible = [l for l in sb_leagues if l.age_rank and l.age_rank <= self.max_softball_age_rank]
            if eligible:
                max_league = max(eligible, key=lambda l: l.age_rank)
                parts.append(f"SB up to {max_league.display_name.replace('SB ', '')}")

        if not parts:
            return "No eligibility set"

        return ", ".join(parts)

    @classmethod
    def get_active(cls):
        """Get all active umpire profiles."""
        return cls.query.filter_by(status=cls.STATUS_ACTIVE).all()

    @classmethod
    def get_eligible_for_game(cls, game):
        """Get all umpires eligible to umpire a specific game.

        Args:
            game: Game object to find eligible umpires for.

        Returns:
            List of eligible UmpireProfile objects.
        """
        profiles = cls.get_active()
        return [p for p in profiles if p.can_umpire_game(game)]

    @classmethod
    def get_by_user_id(cls, user_id):
        """Get umpire profile by user ID."""
        return cls.query.filter_by(user_id=user_id).first()

    @classmethod
    def get_by_assignr_id(cls, assignr_id):
        """Get umpire profile by Assignr ID (for imports)."""
        return cls.query.filter_by(assignr_id=assignr_id).first()

    @classmethod
    def get_accessible_profiles(cls, user_id):
        """Get all umpire profiles a user can access.

        This includes:
        - Their own profile (if they have one)
        - Any profiles they manage as a guardian

        Args:
            user_id: The user's ID

        Returns:
            List of UmpireProfile objects
        """
        from app.models.umpire_guardian import UmpireGuardian

        profiles = []

        # Get their own profile
        own_profile = cls.query.filter_by(user_id=user_id).first()
        if own_profile:
            profiles.append(own_profile)

        # Get managed profiles
        managed = UmpireGuardian.get_managed_profiles(user_id)
        for profile in managed:
            if profile not in profiles:
                profiles.append(profile)

        return profiles

    @classmethod
    def create_managed_profile(cls, first_name, last_name, guardian_user_id, birth_date=None,
                                max_baseball_age_rank=None, max_softball_age_rank=None,
                                relationship='parent'):
        """Create a managed umpire profile (for youth without their own account).

        Args:
            first_name: The umpire's first name
            last_name: The umpire's last name
            guardian_user_id: User ID of the guardian (parent)
            birth_date: Optional birth date
            max_baseball_age_rank: Baseball eligibility level
            max_softball_age_rank: Softball eligibility level
            relationship: Relationship type (parent, guardian, other)

        Returns:
            The created UmpireProfile
        """
        from app.models.umpire_guardian import UmpireGuardian

        profile = cls(
            user_id=None,  # Managed profile - no direct user
            status=cls.STATUS_ACTIVE,
            birth_date=birth_date,
            max_baseball_age_rank=max_baseball_age_rank,
            max_softball_age_rank=max_softball_age_rank
        )
        profile.first_name = first_name
        profile.last_name = last_name

        db.session.add(profile)
        db.session.flush()  # Get the profile ID

        # Link to guardian
        UmpireGuardian.add_guardian(
            user_id=guardian_user_id,
            profile_id=profile.id,
            relationship=relationship,
            is_primary=True
        )

        db.session.commit()
        return profile

    def hive_off_to_user(self, user):
        """Transfer this managed profile to an independent user account.

        This is used when a youth umpire gets their own email address
        and needs their own login.

        Args:
            user: The User object to link this profile to

        Returns:
            True if successful
        """
        from app.models.umpire_guardian import UmpireGuardian

        if self.user_id is not None:
            raise ValueError("Profile is already linked to a user account")

        # Copy name to user if user doesn't have one
        # User model has single 'name' field, so combine first + last
        if not user.name and self.name:
            user.name = self.name

        # Link profile to user
        self.user_id = user.ID

        # Clear the profile's standalone name fields (now uses user's name)
        # Keep them as backup in case we need them
        # self._first_name = None
        # self._last_name = None

        db.session.commit()
        return True

    def can_be_accessed_by(self, user_id):
        """Check if a user can access this profile.

        Args:
            user_id: The user ID to check

        Returns:
            True if user owns this profile or is a guardian
        """
        from app.models.umpire_guardian import UmpireGuardian

        # User owns this profile directly
        if self.user_id == user_id:
            return True

        # User is a guardian
        return UmpireGuardian.is_guardian_of(user_id, self.id)

    def mark_contacted(self):
        """Mark a prospective lead as contacted."""
        if self.status == self.STATUS_PROSPECTIVE:
            self.status = self.STATUS_CONTACTED
            self.last_contacted_at = datetime.utcnow()
            db.session.commit()

    def convert_to_active(self):
        """Convert a lead to an active umpire.

        Clears lead-specific fields and sets status to active.
        """
        self.status = self.STATUS_ACTIVE
        # Clear lead fields since they're now an active umpire
        self.lead_source = None
        self.lead_notes = None
        self.target_org_season_id = None
        db.session.commit()

    def mark_declined(self):
        """Mark a lead as declined."""
        if self.status in self.LEAD_STATUSES:
            self.status = self.STATUS_DECLINED
            db.session.commit()

    @classmethod
    def get_leads(cls, org_season_id=None):
        """Get all prospective leads.

        Args:
            org_season_id: Optional filter by target season.

        Returns:
            List of UmpireProfile with lead status.
        """
        query = cls.query.filter(cls.status.in_(cls.LEAD_STATUSES))
        if org_season_id:
            query = query.filter_by(target_org_season_id=org_season_id)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def get_leads_by_status(cls, status, org_season_id=None):
        """Get leads with a specific status."""
        query = cls.query.filter_by(status=status)
        if org_season_id:
            query = query.filter_by(target_org_season_id=org_season_id)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def create_lead(cls, first_name, last_name, umpire_email=None, umpire_phone=None,
                    parent_name=None, parent_email=None, parent_phone=None,
                    lead_source=None, lead_notes=None, target_org_season_id=None,
                    birth_date=None):
        """Create a new prospective lead.

        Args:
            first_name: Lead's first name
            last_name: Lead's last name
            umpire_email: Umpire's own email address (if they have one)
            umpire_phone: Umpire's own phone number (if they have one)
            parent_name: Parent/guardian name (for minors)
            parent_email: Parent/guardian email address
            parent_phone: Parent/guardian phone number
            lead_source: How they found us (website_form, referral, manual, returning)
            lead_notes: Optional notes about the lead
            target_org_season_id: Season they're interested in
            birth_date: Optional birth date

        Returns:
            Created UmpireProfile with status=prospective
        """
        profile = cls(
            user_id=None,  # No user account yet
            status=cls.STATUS_PROSPECTIVE,
            birth_date=birth_date,
            lead_source=lead_source,
            lead_notes=lead_notes,
            target_org_season_id=target_org_season_id
        )
        profile.first_name = first_name
        profile.last_name = last_name

        # Store umpire's own contact info
        if umpire_email:
            profile.umpire_email = umpire_email
        if umpire_phone:
            profile.umpire_phone = umpire_phone

        # Store parent/guardian contact info
        if parent_name:
            profile.parent_name = parent_name
        if parent_email:
            profile.parent_email = parent_email
        if parent_phone:
            profile.parent_phone = parent_phone

        db.session.add(profile)
        db.session.commit()
        return profile
