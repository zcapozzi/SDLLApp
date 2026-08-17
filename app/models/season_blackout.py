"""Season Blackout model - maps to sdll_season_blackouts table

Represents dates when no games or practices should be scheduled
for an entire season (e.g., Labor Day Weekend, Thanksgiving).
"""

from app.extensions import db


class SeasonBlackout(db.Model):
    """Represents a season-wide blackout date."""
    __tablename__ = 'sdll_season_blackouts'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    blackout_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    def __repr__(self):
        return f'<SeasonBlackout {self.blackout_date} - {self.reason}>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active blackout dates for a season, ordered by date."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.blackout_date).all()

    @classmethod
    def get_blackout_dates_set(cls, year, is_spring):
        """Get a set of blackout dates for quick lookup."""
        blackouts = cls.get_by_season(year, is_spring)
        return {b.blackout_date for b in blackouts}

    @classmethod
    def is_blackout_date(cls, year, is_spring, check_date):
        """Check if a specific date is a blackout date."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            blackout_date=check_date,
            active=1
        ).first() is not None

    @classmethod
    def add_blackout(cls, year, is_spring, blackout_date, reason=None):
        """Add a new blackout date. Returns the blackout or None if duplicate."""
        existing = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
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
            year=year,
            is_spring=is_spring,
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

    @classmethod
    def copy_to_new_season(cls, source_year, source_is_spring, target_year, target_is_spring):
        """Copy blackout dates from one season to another.

        Note: Dates are not automatically adjusted - only useful for copying
        recurring holidays that fall on the same calendar dates.
        """
        source_blackouts = cls.get_by_season(source_year, source_is_spring)
        new_blackouts = []

        for source in source_blackouts:
            # Check if target already has this date
            existing = cls.query.filter_by(
                year=target_year,
                is_spring=target_is_spring,
                blackout_date=source.blackout_date,
                active=1
            ).first()

            if not existing:
                new_blackout = cls(
                    year=target_year,
                    is_spring=target_is_spring,
                    blackout_date=source.blackout_date,
                    reason=source.reason,
                    active=1
                )
                db.session.add(new_blackout)
                new_blackouts.append(new_blackout)

        db.session.commit()
        return new_blackouts
