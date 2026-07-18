"""League model - maps to sdll_leagues table"""

from datetime import time
from app.extensions import db


class League(db.Model):
    """Represents a league/division"""
    __tablename__ = 'sdll_leagues'

    ID = db.Column(db.BigInteger, primary_key=True)
    active = db.Column(db.SmallInteger, default=1)
    display_name = db.Column(db.String(100))        # Spring/canonical name
    fall_display_name = db.Column(db.String(100))   # Fall name (NULL = use display_name)
    pitch_type = db.Column(db.String(20), default='kid_pitch')  # tee_ball, machine_pitch, kid_pitch
    only_assignr_groups = db.Column(db.String(1000))
    earliest_start_time = db.Column(db.Time)  # NULL = no restriction
    latest_start_time = db.Column(db.Time)    # NULL = no restriction

    # Field rules - NULL means "anywhere"
    allowed_game_fields = db.Column(db.Text)      # Comma-separated field IDs
    allowed_practice_fields = db.Column(db.Text)  # Comma-separated field IDs
    preferred_fields = db.Column(db.Text)         # Comma-separated field IDs in preference order
    required_days = db.Column(db.String(50))      # Comma-separated day numbers (0=Mon, 6=Sun)

    # Pitch type constants
    PITCH_TEE_BALL = 'tee_ball'
    PITCH_MACHINE = 'machine_pitch'
    PITCH_KID = 'kid_pitch'

    PITCH_TYPES = [
        ('tee_ball', 'Tee Ball'),
        ('machine_pitch', 'Machine Pitch'),
        ('kid_pitch', 'Kid Pitch'),
    ]

    def __repr__(self):
        return f'<League {self.display_name}>'

    @classmethod
    def get_all_active(cls):
        """Get all active leagues"""
        return cls.query.filter_by(active=1).order_by(cls.display_name).all()

    @classmethod
    def get_by_name(cls, name):
        """Find league by display name (checks both spring and fall names)"""
        # Try spring/canonical name first
        league = cls.query.filter_by(display_name=name, active=1).first()
        if league:
            return league
        # Try fall name
        return cls.query.filter_by(fall_display_name=name, active=1).first()

    def get_seasonal_name(self, is_spring):
        """Get the appropriate display name for the season.

        Args:
            is_spring: True for Spring, False for Fall

        Returns:
            The seasonal display name
        """
        if is_spring or not self.fall_display_name:
            return self.display_name
        return self.fall_display_name

    @property
    def has_seasonal_names(self):
        """Check if this league has different names for Spring and Fall"""
        return self.fall_display_name is not None

    @property
    def pitch_type_display(self):
        """Human-readable pitch type"""
        for value, label in self.PITCH_TYPES:
            if value == self.pitch_type:
                return label
        return 'Kid Pitch'

    def can_play_at_time(self, start_time):
        """Check if this league can play a game starting at the given time.

        Args:
            start_time: datetime.time object or string like '17:30'

        Returns:
            bool: True if the league can play at this time
        """
        if isinstance(start_time, str):
            start_time = time.fromisoformat(start_time)

        if self.earliest_start_time and start_time < self.earliest_start_time:
            return False
        if self.latest_start_time and start_time > self.latest_start_time:
            return False
        return True

    @property
    def time_restriction_display(self):
        """Human-readable time restriction description"""
        if not self.earliest_start_time and not self.latest_start_time:
            return "Any time"

        if self.earliest_start_time and self.latest_start_time:
            early = self.earliest_start_time.strftime('%I:%M %p').lstrip('0')
            late = self.latest_start_time.strftime('%I:%M %p').lstrip('0')
            return f"{early} - {late}"

        if self.latest_start_time:
            late = self.latest_start_time.strftime('%I:%M %p').lstrip('0')
            return f"Before {late}"

        if self.earliest_start_time:
            early = self.earliest_start_time.strftime('%I:%M %p').lstrip('0')
            return f"After {early}"

        return "Any time"

    # Field rules helpers
    DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def _parse_id_list(self, value):
        """Parse comma-separated ID string to list of integers"""
        if not value:
            return []
        return [int(x.strip()) for x in value.split(',') if x.strip().isdigit()]

    def _format_id_list(self, ids):
        """Format list of integers to comma-separated string"""
        if not ids:
            return None
        return ','.join(str(x) for x in ids)

    @property
    def allowed_game_field_ids(self):
        """Get allowed game fields as list of IDs"""
        return self._parse_id_list(self.allowed_game_fields)

    @allowed_game_field_ids.setter
    def allowed_game_field_ids(self, ids):
        self.allowed_game_fields = self._format_id_list(ids)

    @property
    def allowed_practice_field_ids(self):
        """Get allowed practice fields as list of IDs"""
        return self._parse_id_list(self.allowed_practice_fields)

    @allowed_practice_field_ids.setter
    def allowed_practice_field_ids(self, ids):
        self.allowed_practice_fields = self._format_id_list(ids)

    @property
    def preferred_field_ids(self):
        """Get preferred fields as list of IDs (in order)"""
        return self._parse_id_list(self.preferred_fields)

    @preferred_field_ids.setter
    def preferred_field_ids(self, ids):
        self.preferred_fields = self._format_id_list(ids)

    @property
    def required_day_numbers(self):
        """Get required days as list of integers (0=Mon, 6=Sun)"""
        return self._parse_id_list(self.required_days)

    @required_day_numbers.setter
    def required_day_numbers(self, days):
        self.required_days = self._format_id_list(days)

    @property
    def required_days_display(self):
        """Human-readable required days"""
        days = self.required_day_numbers
        if not days:
            return "Any day"
        return ', '.join(self.DAY_NAMES[d] for d in days if 0 <= d <= 6)

    def can_play_at_field(self, field_id, is_practice=False):
        """Check if this league can play at a given field.

        Args:
            field_id: The field ID to check
            is_practice: True if checking for practice, False for game

        Returns:
            bool: True if allowed
        """
        if is_practice:
            allowed = self.allowed_practice_field_ids
        else:
            allowed = self.allowed_game_field_ids

        # Empty list means anywhere is allowed
        if not allowed:
            return True
        return field_id in allowed

    def can_play_on_day(self, day_number):
        """Check if this league can play on a given day.

        Args:
            day_number: 0=Monday, 6=Sunday

        Returns:
            bool: True if allowed
        """
        required = self.required_day_numbers
        # Empty list means any day is allowed
        if not required:
            return True
        return day_number in required

    def get_field_preference_score(self, field_id):
        """Get preference score for a field (lower is better).

        Returns:
            int: 0 for most preferred, 1 for second, etc.
                 999 if not in preference list (but still allowed)
        """
        preferred = self.preferred_field_ids
        if not preferred:
            return 0  # No preferences = all equal
        try:
            return preferred.index(field_id)
        except ValueError:
            return 999  # Not in preference list

    @property
    def game_fields_display(self):
        """Human-readable game fields restriction"""
        ids = self.allowed_game_field_ids
        if not ids:
            return "Any field"
        from app.models.field import Field
        fields = Field.query.filter(Field.ID.in_(ids)).all()
        return ', '.join(f.location_title for f in fields) if fields else "Any field"

    @property
    def practice_fields_display(self):
        """Human-readable practice fields restriction"""
        ids = self.allowed_practice_field_ids
        if not ids:
            return "Any field"
        from app.models.field import Field
        fields = Field.query.filter(Field.ID.in_(ids)).all()
        return ', '.join(f.location_title for f in fields) if fields else "Any field"
