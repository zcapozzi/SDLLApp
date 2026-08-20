"""Practice Pairing model - maps to sdll_practice_pairings table

Stores practice pairings - teams that always share a field on specific days.
When both teams are scheduled to practice on that day, they automatically share a field.

Example: SB Tee Ball Team 1 and SB Tee Ball Team 2 always share a field on Mondays.
Both coaches have agreed to do joint practices.
"""

from app.extensions import db


class PracticePairing(db.Model):
    """Represents a practice pairing between two teams for a specific day of week."""
    __tablename__ = 'sdll_practice_pairings'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    team_one_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)
    team_two_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)
    day_of_week = db.Column(db.SmallInteger, nullable=False)  # 0=Mon, 1=Tue, ..., 6=Sun
    notes = db.Column(db.String(200))  # Optional reason for pairing
    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                          onupdate=db.func.current_timestamp())

    # Relationships
    team_one = db.relationship('TeamSeason', foreign_keys=[team_one_id])
    team_two = db.relationship('TeamSeason', foreign_keys=[team_two_id])

    # Day name mapping
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __repr__(self):
        return f'<PracticePairing {self.team_one_id} + {self.team_two_id} on {self.day_name}>'

    @property
    def day_name(self):
        """Return human-readable day name."""
        return self.DAY_NAMES[self.day_of_week] if 0 <= self.day_of_week <= 6 else 'Unknown'

    @property
    def season_name(self):
        """Return human-readable season name."""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    @classmethod
    def get_by_season(cls, year, is_spring):
        """Get all active pairings for a season, ordered by day of week."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).order_by(cls.day_of_week, cls.team_one_id).all()

    @classmethod
    def get_pairings_for_day(cls, year, is_spring, day_of_week):
        """Get pairings that apply to a specific day of week."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            day_of_week=day_of_week,
            active=1
        ).all()

    @classmethod
    def get_paired_team_ids(cls, year, is_spring):
        """Get set of all team IDs that are in any pairing (for violation exemption)."""
        pairings = cls.get_by_season(year, is_spring)
        team_ids = set()
        for p in pairings:
            team_ids.add(p.team_one_id)
            team_ids.add(p.team_two_id)
        return team_ids

    @classmethod
    def get_pairing_pairs(cls, year, is_spring):
        """Get a set of (team_id, team_id) tuples representing all pairings.

        Both orderings are included, e.g., (1, 2) and (2, 1).
        Used for quick lookup when checking if two teams are paired.
        """
        pairings = cls.get_by_season(year, is_spring)
        pairs = set()
        for p in pairings:
            pairs.add((p.team_one_id, p.team_two_id))
            pairs.add((p.team_two_id, p.team_one_id))
        return pairs

    @classmethod
    def get_pairing_pairs_for_day(cls, year, is_spring, day_of_week):
        """Get a set of (team_id, team_id) tuples for pairings on a specific day.

        Both orderings are included, e.g., (1, 2) and (2, 1).
        """
        pairings = cls.get_pairings_for_day(year, is_spring, day_of_week)
        pairs = set()
        for p in pairings:
            pairs.add((p.team_one_id, p.team_two_id))
            pairs.add((p.team_two_id, p.team_one_id))
        return pairs

    @classmethod
    def add_pairing(cls, year, is_spring, team_one_id, team_two_id, day_of_week, notes=None):
        """Create a new pairing, checking for duplicates.

        Returns the pairing if created, or None if duplicate exists.
        """
        # Normalize order (smaller ID first) to prevent duplicates
        if team_one_id > team_two_id:
            team_one_id, team_two_id = team_two_id, team_one_id

        # Check for existing pairing (same teams, same day)
        existing = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            team_one_id=team_one_id,
            team_two_id=team_two_id,
            day_of_week=day_of_week
        ).first()

        if existing:
            if existing.active == 0:
                # Reactivate soft-deleted pairing
                existing.active = 1
                existing.notes = notes
                db.session.commit()
                return existing
            return None  # Already exists and active

        pairing = cls(
            year=year,
            is_spring=is_spring,
            team_one_id=team_one_id,
            team_two_id=team_two_id,
            day_of_week=day_of_week,
            notes=notes,
            active=1
        )
        db.session.add(pairing)
        db.session.commit()
        return pairing

    def delete(self):
        """Soft delete this pairing."""
        self.active = 0
        db.session.commit()

    @classmethod
    def are_teams_paired(cls, year, is_spring, team_one_id, team_two_id, day_of_week=None):
        """Check if two teams are paired.

        Args:
            year: Season year
            is_spring: 1 for spring, 0 for fall
            team_one_id: First team's ID
            team_two_id: Second team's ID
            day_of_week: Optional - if provided, only checks for that day

        Returns:
            True if teams are paired (on the specified day if provided)
        """
        # Normalize order
        if team_one_id > team_two_id:
            team_one_id, team_two_id = team_two_id, team_one_id

        query = cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            team_one_id=team_one_id,
            team_two_id=team_two_id,
            active=1
        )

        if day_of_week is not None:
            query = query.filter_by(day_of_week=day_of_week)

        return query.first() is not None
