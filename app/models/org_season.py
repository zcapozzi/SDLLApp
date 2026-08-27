"""Organization Season model - maps to sdll_org_seasons table"""

from app.extensions import db


class OrgSeason(db.Model):
    """Represents a season for an organization.

    Tracks which seasons exist for an organization and which is the current one.
    If no season is marked as current, falls back to the one with the latest
    season_started_at date.
    """
    __tablename__ = 'sdll_org_seasons'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    org_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=True)
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    is_current = db.Column(db.SmallInteger, default=0)
    setup_mode = db.Column(db.SmallInteger, default=0)  # Can set up while previous is current
    season_started_at = db.Column(db.DateTime)
    season_ended_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationship to organization
    organization = db.relationship('Organization', backref='seasons')

    def __repr__(self):
        return f'<OrgSeason {self.season_name}>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    @classmethod
    def get_current_season(cls, org_id=None):
        """Get the current season for an organization.

        Args:
            org_id: Organization ID. If None, uses home org (SDLL).

        Returns:
            OrgSeason instance or None if no seasons exist.

        Logic:
            1. First look for a season explicitly marked as is_current=1
            2. If none found, fall back to the season with the latest season_started_at
        """
        # Try to find explicitly marked current season
        query = cls.query.filter_by(is_current=1)
        if org_id is not None:
            query = query.filter_by(org_id=org_id)
        else:
            query = query.filter(cls.org_id.is_(None))

        current = query.first()
        if current:
            return current

        # Fall back to latest started season
        query = cls.query
        if org_id is not None:
            query = query.filter_by(org_id=org_id)
        else:
            query = query.filter(cls.org_id.is_(None))

        return query.order_by(
            cls.season_started_at.desc().nullslast(),
            cls.year.desc(),
            cls.is_spring.desc()
        ).first()

    @classmethod
    def get_current_year_and_season(cls, org_id=None):
        """Get current year and is_spring as a tuple.

        Returns:
            (year, is_spring) tuple, or (None, None) if no seasons exist.
        """
        current = cls.get_current_season(org_id)
        if current:
            return (current.year, current.is_spring)
        return (None, None)

    @classmethod
    def set_current_season(cls, year, is_spring, org_id=None):
        """Set a season as the current season for an organization.

        Clears is_current from all other seasons for that org.

        Args:
            year: The year to set as current
            is_spring: 1 for Spring, 0 for Fall
            org_id: Organization ID. If None, uses home org.

        Returns:
            The OrgSeason that was set as current, or None if not found.
        """
        # Clear current flag from all seasons for this org
        if org_id is not None:
            cls.query.filter_by(org_id=org_id).update({'is_current': 0})
        else:
            cls.query.filter(cls.org_id.is_(None)).update({'is_current': 0})

        # Set the new current season
        if org_id is not None:
            season = cls.query.filter_by(
                org_id=org_id,
                year=year,
                is_spring=is_spring
            ).first()
        else:
            season = cls.query.filter(
                cls.org_id.is_(None),
                cls.year == year,
                cls.is_spring == is_spring
            ).first()

        if season:
            season.is_current = 1
            db.session.commit()

        return season

    @classmethod
    def get_all_for_org(cls, org_id=None):
        """Get all seasons for an organization, ordered by year/season.

        Args:
            org_id: Organization ID. If None, uses home org.

        Returns:
            List of OrgSeason instances.
        """
        query = cls.query
        if org_id is not None:
            query = query.filter_by(org_id=org_id)
        else:
            query = query.filter(cls.org_id.is_(None))

        return query.order_by(
            cls.year.desc(),
            cls.is_spring.desc()
        ).all()

    @classmethod
    def create_season(cls, year, is_spring, org_id=None, set_as_current=False):
        """Create a new season for an organization.

        Args:
            year: The year
            is_spring: 1 for Spring, 0 for Fall
            org_id: Organization ID. If None, uses home org.
            set_as_current: If True, sets this as the current season.

        Returns:
            The created OrgSeason instance.
        """
        from datetime import datetime

        season = cls(
            org_id=org_id,
            year=year,
            is_spring=is_spring,
            is_current=1 if set_as_current else 0,
            season_started_at=datetime.utcnow() if set_as_current else None
        )

        if set_as_current:
            # Clear current from other seasons
            if org_id is not None:
                cls.query.filter_by(org_id=org_id).update({'is_current': 0})
            else:
                cls.query.filter(cls.org_id.is_(None)).update({'is_current': 0})

        db.session.add(season)
        db.session.commit()
        return season
