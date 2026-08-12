"""Organization model - maps to sdll_organizations table"""

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
