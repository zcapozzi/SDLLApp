"""UmpireProfile model - umpire-specific data linked to User accounts."""

from datetime import datetime, date
from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class UmpireProfile(db.Model):
    """Umpire-specific data linked to a user account.

    This is a profile table - the User handles authentication,
    and this table holds umpire-specific attributes like eligibility,
    parent contacts (for youth umpires), and pay scale.
    """
    __tablename__ = 'sdll_umpire_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'),
                        unique=True, nullable=False)

    # Age tracking (important for youth umpires)
    birth_date = db.Column(db.Date)

    # Parent/guardian contacts (encrypted, for minors)
    _parent_name = db.Column('parent_name', db.String(500))
    _parent_email = db.Column('parent_email', db.String(500))
    parent_email_hash = db.Column(db.String(64))
    _parent_phone = db.Column('parent_phone', db.String(500))

    # Status and qualifications
    status = db.Column(db.String(20), default='active')  # active, inactive, retired
    is_kid_pitch_eligible = db.Column(db.Boolean, default=False)  # Legacy - use age_rank fields
    pay_scale = db.Column(db.String(50))  # 'standard', 'machine_pitch_only', etc.

    # Eligibility by sport and age_rank
    # NULL = not eligible for that sport, value = max age_rank they can work
    # Example: max_baseball_age_rank=5 means eligible for Tee Ball(1) through AAA(5)
    max_baseball_age_rank = db.Column(db.SmallInteger)  # NULL = no baseball
    max_softball_age_rank = db.Column(db.SmallInteger)  # NULL = no softball

    # Excluded leagues - comma-separated league IDs they won't see as available
    excluded_leagues = db.Column(db.String(200))  # e.g., "3,7" to exclude specific leagues

    # External reference for imports
    assignr_id = db.Column(db.String(50))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('umpire_profile', uselist=False))
    assignments = db.relationship('GameUmpire', back_populates='umpire',
                                  foreign_keys='GameUmpire.umpire_profile_id')

    # Status constants
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_RETIRED = 'retired'
    STATUSES = [STATUS_ACTIVE, STATUS_INACTIVE, STATUS_RETIRED]

    def __repr__(self):
        return f'<UmpireProfile {self.id}: user_id={self.user_id}>'

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
        """Get the umpire's full name from the linked User."""
        return self.user.name if self.user else None

    @property
    def email(self):
        """Get the umpire's email from the linked User."""
        return self.user.email if self.user else None

    @property
    def phone(self):
        """Get the umpire's phone from the linked User."""
        return self.user.phone if self.user else None

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
