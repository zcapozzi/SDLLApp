"""Field Blackout model - maps to sdll_field_blackouts table

Represents dates when a specific field is unavailable
(e.g., maintenance, tournaments, reservations by other organizations).
"""

from app.extensions import db


class FieldBlackout(db.Model):
    """Represents a field-specific blackout date."""
    __tablename__ = 'sdll_field_blackouts'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    field_ID = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID'), nullable=False)
    blackout_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    # Relationship to Field
    field = db.relationship('Field', backref=db.backref('blackouts', lazy='dynamic'))

    def __repr__(self):
        return f'<FieldBlackout {self.field.location_title if self.field else "?"} {self.blackout_date}>'

    @classmethod
    def get_by_field(cls, field_id):
        """Get all active blackout dates for a field, ordered by date."""
        return cls.query.filter_by(
            field_ID=field_id,
            active=1
        ).order_by(cls.blackout_date).all()

    @classmethod
    def get_blackout_dates_for_field(cls, field_id):
        """Get a set of blackout dates for a specific field."""
        blackouts = cls.get_by_field(field_id)
        return {b.blackout_date for b in blackouts}

    @classmethod
    def is_field_blacked_out(cls, field_id, check_date):
        """Check if a specific field is blacked out on a given date."""
        return cls.query.filter_by(
            field_ID=field_id,
            blackout_date=check_date,
            active=1
        ).first() is not None

    @classmethod
    def add_blackout(cls, field_id, blackout_date, reason=None):
        """Add a new blackout date. Returns the blackout or None if duplicate."""
        existing = cls.query.filter_by(
            field_ID=field_id,
            blackout_date=blackout_date
        ).first()

        if existing:
            if existing.active == 0:
                # Reactivate soft-deleted blackout
                existing.active = 1
                existing.reason = reason
                db.session.commit()
                return existing
            return None  # Already exists and active

        blackout = cls(
            field_ID=field_id,
            blackout_date=blackout_date,
            reason=reason,
            active=1
        )
        db.session.add(blackout)
        db.session.commit()
        return blackout

    def delete(self):
        """Soft delete this blackout date."""
        self.active = 0
        db.session.commit()
