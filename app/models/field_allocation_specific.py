"""Field Allocation Specific model - maps to sdll_field_allocations_specific table

Represents specific-date field allocations (one-off events, not recurring weekly).
This complements FieldSlot which handles recurring weekly allocations.
"""

from app.extensions import db


class FieldAllocationSpecific(db.Model):
    """Represents a specific-date field allocation.

    Unlike FieldSlot (recurring weekly by day_of_week), this stores
    allocations for specific dates - useful for:
    - Tournament days with different schedules
    - Make-up game slots
    - Special events
    - Holiday schedule changes
    """
    __tablename__ = 'sdll_field_allocations_specific'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    field_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)  # 0=Fall, 1=Spring
    allocation_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    league = db.Column(db.String(50))  # NULL = any league can use
    is_owned = db.Column(db.SmallInteger, default=1)  # 1 = SDLL owns, 0 = away only
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    # Relationship to Field
    field = db.relationship('Field', backref=db.backref('specific_allocations', lazy='dynamic'))

    def __repr__(self):
        return f'<FieldAllocationSpecific {self.field.location_title if self.field else "?"} {self.allocation_date} {self.start_time}>'

    @property
    def date_display(self):
        """Return formatted date"""
        return self.allocation_date.strftime('%a %m/%d') if self.allocation_date else ''

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
        """Get all active specific allocations for a season, ordered by date and field"""
        from app.models.field import Field
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).join(Field).order_by(
            cls.allocation_date,
            Field.location_title,
            cls.start_time
        ).all()

    @classmethod
    def get_by_date(cls, year, is_spring, target_date):
        """Get all active specific allocations for a specific date"""
        from app.models.field import Field
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            allocation_date=target_date,
            active=1
        ).join(Field).order_by(
            Field.location_title,
            cls.start_time
        ).all()

    @classmethod
    def get_by_field_and_season(cls, field_id, year, is_spring):
        """Get all active specific allocations for a field and season"""
        return cls.query.filter_by(
            field_ID=field_id,
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.allocation_date, cls.start_time).all()

    @classmethod
    def get_by_field_and_date(cls, field_id, target_date):
        """Get all active specific allocations for a field on a specific date"""
        return cls.query.filter_by(
            field_ID=field_id,
            allocation_date=target_date,
            active=1
        ).order_by(cls.start_time).all()

    @classmethod
    def get_date_range(cls, year, is_spring, start_date, end_date):
        """Get all active specific allocations within a date range"""
        from app.models.field import Field
        return cls.query.filter(
            cls.year == year,
            cls.is_spring == is_spring,
            cls.allocation_date >= start_date,
            cls.allocation_date <= end_date,
            cls.active == 1
        ).join(Field).order_by(
            cls.allocation_date,
            Field.location_title,
            cls.start_time
        ).all()

    def delete(self):
        """Soft delete this allocation"""
        self.active = 0
        db.session.commit()
