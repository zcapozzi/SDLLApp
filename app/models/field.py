"""Field model - maps to sdll_fields table"""

from app.extensions import db


class Field(db.Model):
    """Represents a playing field/location"""
    __tablename__ = 'sdll_fields'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    location_title = db.Column(db.String(200))
    is_owned = db.Column(db.SmallInteger, default=1)  # 1 = SDLL owns, 0 = other league
    restriction_type = db.Column(db.String(20), default='anyone')  # 'anyone', 'exclude', 'only'
    restricted_leagues = db.Column(db.String(500))  # comma-separated league names

    # Field usage properties
    usage_type = db.Column(db.String(20), default='both')  # 'both', 'games_only', 'practice_only'
    practice_capacity = db.Column(db.Integer, default=1)   # Teams that can practice simultaneously
    practice_capacity_late = db.Column(db.Integer)         # Capacity for late slots (NULL = same as practice_capacity)

    # Restriction type constants
    RESTRICTION_ANYONE = 'anyone'
    RESTRICTION_EXCLUDE = 'exclude'
    RESTRICTION_ONLY = 'only'

    # Usage type constants
    USAGE_BOTH = 'both'
    USAGE_GAMES_ONLY = 'games_only'
    USAGE_PRACTICE_ONLY = 'practice_only'

    USAGE_TYPES = [
        ('both', 'Games & Practices'),
        ('games_only', 'Games Only'),
        ('practice_only', 'Practice Only'),
    ]

    # Relationship to alternate names
    alternate_names = db.relationship(
        'AlternateFieldName',
        backref='field',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Field {self.ID}: {self.location_title}>'

    @classmethod
    def get_all_active(cls):
        """Get all active fields"""
        return cls.query.filter_by(active=1).order_by(cls.location_title).all()

    @classmethod
    def get_by_name(cls, name):
        """Find field by name or alternate name"""
        # First try exact match
        field = cls.query.filter_by(location_title=name, active=1).first()
        if field:
            return field

        # Try alternate names
        alt = AlternateFieldName.query.filter_by(alternate_name=name).first()
        if alt:
            return cls.query.get(alt.field_ID)

        return None

    @property
    def restricted_leagues_list(self):
        """Get restricted leagues as a list"""
        if not self.restricted_leagues:
            return []
        return [l.strip() for l in self.restricted_leagues.split(',') if l.strip()]

    @restricted_leagues_list.setter
    def restricted_leagues_list(self, leagues):
        """Set restricted leagues from a list"""
        if not leagues:
            self.restricted_leagues = None
        else:
            self.restricted_leagues = ','.join(leagues)

    def can_league_use(self, league_name):
        """Check if a league can use this field based on restrictions"""
        if self.restriction_type == self.RESTRICTION_ANYONE:
            return True
        elif self.restriction_type == self.RESTRICTION_EXCLUDE:
            # Anyone except these leagues
            return league_name not in self.restricted_leagues_list
        elif self.restriction_type == self.RESTRICTION_ONLY:
            # Only these leagues
            return league_name in self.restricted_leagues_list
        return True  # Default to allowed

    @property
    def restriction_display(self):
        """Human-readable restriction description"""
        if self.restriction_type == self.RESTRICTION_ANYONE:
            return "Anyone"
        elif self.restriction_type == self.RESTRICTION_EXCLUDE:
            leagues = self.restricted_leagues_list
            if leagues:
                return f"Anyone except: {', '.join(leagues)}"
            return "Anyone"
        elif self.restriction_type == self.RESTRICTION_ONLY:
            leagues = self.restricted_leagues_list
            if leagues:
                return f"Only: {', '.join(leagues)}"
            return "Anyone"
        return "Anyone"

    @property
    def usage_type_display(self):
        """Human-readable usage type"""
        for value, label in self.USAGE_TYPES:
            if value == self.usage_type:
                return label
        return 'Games & Practices'

    @property
    def allows_games(self):
        """Check if this field allows games"""
        return self.usage_type in (self.USAGE_BOTH, self.USAGE_GAMES_ONLY, None)

    @property
    def allows_practices(self):
        """Check if this field allows practices"""
        return self.usage_type in (self.USAGE_BOTH, self.USAGE_PRACTICE_ONLY, None)

    def get_practice_capacity(self, is_late_slot=False):
        """Get practice capacity, optionally for late slots.

        Args:
            is_late_slot: True if checking for late time slots (e.g., 7:30 PM)

        Returns:
            int: Number of teams that can practice simultaneously
        """
        if is_late_slot and self.practice_capacity_late is not None:
            return self.practice_capacity_late
        return self.practice_capacity or 1

    @property
    def capacity_display(self):
        """Human-readable capacity description"""
        cap = self.practice_capacity or 1
        late_cap = self.practice_capacity_late

        if late_cap is not None and late_cap != cap:
            return f"{cap} teams (early), {late_cap} teams (late)"
        elif cap > 1:
            return f"{cap} teams"
        return "1 team"

    @property
    def derived_ownership(self):
        """Derive ownership from field slots.

        Returns: 'sdll', 'away', 'mixed', or 'none' (no slots)
        """
        from app.models.field_slot import FieldSlot
        slots = FieldSlot.query.filter_by(field_ID=self.ID, active=1).all()

        if not slots:
            return 'none'

        owned_count = sum(1 for s in slots if s.is_owned)
        away_count = len(slots) - owned_count

        if away_count == 0:
            return 'sdll'
        elif owned_count == 0:
            return 'away'
        else:
            return 'mixed'


class AlternateFieldName(db.Model):
    """Alternate names for fields"""
    __tablename__ = 'sdll_alternate_field_names'

    ID = db.Column(db.BigInteger, primary_key=True)
    active = db.Column(db.SmallInteger, default=1)
    field_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID'))
    alternate_name = db.Column(db.String(200))

    def __repr__(self):
        return f'<AlternateFieldName {self.alternate_name}>'
