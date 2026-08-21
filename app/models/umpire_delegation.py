"""Umpire delegation models - rules for auto-assigning umpire sources to games."""

from datetime import datetime
from app.extensions import db


class UmpireDelegationRule(db.Model):
    """Configurable umpire delegation percentages by league and season.

    Controls what percentage of games should go to Academy (SDLL),
    Diamond, or Dynamic umpires.
    """
    __tablename__ = 'sdll_umpire_delegation_rules'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('sdll_organizations.ID'), nullable=False)
    league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'), nullable=False)

    # Season scope (null = applies to all seasons)
    year = db.Column(db.SmallInteger)
    is_spring = db.Column(db.Boolean)

    # Allocation percentages (should sum to 100)
    academy_pct = db.Column(db.SmallInteger, default=0)  # SDLL umpires
    diamond_pct = db.Column(db.SmallInteger, default=0)
    dynamic_pct = db.Column(db.SmallInteger, default=0)

    # Status
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    organization = db.relationship('Organization', backref='delegation_rules')
    league = db.relationship('League', backref='delegation_rules')

    def __repr__(self):
        return f'<UmpireDelegationRule league={self.league_id}: {self.academy_pct}/{self.diamond_pct}/{self.dynamic_pct}>'

    @property
    def total_pct(self):
        """Sum of all allocation percentages."""
        return (self.academy_pct or 0) + (self.diamond_pct or 0) + (self.dynamic_pct or 0)

    def validate_percentages(self):
        """Ensure percentages sum to 100.

        Returns:
            bool: True if valid (sums to 100), False otherwise.
        """
        return self.total_pct == 100

    @property
    def is_season_specific(self):
        """Check if this is a season-specific rule."""
        return self.year is not None or self.is_spring is not None

    def get_allocation_dict(self):
        """Get allocations as a dictionary.

        Returns:
            dict: {'academy': pct, 'diamond': pct, 'dynamic': pct}
        """
        return {
            'academy': self.academy_pct or 0,
            'diamond': self.diamond_pct or 0,
            'dynamic': self.dynamic_pct or 0
        }

    @classmethod
    def get_for_league(cls, league_id, year=None, is_spring=None):
        """Get delegation rule for a league, falling back to default if no season-specific rule.

        Args:
            league_id: League ID
            year: Season year (optional)
            is_spring: Whether spring season (optional)

        Returns:
            UmpireDelegationRule or None
        """
        # Try season-specific first
        if year is not None and is_spring is not None:
            rule = cls.query.filter_by(
                league_id=league_id,
                year=year,
                is_spring=is_spring,
                active=True
            ).first()
            if rule:
                return rule

        # Fall back to default (no season)
        return cls.query.filter_by(
            league_id=league_id,
            year=None,
            is_spring=None,
            active=True
        ).first()

    @classmethod
    def get_all_for_org(cls, org_id=1, year=None, is_spring=None):
        """Get all delegation rules for an organization.

        Args:
            org_id: Organization ID
            year: Filter by season year (optional)
            is_spring: Filter by season type (optional)

        Returns:
            List of UmpireDelegationRule objects
        """
        query = cls.query.filter_by(org_id=org_id, active=True)

        if year is not None:
            # Include both season-specific and defaults
            query = query.filter(
                db.or_(cls.year == year, cls.year.is_(None))
            )

        return query.all()


class UmpireDelegationOverride(db.Model):
    """Manual override keywords for specific umpire routing.

    When a game's notes contain these keywords, it overrides
    the normal delegation rules.
    """
    __tablename__ = 'sdll_umpire_delegation_overrides'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # Keyword to match (case-insensitive)
    keyword = db.Column(db.String(50), nullable=False)

    # Where to route
    target_type = db.Column(db.String(20), nullable=False)  # 'academy' or 'partner'
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id',
                                                      ondelete='SET NULL'))

    # Description for admin UI
    description = db.Column(db.String(200))
    active = db.Column(db.Boolean, default=True)

    # Relationships
    organization = db.relationship('Organization', backref='delegation_overrides')
    partner = db.relationship('UmpirePartner')

    # Target type constants
    TARGET_ACADEMY = 'academy'
    TARGET_PARTNER = 'partner'
    TARGET_TYPES = [TARGET_ACADEMY, TARGET_PARTNER]

    def __repr__(self):
        return f'<UmpireDelegationOverride "{self.keyword}" -> {self.target_type}>'

    @property
    def target_name(self):
        """Human-readable target name."""
        if self.target_type == self.TARGET_ACADEMY:
            return 'Academy (SDLL)'
        if self.partner:
            return self.partner.name
        return self.target_type

    def matches(self, text):
        """Check if keyword matches text (case-insensitive).

        Args:
            text: Text to search for keyword

        Returns:
            bool: True if keyword found in text
        """
        if not text:
            return False
        return self.keyword.lower() in text.lower()

    @classmethod
    def get_active(cls, org_id=1):
        """Get all active overrides for an organization."""
        return cls.query.filter_by(org_id=org_id, active=True).all()

    @classmethod
    def find_matching(cls, text, org_id=1):
        """Find first matching override for given text.

        Args:
            text: Text to search for keywords
            org_id: Organization ID

        Returns:
            UmpireDelegationOverride or None
        """
        if not text:
            return None

        overrides = cls.get_active(org_id)
        for override in overrides:
            if override.matches(text):
                return override
        return None
