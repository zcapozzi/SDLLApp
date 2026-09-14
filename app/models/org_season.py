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
    org_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    season_desc = db.Column(db.String(20), nullable=False)  # e.g., "Spring 2027"
    is_spring = db.Column(db.SmallInteger, nullable=False)
    is_current = db.Column(db.SmallInteger, default=0)
    setup_mode = db.Column(db.SmallInteger, default=0)  # Can set up while previous is current
    season_started_at = db.Column(db.DateTime)
    season_ended_at = db.Column(db.DateTime)
    training_date = db.Column(db.Date)  # Umpire training session date
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationship to organization
    organization = db.relationship('Organization', backref='seasons')

    def __repr__(self):
        return f'<OrgSeason {self.season_name}>'

    @property
    def season_name(self):
        """Return human-readable season name"""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    def get_training_date(self):
        """Get training date with fallback to 2 weeks before earliest opening day.

        Returns:
            date object or None if no training date can be determined.
        """
        if self.training_date:
            return self.training_date

        # Fallback: 2 weeks before earliest opening_day_date from LeagueSeason
        from app.models.league_season import LeagueSeason
        from datetime import timedelta

        league_seasons = LeagueSeason.query.filter_by(
            year=self.year,
            is_spring=self.is_spring,
            active=1
        ).filter(LeagueSeason.opening_day_date.isnot(None)).all()

        if league_seasons:
            earliest = min(ls.opening_day_date for ls in league_seasons)
            return earliest - timedelta(days=14)

        return None

    # Default organization ID for SDLL
    DEFAULT_ORG_ID = 1

    @classmethod
    def get_current_season(cls, org_id=None):
        """Get the current season for an organization.

        Args:
            org_id: Organization ID. If None, uses home org (SDLL, org_id=1).

        Returns:
            OrgSeason instance or None if no seasons exist.

        Logic:
            1. First look for a season explicitly marked as is_current=1
            2. If none found, fall back to the season with the latest season_started_at
        """
        # Use default org if not specified
        if org_id is None:
            org_id = cls.DEFAULT_ORG_ID

        # Try to find explicitly marked current season
        query = cls.query.filter_by(is_current=1, org_id=org_id)

        current = query.first()
        if current:
            return current

        # Fall back to latest started season
        # MySQL doesn't support NULLS LAST, so use CASE to sort NULLs last
        query = cls.query.filter_by(org_id=org_id)

        return query.order_by(
            db.case((cls.season_started_at.is_(None), 1), else_=0),  # NULLs last
            cls.season_started_at.desc(),
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
            org_id: Organization ID. If None, uses home org (SDLL, org_id=1).

        Returns:
            The OrgSeason that was set as current, or None if not found.
        """
        # Use default org if not specified
        if org_id is None:
            org_id = cls.DEFAULT_ORG_ID

        # Clear current flag from all seasons for this org
        cls.query.filter_by(org_id=org_id).update({'is_current': 0})

        # Set the new current season
        season = cls.query.filter_by(
            org_id=org_id,
            year=year,
            is_spring=is_spring
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
        if org_id is None:
            org_id = cls.DEFAULT_ORG_ID

        return cls.query.filter_by(org_id=org_id).order_by(
            cls.year.desc(),
            cls.is_spring.desc()
        ).all()

    @classmethod
    def create_season(cls, year, is_spring, org_id=None, set_as_current=False,
                      generate_campaigns=True, season_desc=None):
        """Create a new season for an organization.

        Args:
            year: The year
            is_spring: 1 for Spring, 0 for Fall
            org_id: Organization ID. If None, uses home org.
            set_as_current: If True, sets this as the current season.
            generate_campaigns: If True, generates email campaigns for the season.
            season_desc: Custom description. If None, generates from is_spring/year.

        Returns:
            The created OrgSeason instance.
        """
        from datetime import datetime

        # Use default org if not specified
        if org_id is None:
            org_id = cls.DEFAULT_ORG_ID

        # Generate season_desc if not provided
        if season_desc is None:
            season_desc = f'{"Spring" if is_spring else "Fall"} {year}'

        season = cls(
            org_id=org_id,
            year=year,
            season_desc=season_desc,
            is_spring=is_spring,
            is_current=1 if set_as_current else 0,
            season_started_at=datetime.utcnow() if set_as_current else None
        )

        if set_as_current:
            # Clear current from other seasons for this org
            cls.query.filter_by(org_id=org_id).update({'is_current': 0})

        db.session.add(season)
        db.session.commit()

        # Generate email campaigns for the new season
        if generate_campaigns:
            season.ensure_campaigns()

        return season

    def ensure_campaigns(self):
        """Ensure email campaigns exist for this season.

        Creates any missing campaigns based on active templates.
        Safe to call multiple times - will not duplicate campaigns.

        Returns:
            List of newly created EmailCampaignInstance objects.
        """
        try:
            from app.services.email_campaign_service import EmailCampaignService
            service = EmailCampaignService()
            return service.generate_all_campaigns_for_season(self)
        except Exception as e:
            # Log but don't fail if campaign generation fails
            print(f"Warning: Failed to generate campaigns for {self.season_name}: {e}")
            return []
