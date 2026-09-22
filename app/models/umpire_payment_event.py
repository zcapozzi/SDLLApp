"""UmpirePaymentEvent model - standalone payment events decoupled from game lifecycle.

These events track payment obligations that persist regardless of what happens to the
underlying game. This is critical for scenarios like:

1. Umpire arrives for a rainout - game may be rescheduled, but umpire still needs payment
2. Game postponed after umpire shows up - original payment obligation persists
3. Bonus payments for training, meetings, etc.
4. Adjustments for disputes or corrections

The key insight is that games can be rescheduled (new date, new field, possibly new game_id),
but the payment obligation from the original game should persist independently.
"""

from datetime import datetime
from decimal import Decimal
from app.extensions import db


class UmpirePaymentEvent(db.Model):
    """Standalone payment event, decoupled from game lifecycle.

    This model captures payment obligations that exist independently of game records.
    When an umpire shows up for a rained-out game, we create a payment event that
    persists even if the game is rescheduled or deleted.
    """
    __tablename__ = 'sdll_umpire_payment_events'

    id = db.Column(db.Integer, primary_key=True)

    # Event type
    event_type = db.Column(db.String(30), nullable=False)

    # Original game snapshot (NOT a FK - game may be rescheduled/deleted)
    # We store the snapshot because the original game_id may be reused or deleted
    original_game_id = db.Column(db.BigInteger, index=True)
    original_assignr_id = db.Column(db.String(15))
    original_date = db.Column(db.Date, nullable=False)
    original_time = db.Column(db.Time)
    original_field_id = db.Column(db.BigInteger)
    original_field_name = db.Column(db.String(100))
    original_league = db.Column(db.String(30))
    original_home_team = db.Column(db.String(100))
    original_away_team = db.Column(db.String(100))

    # Who gets paid (mutually exclusive - one or the other)
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id'))
    partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'))

    # Assignment details
    umpire_count = db.Column(db.SmallInteger, default=1)
    position = db.Column(db.String(20))  # 'plate', 'base', 'umpire'

    # Payment calculation
    rate_applied = db.Column(db.Numeric(8, 2))  # Per-umpire or flat rate used
    booking_fee_applied = db.Column(db.Numeric(8, 2), default=0)  # For partners
    amount = db.Column(db.Numeric(8, 2), nullable=False)
    umpire_showed_up = db.Column(db.Boolean, default=True)

    # Status workflow: pending -> approved -> paid (or voided at any point)
    status = db.Column(db.String(20), default='pending')
    reason = db.Column(db.String(255))  # Brief reason for the event
    notes = db.Column(db.Text)  # Extended notes/discussion

    # Season context
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'))

    # Audit trail
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    approved_at = db.Column(db.DateTime)
    approved_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    paid_at = db.Column(db.DateTime)
    paid_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    voided_at = db.Column(db.DateTime)
    voided_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Relationships
    umpire_profile = db.relationship('UmpireProfile', backref='payment_events')
    partner = db.relationship('UmpirePartner', backref='payment_events')
    org_season = db.relationship('OrgSeason', backref='umpire_payment_events')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id])
    paid_by = db.relationship('User', foreign_keys=[paid_by_user_id])
    voided_by = db.relationship('User', foreign_keys=[voided_by_user_id])

    # Event type constants
    TYPE_RAINOUT_ARRIVAL = 'rainout_arrival'  # Umpire showed up for rained-out game
    TYPE_CANCELLED_ARRIVAL = 'cancelled_arrival'  # Umpire showed up for cancelled game
    TYPE_COMPLETED = 'completed'  # Normal game completion
    TYPE_BONUS = 'bonus'  # Training, meetings, special assignments
    TYPE_ADJUSTMENT = 'adjustment'  # Corrections, disputes

    EVENT_TYPES = [
        TYPE_RAINOUT_ARRIVAL,
        TYPE_CANCELLED_ARRIVAL,
        TYPE_COMPLETED,
        TYPE_BONUS,
        TYPE_ADJUSTMENT,
    ]

    EVENT_TYPE_LABELS = {
        TYPE_RAINOUT_ARRIVAL: 'Rainout Arrival',
        TYPE_CANCELLED_ARRIVAL: 'Cancelled Arrival',
        TYPE_COMPLETED: 'Completed Game',
        TYPE_BONUS: 'Bonus',
        TYPE_ADJUSTMENT: 'Adjustment',
    }

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PAID = 'paid'
    STATUS_VOIDED = 'voided'

    STATUSES = [STATUS_PENDING, STATUS_APPROVED, STATUS_PAID, STATUS_VOIDED]

    STATUS_LABELS = {
        STATUS_PENDING: 'Pending',
        STATUS_APPROVED: 'Approved',
        STATUS_PAID: 'Paid',
        STATUS_VOIDED: 'Voided',
    }

    def __repr__(self):
        payee = self.umpire_display_name or self.partner_display_name or 'Unknown'
        return f'<UmpirePaymentEvent {self.id}: {self.event_type_label} ${self.amount} -> {payee}>'

    @property
    def event_type_label(self):
        """Get human-readable event type label."""
        return self.EVENT_TYPE_LABELS.get(self.event_type, self.event_type)

    @property
    def status_label(self):
        """Get human-readable status label."""
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def is_pending(self):
        """Check if event is pending approval."""
        return self.status == self.STATUS_PENDING

    @property
    def is_approved(self):
        """Check if event is approved but not yet paid."""
        return self.status == self.STATUS_APPROVED

    @property
    def is_paid(self):
        """Check if event has been paid."""
        return self.status == self.STATUS_PAID

    @property
    def is_voided(self):
        """Check if event has been voided."""
        return self.status == self.STATUS_VOIDED

    @property
    def is_active(self):
        """Check if event is still active (not voided)."""
        return self.status != self.STATUS_VOIDED

    @property
    def payee_type(self):
        """Get the type of payee: 'umpire', 'partner', or None."""
        if self.umpire_profile_id:
            return 'umpire'
        if self.partner_id:
            return 'partner'
        return None

    @property
    def umpire_display_name(self):
        """Get umpire display name if this is an umpire payment."""
        if self.umpire_profile:
            return self.umpire_profile.display_name
        return None

    @property
    def partner_display_name(self):
        """Get partner display name if this is a partner payment."""
        if self.partner:
            return self.partner.name
        return None

    @property
    def payee_display(self):
        """Get display name for whoever gets paid."""
        return self.umpire_display_name or self.partner_display_name or 'Unknown'

    @property
    def game_display(self):
        """Get a display string for the original game."""
        parts = []
        if self.original_date:
            parts.append(self.original_date.strftime('%m/%d/%Y'))
        if self.original_time:
            parts.append(self.original_time.strftime('%I:%M %p').lstrip('0'))
        if self.original_league:
            parts.append(self.original_league)
        if self.original_field_name:
            parts.append(f'@ {self.original_field_name}')
        return ' '.join(parts) if parts else f'Game #{self.original_game_id}'

    @property
    def season_display(self):
        """Get formatted season name."""
        if self.org_season:
            return self.org_season.display_name
        return None

    def approve(self, user_id):
        """Approve this payment event.

        Args:
            user_id: ID of user approving
        """
        if self.status != self.STATUS_PENDING:
            raise ValueError(f'Cannot approve event in status {self.status}')

        self.status = self.STATUS_APPROVED
        self.approved_at = datetime.utcnow()
        self.approved_by_user_id = user_id

    def mark_paid(self, user_id):
        """Mark this payment event as paid.

        Args:
            user_id: ID of user marking as paid
        """
        if self.status not in [self.STATUS_PENDING, self.STATUS_APPROVED]:
            raise ValueError(f'Cannot mark as paid event in status {self.status}')

        self.status = self.STATUS_PAID
        self.paid_at = datetime.utcnow()
        self.paid_by_user_id = user_id
        # Also set approved if not already
        if not self.approved_at:
            self.approved_at = datetime.utcnow()
            self.approved_by_user_id = user_id

    def void(self, user_id, reason=None):
        """Void this payment event.

        Args:
            user_id: ID of user voiding
            reason: Optional reason to add to notes
        """
        if self.status == self.STATUS_VOIDED:
            return  # Already voided

        self.status = self.STATUS_VOIDED
        self.voided_at = datetime.utcnow()
        self.voided_by_user_id = user_id
        if reason:
            self.notes = f'{self.notes or ""}\n[VOIDED: {reason}]'.strip()

    @classmethod
    def create_from_rainout(cls, game, payee, rate, umpire_count=1, position=None,
                            user_id=None, org_season_id=None, booking_fee=None):
        """Create a payment event for a rained-out game where umpire arrived.

        Args:
            game: The Game object being rained out
            payee: Either UmpireProfile or UmpirePartner that needs payment
            rate: Per-umpire rate (Decimal)
            umpire_count: Number of umpires (for partners with flat rate, this is 1)
            position: Position ('plate', 'base', 'umpire')
            user_id: User creating this event
            org_season_id: OrgSeason ID
            booking_fee: Per-game booking fee (for partners)

        Returns:
            New UmpirePaymentEvent instance (not yet committed)
        """
        from app.models.umpire_profile import UmpireProfile
        from app.models.umpire_partner import UmpirePartner

        # Calculate amount
        rate_decimal = Decimal(str(rate)) if rate else Decimal('0')
        booking_decimal = Decimal(str(booking_fee)) if booking_fee else Decimal('0')

        # Check if payee is partner with flat rate
        is_flat_rate = False
        if isinstance(payee, UmpirePartner) and payee.is_flat_rate:
            is_flat_rate = True
            amount = rate_decimal + booking_decimal
        else:
            amount = (rate_decimal * umpire_count) + booking_decimal

        event = cls(
            event_type=cls.TYPE_RAINOUT_ARRIVAL,
            original_game_id=game.ID,
            original_assignr_id=game.assignr_id,
            original_date=game.game_date,
            original_time=game.game_time,
            original_field_id=game.field_id,
            original_field_name=game.field_rel.location_title if game.field_rel else None,
            original_league=game.league,
            original_home_team=game.home_team,
            original_away_team=game.away_team,
            umpire_count=umpire_count,
            position=position,
            rate_applied=rate_decimal,
            booking_fee_applied=booking_decimal,
            amount=amount,
            umpire_showed_up=True,
            reason=f'Rainout arrival: {game.league} on {game.game_date.strftime("%m/%d/%Y")}',
            org_season_id=org_season_id,
            created_by_user_id=user_id,
        )

        # Set the payee
        if isinstance(payee, UmpireProfile):
            event.umpire_profile_id = payee.id
        elif isinstance(payee, UmpirePartner):
            event.partner_id = payee.id

        return event

    @classmethod
    def get_pending(cls, org_season_id=None, partner_id=None, umpire_profile_id=None):
        """Get pending payment events.

        Args:
            org_season_id: Optional season filter
            partner_id: Optional partner filter
            umpire_profile_id: Optional umpire filter

        Returns:
            List of pending UmpirePaymentEvent records
        """
        query = cls.query.filter_by(status=cls.STATUS_PENDING)

        if org_season_id is not None:
            query = query.filter_by(org_season_id=org_season_id)
        if partner_id is not None:
            query = query.filter_by(partner_id=partner_id)
        if umpire_profile_id is not None:
            query = query.filter_by(umpire_profile_id=umpire_profile_id)

        return query.order_by(cls.original_date.desc()).all()

    @classmethod
    def get_for_season(cls, org_season_id, status=None, payee_type=None):
        """Get payment events for a season.

        Args:
            org_season_id: OrgSeason ID
            status: Optional status filter
            payee_type: Optional 'umpire' or 'partner' filter

        Returns:
            List of UmpirePaymentEvent records
        """
        query = cls.query.filter_by(org_season_id=org_season_id)

        if status is not None:
            query = query.filter_by(status=status)

        if payee_type == 'umpire':
            query = query.filter(cls.umpire_profile_id.isnot(None))
        elif payee_type == 'partner':
            query = query.filter(cls.partner_id.isnot(None))

        return query.order_by(cls.original_date.desc()).all()

    @classmethod
    def get_totals_for_umpire(cls, umpire_profile_id, org_season_id=None, status=None):
        """Get payment totals for an umpire.

        Args:
            umpire_profile_id: UmpireProfile ID
            org_season_id: Optional season filter
            status: Optional status filter (default: all active)

        Returns:
            Dict with total_amount, event_count
        """
        query = cls.query.filter_by(umpire_profile_id=umpire_profile_id)

        if org_season_id is not None:
            query = query.filter_by(org_season_id=org_season_id)

        if status is not None:
            query = query.filter_by(status=status)
        else:
            query = query.filter(cls.status != cls.STATUS_VOIDED)

        events = query.all()

        return {
            'total_amount': sum(e.amount for e in events),
            'pending_amount': sum(e.amount for e in events if e.is_pending),
            'approved_amount': sum(e.amount for e in events if e.is_approved),
            'paid_amount': sum(e.amount for e in events if e.is_paid),
            'event_count': len(events),
        }

    @classmethod
    def get_totals_for_partner(cls, partner_id, org_season_id=None, status=None):
        """Get payment totals for a partner.

        Args:
            partner_id: UmpirePartner ID
            org_season_id: Optional season filter
            status: Optional status filter (default: all active)

        Returns:
            Dict with total_amount, event_count by type
        """
        query = cls.query.filter_by(partner_id=partner_id)

        if org_season_id is not None:
            query = query.filter_by(org_season_id=org_season_id)

        if status is not None:
            query = query.filter_by(status=status)
        else:
            query = query.filter(cls.status != cls.STATUS_VOIDED)

        events = query.all()

        return {
            'total_amount': sum(e.amount for e in events),
            'pending_amount': sum(e.amount for e in events if e.is_pending),
            'approved_amount': sum(e.amount for e in events if e.is_approved),
            'paid_amount': sum(e.amount for e in events if e.is_paid),
            'event_count': len(events),
            'rainout_count': sum(1 for e in events if e.event_type == cls.TYPE_RAINOUT_ARRIVAL),
            'rainout_amount': sum(e.amount for e in events if e.event_type == cls.TYPE_RAINOUT_ARRIVAL),
        }
