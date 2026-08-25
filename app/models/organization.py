"""Organization model - maps to sdll_organizations table"""

from datetime import datetime, timezone as tz
from zoneinfo import ZoneInfo
from app.extensions import db


class Organization(db.Model):
    """Represents an organization (Little League) that teams belong to.

    SDLL is the home organization. External organizations like Bull City,
    Morrisville, etc. can be added for inter-league games.
    """
    __tablename__ = 'sdll_organizations'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)
    name = db.Column(db.String(100), nullable=False)  # "South Durham Little League"
    short_name = db.Column(db.String(30))  # "SDLL" or "Bull City"
    location = db.Column(db.String(100))  # City/area
    timezone = db.Column(db.String(50), default='America/New_York')  # IANA timezone
    is_home_org = db.Column(db.SmallInteger, default=0)  # 1 = SDLL itself
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationship to teams (defined via backref in TeamSeason)

    def __repr__(self):
        return f'<Organization {self.short_name or self.name}>'

    @property
    def display_name(self):
        """Return short name if available, otherwise full name"""
        return self.short_name or self.name

    @classmethod
    def get_all_active(cls):
        """Get all active organizations"""
        return cls.query.filter_by(active=1).order_by(cls.is_home_org.desc(), cls.name).all()

    @classmethod
    def get_external(cls):
        """Get all external (non-home) organizations"""
        return cls.query.filter_by(active=1, is_home_org=0).order_by(cls.name).all()

    @classmethod
    def get_home_org(cls):
        """Get the home organization (SDLL)"""
        return cls.query.filter_by(is_home_org=1, active=1).first()

    @classmethod
    def get_or_create(cls, name, short_name=None):
        """Get existing org by name or create new one"""
        org = cls.query.filter_by(name=name, active=1).first()
        if not org:
            org = cls(name=name, short_name=short_name)
            db.session.add(org)
            db.session.commit()
        return org

    @classmethod
    def get_default_timezone(cls):
        """Get the timezone for the home organization (default for all displays)."""
        home = cls.get_home_org()
        if home and home.timezone:
            return home.timezone
        return 'America/New_York'

    @classmethod
    def utc_to_local(cls, utc_dt, tz_name=None):
        """
        Convert a UTC datetime to local time.

        Args:
            utc_dt: datetime object (assumed UTC if naive)
            tz_name: IANA timezone name (e.g., 'America/New_York'). If None, uses home org timezone.

        Returns:
            datetime object in local timezone
        """
        if utc_dt is None:
            return None

        if tz_name is None:
            tz_name = cls.get_default_timezone()

        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            local_tz = ZoneInfo('America/New_York')

        # If naive datetime, assume UTC
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=tz.utc)

        return utc_dt.astimezone(local_tz)

    @classmethod
    def format_local_datetime(cls, utc_dt, fmt='%m/%d/%Y %I:%M %p', tz_name=None):
        """
        Convert UTC datetime to local time and format as string.

        Args:
            utc_dt: datetime object (assumed UTC if naive)
            fmt: strftime format string
            tz_name: IANA timezone name. If None, uses home org timezone.

        Returns:
            Formatted string in local time, or empty string if None
        """
        local_dt = cls.utc_to_local(utc_dt, tz_name)
        if local_dt is None:
            return ''
        return local_dt.strftime(fmt)
