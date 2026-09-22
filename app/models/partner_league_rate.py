"""PartnerLeagueRate model - league-specific rate overrides for umpire partners.

This allows setting custom rates per partner/league combination, e.g.:
- Diamond + AA = $45/umpire
- Diamond + T-Ball = $40/umpire
- Dynamic + Majors = $55/game flat

Rate lookup hierarchy:
1. PartnerLeagueRate (partner + league + season) - most specific
2. PartnerLeagueRate (partner + league + NULL season) - all seasons
3. UmpirePartner.rate_normal / rate_ntl - partner default
"""

from datetime import datetime
from decimal import Decimal
from app.extensions import db


class PartnerLeagueRate(db.Model):
    """League-specific rate overrides for umpire partners.

    Allows setting different rates for each league when using a partner.
    For example, Diamond might charge $85/umpire for Majors but $75 for AA.
    """
    __tablename__ = 'sdll_partner_league_rates'

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'), nullable=False)
    league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'), nullable=False)

    # Rates (NULL = use partner default)
    rate_normal = db.Column(db.Numeric(8, 2))
    rate_ntl = db.Column(db.Numeric(8, 2))  # No-time-limit games

    # Optional season scope (NULL = all seasons)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Unique: one rate per partner/league/season combo
    __table_args__ = (
        db.UniqueConstraint('partner_id', 'league_id', 'org_season_id',
                           name='uq_partner_league_season'),
    )

    # Relationships
    partner = db.relationship('UmpirePartner', backref='league_rates')
    league = db.relationship('League', backref='partner_rates')
    org_season = db.relationship('OrgSeason', backref='partner_league_rates')

    def __repr__(self):
        league_name = self.league.display_name if self.league else f'league_{self.league_id}'
        partner_code = self.partner.short_code if self.partner else f'partner_{self.partner_id}'
        return f'<PartnerLeagueRate {partner_code} + {league_name}: ${self.rate_normal}>'

    @property
    def effective_rate_normal(self):
        """Get rate_normal, falling back to partner default if not set."""
        if self.rate_normal is not None:
            return Decimal(str(self.rate_normal))
        if self.partner and self.partner.rate_normal:
            return Decimal(str(self.partner.rate_normal))
        return Decimal('0')

    @property
    def effective_rate_ntl(self):
        """Get rate_ntl, falling back to rate_normal or partner default."""
        if self.rate_ntl is not None:
            return Decimal(str(self.rate_ntl))
        if self.rate_normal is not None:
            return Decimal(str(self.rate_normal))
        if self.partner:
            if self.partner.rate_ntl:
                return Decimal(str(self.partner.rate_ntl))
            if self.partner.rate_normal:
                return Decimal(str(self.partner.rate_normal))
        return Decimal('0')

    @property
    def has_override(self):
        """Check if this record has any rate overrides set."""
        return self.rate_normal is not None or self.rate_ntl is not None

    @property
    def season_display(self):
        """Get display name for the season scope."""
        if self.org_season:
            return self.org_season.display_name
        return "All Seasons"

    @classmethod
    def get_for_partner(cls, partner_id, org_season_id=None):
        """Get all league rate overrides for a partner.

        Args:
            partner_id: UmpirePartner ID
            org_season_id: Optional season filter (None = all seasons)

        Returns:
            List of PartnerLeagueRate records
        """
        query = cls.query.filter_by(partner_id=partner_id)
        if org_season_id is not None:
            # Include both season-specific and all-season rates
            query = query.filter(
                (cls.org_season_id == org_season_id) |
                (cls.org_season_id.is_(None))
            )
        return query.all()

    @classmethod
    def get_rate(cls, partner_id, league_id, is_ntl=False, org_season_id=None):
        """Get the effective rate for a partner/league combination.

        Looks up in order of specificity:
        1. Season-specific rate for this partner + league
        2. All-season rate for this partner + league
        3. Partner's default rate

        Args:
            partner_id: UmpirePartner ID
            league_id: League ID
            is_ntl: True for no-time-limit games
            org_season_id: Optional season context

        Returns:
            Decimal rate amount, or None if no rate found
        """
        from app.models.umpire_partner import UmpirePartner

        # Try season-specific rate first
        if org_season_id:
            rate_record = cls.query.filter_by(
                partner_id=partner_id,
                league_id=league_id,
                org_season_id=org_season_id
            ).first()

            if rate_record and rate_record.has_override:
                return rate_record.effective_rate_ntl if is_ntl else rate_record.effective_rate_normal

        # Try all-season rate
        rate_record = cls.query.filter_by(
            partner_id=partner_id,
            league_id=league_id,
            org_season_id=None
        ).first()

        if rate_record and rate_record.has_override:
            return rate_record.effective_rate_ntl if is_ntl else rate_record.effective_rate_normal

        # Fall back to partner default
        partner = UmpirePartner.query.get(partner_id)
        if partner:
            if is_ntl and partner.rate_ntl:
                return Decimal(str(partner.rate_ntl))
            if partner.rate_normal:
                return Decimal(str(partner.rate_normal))

        return None

    @classmethod
    def get_or_create(cls, partner_id, league_id, org_season_id=None):
        """Get existing rate record or create a new one.

        Args:
            partner_id: UmpirePartner ID
            league_id: League ID
            org_season_id: Optional season context

        Returns:
            Tuple of (PartnerLeagueRate, created_bool)
        """
        existing = cls.query.filter_by(
            partner_id=partner_id,
            league_id=league_id,
            org_season_id=org_season_id
        ).first()

        if existing:
            return existing, False

        new_rate = cls(
            partner_id=partner_id,
            league_id=league_id,
            org_season_id=org_season_id
        )
        return new_rate, True

    @classmethod
    def get_summary_for_partner(cls, partner_id):
        """Get a summary of all league rate overrides for a partner.

        Returns:
            Dict mapping league_id -> {
                'league_name': str,
                'rate_normal': Decimal or None,
                'rate_ntl': Decimal or None,
                'is_override': bool
            }
        """
        from app.models.league import League

        # Get all leagues
        leagues = League.get_all_active()

        # Get all rate records for this partner
        rates = cls.query.filter_by(partner_id=partner_id, org_season_id=None).all()
        rate_by_league = {r.league_id: r for r in rates}

        summary = {}
        for league in leagues:
            rate_record = rate_by_league.get(league.ID)
            summary[league.ID] = {
                'league_name': league.display_name,
                'rate_normal': rate_record.rate_normal if rate_record else None,
                'rate_ntl': rate_record.rate_ntl if rate_record else None,
                'is_override': rate_record is not None and rate_record.has_override
            }

        return summary
