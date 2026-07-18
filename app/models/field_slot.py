"""Field Slot model - maps to sdll_field_slots table"""

from app.extensions import db


class FieldSlot(db.Model):
    """Represents an available time slot at a field for a specific season.

    Field slots define when a field is available from Durham Parks and Rec.
    These are separate from actual games - they represent potential scheduling windows.
    """
    __tablename__ = 'sdll_field_slots'

    slot_ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    field_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)  # 0=Fall, 1=Spring
    day_of_week = db.Column(db.SmallInteger, nullable=False)  # 0=Mon, 1=Tue, ..., 6=Sun
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    league = db.Column(db.String(50))  # NULL = any league can use
    is_owned = db.Column(db.SmallInteger, default=1)  # 1 = SDLL owns, 0 = away only
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    # Relationship to Field
    field = db.relationship('Field', backref=db.backref('slots', lazy='dynamic'))

    # Day names for display
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __repr__(self):
        return f'<FieldSlot {self.field.location_title if self.field else "?"} {self.day_name} {self.start_time}>'

    @property
    def day_name(self):
        """Return day of week name"""
        return self.DAY_NAMES[self.day_of_week] if 0 <= self.day_of_week <= 6 else 'Unknown'

    @property
    def day_abbrev(self):
        """Return abbreviated day of week"""
        return self.DAY_ABBREV[self.day_of_week] if 0 <= self.day_of_week <= 6 else '???'

    @property
    def time_display(self):
        """Return formatted time range"""
        start = self.start_time.strftime('%I:%M %p').lstrip('0') if self.start_time else ''
        end = self.end_time.strftime('%I:%M %p').lstrip('0') if self.end_time else ''
        return f'{start} - {end}'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active slots for a specific season, ordered by field and day"""
        from app.models.field import Field
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).join(Field).order_by(
            Field.location_title,
            cls.day_of_week,
            cls.start_time
        ).all()

    @classmethod
    def get_by_field_and_season(cls, field_id, year, is_spring):
        """Get all active slots for a specific field and season"""
        return cls.query.filter_by(
            field_ID=field_id,
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.day_of_week, cls.start_time).all()

    @classmethod
    def copy_to_new_season(cls, source_year, source_is_spring, target_year, target_is_spring):
        """Copy all field slots from source season to target season."""
        source_slots = cls.get_by_season(source_year, source_is_spring)
        new_slots = []

        for source_slot in source_slots:
            new_slot = FieldSlot(
                active=1,
                field_ID=source_slot.field_ID,
                year=target_year,
                is_spring=target_is_spring,
                day_of_week=source_slot.day_of_week,
                start_time=source_slot.start_time,
                end_time=source_slot.end_time,
                league=source_slot.league,
                is_owned=source_slot.is_owned,
                notes=source_slot.notes
            )
            db.session.add(new_slot)
            new_slots.append(new_slot)

        db.session.commit()
        return new_slots

    @classmethod
    def delete_season_slots(cls, year, is_spring):
        """Soft delete all slots for a season. Returns count."""
        slots = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).all()

        count = 0
        for slot in slots:
            slot.active = 0
            count += 1

        db.session.commit()
        return count

    @classmethod
    def hard_delete_season_slots(cls, year, is_spring):
        """Permanently delete all slots for a season. Returns count."""
        count = cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).delete()
        db.session.commit()
        return count
