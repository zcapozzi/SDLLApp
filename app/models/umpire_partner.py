"""UmpirePartner model - external umpire service providers (Dynamic, Diamond, etc.)."""

from datetime import datetime
import secrets
from app.extensions import db


class UmpirePartner(db.Model):
    """External umpire service provider.

    Partners like Dynamic and Diamond provide umpires for games.
    We track assignments at the organization level, not individual umpires.
    """
    __tablename__ = 'sdll_umpire_partners'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # Partner identification
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(20))  # "DIA", "DYN" for quick reference

    # Notification preferences
    notification_preference = db.Column(db.String(20), default='weekly')
    # Options: 'daily', 'weekly', 'per_game'

    # Status
    active = db.Column(db.Boolean, default=True)

    # Per-game rates
    # If is_flat_rate=False: rate is per umpire (e.g., Diamond $85/umpire)
    # If is_flat_rate=True: rate is flat per game (e.g., Dynamic $100/game)
    rate_normal = db.Column(db.Numeric(8, 2))  # Rate for normal games
    rate_ntl = db.Column(db.Numeric(8, 2))     # Rate for no-time-limit games
    is_flat_rate = db.Column(db.Boolean, default=False)  # True = rate is per game, False = rate is per umpire

    # Booking fees (in addition to umpire rates)
    booking_fee_per_game = db.Column(db.Numeric(8, 2), default=0)  # Per-game fee (e.g., Diamond $18/game)
    booking_fee_per_season = db.Column(db.Numeric(8, 2), default=0)  # Per-season fee (e.g., Dynamic $1000/season)

    # Schedule token for public schedule URL
    schedule_token = db.Column(db.String(32), unique=True, nullable=True, index=True)

    # Weekly digest settings
    auto_send_digest = db.Column(db.Boolean, default=False)  # Auto-send weekly digests without review

    # Whether this org manages the umpires directly (SDL Academy = 1, external partners = 0)
    # If 1, individual umpire digests are generated instead of a single partner digest
    is_managed_by_org = db.Column(db.Boolean, default=False)

    # Whether we prepay invoices for this partner (requires credit tracking)
    # If True, postponed games generate credits to be applied to future payments
    prepays_invoices = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    organization = db.relationship('Organization', backref='umpire_partners')
    game_assignments = db.relationship('GameUmpire', back_populates='partner',
                                       foreign_keys='GameUmpire.partner_id')
    contacts = db.relationship('PartnerContact', back_populates='partner',
                               cascade='all, delete-orphan', lazy='dynamic')

    # Notification preference constants
    NOTIFY_DAILY = 'daily'
    NOTIFY_WEEKLY = 'weekly'
    NOTIFY_PER_GAME = 'per_game'
    NOTIFICATION_PREFERENCES = [NOTIFY_DAILY, NOTIFY_WEEKLY, NOTIFY_PER_GAME]

    def __repr__(self):
        return f'<UmpirePartner {self.name} ({self.short_code})>'

    @property
    def is_active(self):
        """Check if partner is active."""
        return self.active

    @property
    def code(self):
        """Alias for short_code."""
        return self.short_code

    def get_upcoming_games(self, days=7):
        """Get games assigned to this partner in the next N days.

        Args:
            days: Number of days to look ahead.

        Returns:
            List of GameUmpire assignments.
        """
        from datetime import timedelta
        from app.models.game import Game

        cutoff = datetime.utcnow() + timedelta(days=days)
        return [
            assignment for assignment in self.game_assignments
            if assignment.game.game_date and
               assignment.game.game_date <= cutoff and
               assignment.status != 'cancelled'
        ]

    @classmethod
    def get_active(cls, org_id=1):
        """Get all active partners for an organization."""
        return cls.query.filter_by(org_id=org_id, active=True).all()

    @classmethod
    def get_by_code(cls, short_code, org_id=1):
        """Get partner by short code.

        Args:
            short_code: Partner's short code (e.g., 'DIA', 'DYN')
            org_id: Organization ID (default 1 for SDLL)

        Returns:
            UmpirePartner or None
        """
        return cls.query.filter_by(
            short_code=short_code.upper(),
            org_id=org_id,
            active=True
        ).first()

    @classmethod
    def get_by_name(cls, name, org_id=1):
        """Get partner by name."""
        return cls.query.filter_by(
            name=name,
            org_id=org_id,
            active=True
        ).first()

    def generate_schedule_token(self):
        """Generate a unique schedule token for public URL access."""
        self.schedule_token = secrets.token_urlsafe(16)
        return self.schedule_token

    @classmethod
    def get_by_schedule_token(cls, token):
        """Get partner by schedule token.

        Args:
            token: The schedule token from the URL

        Returns:
            UmpirePartner or None
        """
        if not token:
            return None
        return cls.query.filter_by(
            schedule_token=token,
            active=True
        ).first()

    def get_contacts_for_message_type(self, msg_type):
        """Get contacts that receive a specific message type.

        Args:
            msg_type: Message type (e.g., 'weeklyDigest', 'recentChanges')

        Returns:
            List of PartnerContact objects
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_for_message_type(self.id, msg_type)

    def get_emails_for_message_type(self, msg_type):
        """Get email addresses for contacts that receive a message type.

        Args:
            msg_type: Message type

        Returns:
            List of email addresses
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_emails_for_message_type(self.id, msg_type)

    def get_active_contacts(self):
        """Get all active contacts for this partner.

        Returns:
            List of PartnerContact objects
        """
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_for_partner(self.id)

    @property
    def primary_contact(self):
        """Get the primary contact for display purposes."""
        from app.models.partner_contact import PartnerContact
        return PartnerContact.get_primary_contact(self.id)

    def calculate_game_cost(self, umpire_count, is_ntl=False):
        """Calculate total cost for a single game.

        Args:
            umpire_count: Number of umpires assigned to the game
            is_ntl: True if this is a no-time-limit game

        Returns:
            Decimal total cost for the game

        Examples:
            Diamond (per-umpire): 2 umpires * $85 + $18 booking = $188
            Dynamic (flat rate): $100 flat + $0 booking = $100
        """
        from decimal import Decimal

        # Get the appropriate rate
        if is_ntl and self.rate_ntl:
            base_rate = Decimal(str(self.rate_ntl))
        else:
            base_rate = Decimal(str(self.rate_normal or 0))

        # Calculate umpire cost
        if self.is_flat_rate:
            # Flat rate per game regardless of umpire count
            umpire_cost = base_rate
        else:
            # Per-umpire rate
            umpire_cost = base_rate * umpire_count

        # Add per-game booking fee
        booking_fee = Decimal(str(self.booking_fee_per_game or 0))

        return umpire_cost + booking_fee

    def get_rate_description(self):
        """Get a human-readable description of the rate structure.

        Returns:
            String like "$85/umpire + $18/game" or "$100/game flat"
        """
        parts = []

        if self.rate_normal:
            if self.is_flat_rate:
                parts.append(f"${self.rate_normal}/game flat")
            else:
                parts.append(f"${self.rate_normal}/umpire")

        if self.booking_fee_per_game and self.booking_fee_per_game > 0:
            parts.append(f"${self.booking_fee_per_game}/game booking")

        if self.booking_fee_per_season and self.booking_fee_per_season > 0:
            parts.append(f"${self.booking_fee_per_season}/season")

        return " + ".join(parts) if parts else "No rates set"

    def get_rate_for_league(self, league_id, is_ntl=False, org_season_id=None):
        """Get rate for specific league, falling back to partner default.

        Lookup hierarchy:
        1. PartnerLeagueRate (partner + league + season) - most specific
        2. PartnerLeagueRate (partner + league + NULL) - all seasons
        3. UmpirePartner.rate_ntl / rate_normal - partner default

        Args:
            league_id: League ID to get rate for
            is_ntl: True for no-time-limit games
            org_season_id: Optional season context for season-specific rates

        Returns:
            Decimal rate amount
        """
        from decimal import Decimal
        from app.models.partner_league_rate import PartnerLeagueRate

        # Use PartnerLeagueRate's lookup which handles the hierarchy
        league_rate = PartnerLeagueRate.get_rate(
            partner_id=self.id,
            league_id=league_id,
            is_ntl=is_ntl,
            org_season_id=org_season_id
        )

        if league_rate is not None:
            return league_rate

        # Fall back to partner default
        if is_ntl and self.rate_ntl:
            return Decimal(str(self.rate_ntl))
        if self.rate_normal:
            return Decimal(str(self.rate_normal))

        return Decimal('0')

    def calculate_game_cost_for_league(self, league_id, umpire_count, is_ntl=False, org_season_id=None):
        """Calculate total cost for a game in a specific league.

        Uses league-specific rate if available, then applies flat_rate logic
        and adds booking fee.

        Args:
            league_id: League ID for the game
            umpire_count: Number of umpires assigned
            is_ntl: True for no-time-limit games
            org_season_id: Optional season context

        Returns:
            Decimal total cost for the game

        Examples:
            Diamond (per-umpire, $85 default, $75 for AA): 2 umpires AA = $150 + $18 = $168
            Dynamic (flat rate, $100): 2 umpires Majors = $100 + $0 = $100
        """
        from decimal import Decimal

        # Get the league-specific rate
        base_rate = self.get_rate_for_league(league_id, is_ntl, org_season_id)

        # Calculate umpire cost
        if self.is_flat_rate:
            # Flat rate per game regardless of umpire count
            umpire_cost = base_rate
        else:
            # Per-umpire rate
            umpire_cost = base_rate * umpire_count

        # Add per-game booking fee
        booking_fee = Decimal(str(self.booking_fee_per_game or 0))

        return umpire_cost + booking_fee

    def get_league_rates_summary(self, org_season_id=None):
        """Get a summary of all league-specific rates for this partner.

        Args:
            org_season_id: Optional season filter

        Returns:
            List of dicts with league info and rates
        """
        from app.models.league import League
        from app.models.partner_league_rate import PartnerLeagueRate

        leagues = League.get_all_active()
        rates = PartnerLeagueRate.get_for_partner(self.id, org_season_id)
        rate_by_league = {r.league_id: r for r in rates}

        summary = []
        for league in leagues:
            rate_record = rate_by_league.get(league.ID)
            summary.append({
                'league_id': league.ID,
                'league_name': league.display_name,
                'rate_normal': rate_record.rate_normal if rate_record else None,
                'rate_ntl': rate_record.rate_ntl if rate_record else None,
                'has_override': rate_record is not None and rate_record.has_override,
                'effective_rate_normal': self.get_rate_for_league(league.ID, False, org_season_id),
                'effective_rate_ntl': self.get_rate_for_league(league.ID, True, org_season_id),
            })

        return summary
