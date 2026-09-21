"""Partner payment and credit tracking models.

These models track:
- Payments made to umpire partners for umpire services
- Credits from postponed games or adjustments
"""

from datetime import datetime
from decimal import Decimal
from app.extensions import db


class PartnerPaymentRecord(db.Model):
    """Track payments made to umpire partners for a season or date range.

    For partners where we prepay invoices (prepays_invoices=True), this tracks
    what we've paid vs. what we've used, generating credits when games are postponed.
    """
    __tablename__ = 'sdll_partner_payment_records'

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'), nullable=False)

    # Season context (optional - can be per-invoice instead)
    year = db.Column(db.Integer)
    is_spring = db.Column(db.Boolean)

    # Invoice details
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    invoice_amount = db.Column(db.Numeric(8, 2))

    # What we calculated we owed
    calculated_games = db.Column(db.Integer)
    calculated_amount = db.Column(db.Numeric(8, 2))

    # Payment details
    paid_amount = db.Column(db.Numeric(8, 2))
    payment_date = db.Column(db.Date)
    payment_method = db.Column(db.String(30))
    payment_reference = db.Column(db.String(100))

    # Credit tracking
    credit_applied = db.Column(db.Numeric(8, 2), default=0)
    credit_generated = db.Column(db.Numeric(8, 2), default=0)

    # Status: pending, paid, disputed, void
    status = db.Column(db.String(20), default='pending')

    # Notes
    notes = db.Column(db.Text)

    # Audit
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    paid_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    partner = db.relationship('UmpirePartner', backref='payment_records')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    paid_by = db.relationship('User', foreign_keys=[paid_by_user_id])
    credits_applied = db.relationship('PartnerCredit',
                                      foreign_keys='PartnerCredit.applied_to_payment_id',
                                      backref='applied_to_payment')
    credits_generated = db.relationship('PartnerCredit',
                                        foreign_keys='PartnerCredit.source_payment_id',
                                        backref='source_payment')

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_DISPUTED = 'disputed'
    STATUS_VOID = 'void'

    PAYMENT_METHODS = ['check', 'ach', 'venmo', 'zelle', 'cash', 'other']

    def __repr__(self):
        return f'<PartnerPaymentRecord {self.id}: {self.partner.short_code if self.partner else "?"} ${self.paid_amount or 0}>'

    @property
    def season_name(self):
        """Get formatted season name."""
        if self.year and self.is_spring is not None:
            return f'{"Spring" if self.is_spring else "Fall"} {self.year}'
        return None

    @property
    def is_paid(self):
        """Check if payment has been made."""
        return self.status == self.STATUS_PAID

    @property
    def is_void(self):
        """Check if payment record is voided."""
        return self.status == self.STATUS_VOID

    @property
    def net_amount(self):
        """Calculate net amount after credits applied."""
        paid = self.paid_amount or Decimal('0')
        credit = self.credit_applied or Decimal('0')
        return paid - credit

    @classmethod
    def get_for_partner(cls, partner_id, year=None, is_spring=None, status=None):
        """Get payment records for a partner.

        Args:
            partner_id: Partner ID
            year: Optional year filter
            is_spring: Optional season filter
            status: Optional status filter

        Returns:
            List of PartnerPaymentRecord
        """
        query = cls.query.filter_by(partner_id=partner_id)
        if year is not None:
            query = query.filter_by(year=year)
        if is_spring is not None:
            query = query.filter_by(is_spring=is_spring)
        if status is not None:
            query = query.filter_by(status=status)
        return query.order_by(cls.invoice_date.desc()).all()

    @classmethod
    def get_season_totals(cls, partner_id, year, is_spring):
        """Get payment totals for a partner's season.

        Returns:
            Dict with total_paid, total_credits_applied, total_games, total_credits_generated
        """
        records = cls.query.filter_by(
            partner_id=partner_id,
            year=year,
            is_spring=is_spring
        ).filter(cls.status != cls.STATUS_VOID).all()

        return {
            'total_paid': sum((r.paid_amount or 0) for r in records),
            'total_credits_applied': sum((r.credit_applied or 0) for r in records),
            'total_games': sum((r.calculated_games or 0) for r in records),
            'total_credits_generated': sum((r.credit_generated or 0) for r in records),
            'record_count': len(records)
        }


class PartnerCredit(db.Model):
    """Track credits owed to/from partners across seasons.

    Credits are generated when:
    - A game is postponed after prepayment (source_type='postponed_game')
    - A partner fails to fulfill an assignment (source_type='unfulfilled')
    - We overpay on an invoice (source_type='overpayment')
    - Manual adjustment needed (source_type='adjustment')
    """
    __tablename__ = 'sdll_partner_credits'

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'), nullable=False)

    # Source of credit
    source_type = db.Column(db.String(30), nullable=False)
    source_game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID'))
    source_payment_id = db.Column(db.Integer, db.ForeignKey('sdll_partner_payment_records.id'))

    # Credit details
    amount = db.Column(db.Numeric(8, 2), nullable=False)
    umpire_games = db.Column(db.Integer)

    # Season context
    season_year = db.Column(db.Integer)
    season_is_spring = db.Column(db.Boolean)

    # Status: available, applied, expired, void
    status = db.Column(db.String(20), default='available')
    applied_to_payment_id = db.Column(db.Integer, db.ForeignKey('sdll_partner_payment_records.id'))

    # Notes and audit
    description = db.Column(db.String(255))
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    partner = db.relationship('UmpirePartner', backref='credits')
    source_game = db.relationship('Game')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    # Source type constants
    SOURCE_POSTPONED_GAME = 'postponed_game'
    SOURCE_UNFULFILLED = 'unfulfilled'
    SOURCE_OVERPAYMENT = 'overpayment'
    SOURCE_ADJUSTMENT = 'adjustment'

    SOURCE_TYPES = [SOURCE_POSTPONED_GAME, SOURCE_UNFULFILLED, SOURCE_OVERPAYMENT, SOURCE_ADJUSTMENT]
    SOURCE_TYPE_LABELS = {
        SOURCE_POSTPONED_GAME: 'Postponed Game',
        SOURCE_UNFULFILLED: 'Unfulfilled Assignment',
        SOURCE_OVERPAYMENT: 'Overpayment',
        SOURCE_ADJUSTMENT: 'Manual Adjustment'
    }

    # Status constants
    STATUS_AVAILABLE = 'available'
    STATUS_APPLIED = 'applied'
    STATUS_EXPIRED = 'expired'
    STATUS_VOID = 'void'

    def __repr__(self):
        return f'<PartnerCredit {self.id}: {self.partner.short_code if self.partner else "?"} ${self.amount} ({self.status})>'

    @property
    def source_type_label(self):
        """Get human-readable label for source type."""
        return self.SOURCE_TYPE_LABELS.get(self.source_type, self.source_type)

    @property
    def season_name(self):
        """Get formatted season name."""
        if self.season_year and self.season_is_spring is not None:
            return f'{"Spring" if self.season_is_spring else "Fall"} {self.season_year}'
        return None

    @property
    def is_available(self):
        """Check if credit is available to apply."""
        return self.status == self.STATUS_AVAILABLE

    @property
    def is_void(self):
        """Check if credit has been voided."""
        return self.status == self.STATUS_VOID

    def apply_to_payment(self, payment_record):
        """Apply this credit to a payment record.

        Args:
            payment_record: PartnerPaymentRecord to apply credit to
        """
        if not self.is_available:
            raise ValueError(f'Credit {self.id} is not available (status={self.status})')

        self.status = self.STATUS_APPLIED
        self.applied_to_payment_id = payment_record.id

        # Update payment record's credit_applied
        payment_record.credit_applied = (payment_record.credit_applied or Decimal('0')) + self.amount

    def void(self, reason=None):
        """Void this credit.

        Args:
            reason: Optional reason to append to description
        """
        self.status = self.STATUS_VOID
        if reason:
            self.description = f'{self.description or ""} [VOIDED: {reason}]'.strip()

    @classmethod
    def get_available_for_partner(cls, partner_id):
        """Get all available credits for a partner.

        Args:
            partner_id: Partner ID

        Returns:
            List of available PartnerCredit records
        """
        return cls.query.filter_by(
            partner_id=partner_id,
            status=cls.STATUS_AVAILABLE
        ).order_by(cls.created_at).all()

    @classmethod
    def get_total_available(cls, partner_id):
        """Get total available credit amount for a partner.

        Args:
            partner_id: Partner ID

        Returns:
            Decimal total
        """
        result = db.session.query(
            db.func.sum(cls.amount)
        ).filter_by(
            partner_id=partner_id,
            status=cls.STATUS_AVAILABLE
        ).scalar()
        return result or Decimal('0')

    @classmethod
    def create_from_postponed_game(cls, game, partner, rate, umpire_count, user_id=None):
        """Create a credit from a postponed game.

        Args:
            game: The postponed Game object
            partner: The UmpirePartner
            rate: Per-umpire rate
            umpire_count: Number of umpires assigned
            user_id: User creating the credit (optional)

        Returns:
            New PartnerCredit instance (not yet committed)
        """
        amount = Decimal(str(rate)) * umpire_count

        credit = cls(
            partner_id=partner.id,
            source_type=cls.SOURCE_POSTPONED_GAME,
            source_game_id=game.ID,
            amount=amount,
            umpire_games=umpire_count,
            season_year=game.year,
            season_is_spring=game.is_spring,
            description=f'Postponed: {game.league} - {game.game_date.strftime("%m/%d/%Y")}',
            created_by_user_id=user_id
        )
        return credit

    @classmethod
    def get_for_season(cls, partner_id, year, is_spring, status=None):
        """Get credits for a partner's season.

        Args:
            partner_id: Partner ID
            year: Season year
            is_spring: Season type
            status: Optional status filter

        Returns:
            List of PartnerCredit records
        """
        query = cls.query.filter_by(
            partner_id=partner_id,
            season_year=year,
            season_is_spring=is_spring
        )
        if status is not None:
            query = query.filter_by(status=status)
        return query.order_by(cls.created_at.desc()).all()
