"""UmpirePayment model - payment records for umpire work."""

from datetime import datetime
from app.extensions import db


class UmpirePayment(db.Model):
    """Payment record for umpire work.

    Tracks payments to SDLL umpires for games worked.
    Partners (Diamond, Dynamic) are paid separately through their own systems.
    """
    __tablename__ = 'sdll_umpire_payments'

    id = db.Column(db.Integer, primary_key=True)
    umpire_profile_id = db.Column(db.Integer,
                                   db.ForeignKey('sdll_umpire_profiles.id', ondelete='CASCADE'),
                                   nullable=False)

    # Pay period
    pay_period_start = db.Column(db.Date, nullable=False)
    pay_period_end = db.Column(db.Date, nullable=False)

    # Amounts
    games_count = db.Column(db.SmallInteger, default=0)
    base_amount = db.Column(db.Numeric(8, 2), default=0)
    bonus_amount = db.Column(db.Numeric(8, 2), default=0)
    total_amount = db.Column(db.Numeric(8, 2), default=0)

    # Status
    status = db.Column(db.String(20), default='pending')  # pending, paid, void

    # Payment details
    paid_at = db.Column(db.DateTime)
    paid_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))
    payment_method = db.Column(db.String(50))  # check, venmo, cash
    payment_reference = db.Column(db.String(100))  # check number, transaction ID

    # Tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    # Relationships
    umpire = db.relationship('UmpireProfile', backref='payments')
    payer = db.relationship('User', foreign_keys=[paid_by])

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_VOID = 'void'
    STATUSES = [STATUS_PENDING, STATUS_PAID, STATUS_VOID]

    # Payment method constants
    METHOD_CHECK = 'check'
    METHOD_VENMO = 'venmo'
    METHOD_CASH = 'cash'
    METHOD_ZELLE = 'zelle'
    PAYMENT_METHODS = [METHOD_CHECK, METHOD_VENMO, METHOD_CASH, METHOD_ZELLE]

    def __repr__(self):
        return f'<UmpirePayment {self.id}: {self.total_amount} ({self.status})>'

    @property
    def is_paid(self):
        """Check if payment has been made."""
        return self.status == self.STATUS_PAID

    @property
    def is_pending(self):
        """Check if payment is pending."""
        return self.status == self.STATUS_PENDING

    @property
    def period_display(self):
        """Human-readable pay period."""
        return f"{self.pay_period_start.strftime('%m/%d')} - {self.pay_period_end.strftime('%m/%d/%Y')}"

    def mark_paid(self, user_id, method, reference=None):
        """Mark payment as paid.

        Args:
            user_id: ID of user processing the payment
            method: Payment method ('check', 'venmo', 'cash', 'zelle')
            reference: Payment reference (check number, transaction ID)
        """
        self.status = self.STATUS_PAID
        self.paid_at = datetime.utcnow()
        self.paid_by = user_id
        self.payment_method = method
        self.payment_reference = reference

    def void(self, reason=None):
        """Void the payment.

        Args:
            reason: Optional reason for voiding
        """
        self.status = self.STATUS_VOID
        if reason:
            self.notes = f"Voided: {reason}" + (f"\n{self.notes}" if self.notes else "")

    def calculate_from_assignments(self, assignments):
        """Calculate payment amounts from game assignments.

        Args:
            assignments: List of GameUmpire assignments in the pay period
        """
        self.games_count = len(assignments)
        self.base_amount = sum(
            float(a.base_pay or 0) for a in assignments
        )
        self.bonus_amount = sum(
            float(a.base_pay or 0) * (float(a.bonus_multiplier or 1) - 1)
            for a in assignments
        )
        self.total_amount = self.base_amount + self.bonus_amount

    @classmethod
    def get_for_umpire(cls, umpire_profile_id, status=None):
        """Get payments for an umpire.

        Args:
            umpire_profile_id: ID of the umpire profile
            status: Optional status filter

        Returns:
            List of UmpirePayment objects
        """
        query = cls.query.filter_by(umpire_profile_id=umpire_profile_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(cls.pay_period_end.desc()).all()

    @classmethod
    def get_pending(cls, org_id=None):
        """Get all pending payments.

        Args:
            org_id: Optional organization filter (not implemented yet)

        Returns:
            List of pending UmpirePayment objects
        """
        return cls.query.filter_by(status=cls.STATUS_PENDING).all()

    @classmethod
    def get_for_period(cls, start_date, end_date):
        """Get all payments within a date range.

        Args:
            start_date: Period start date
            end_date: Period end date

        Returns:
            List of UmpirePayment objects
        """
        return cls.query.filter(
            cls.pay_period_start >= start_date,
            cls.pay_period_end <= end_date
        ).all()
