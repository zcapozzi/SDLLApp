"""GameUmpire model - umpire assignments to games."""

from datetime import datetime
from app.extensions import db


class GameUmpire(db.Model):
    """Umpire assignment to a specific game.

    Supports both SDLL umpire assignments (via umpire_profile_id)
    and partner company assignments (via partner_id).
    Only one of these should be set per assignment.
    """
    __tablename__ = 'sdll_game_umpires'

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'),
                        nullable=False)

    # Assignment type (mutually exclusive)
    umpire_profile_id = db.Column(db.Integer,
                                   db.ForeignKey('sdll_umpire_profiles.id', ondelete='SET NULL'))
    partner_id = db.Column(db.Integer,
                           db.ForeignKey('sdll_umpire_partners.id', ondelete='SET NULL'))

    # Role and position
    role = db.Column(db.String(20), default='umpire')
    # Options: 'plate', 'base', 'umpire' (single umpire games)
    position_number = db.Column(db.SmallInteger, default=1)
    # 1 or 2 for 2-umpire crews

    # Status tracking
    status = db.Column(db.String(20), default='assigned')
    # Options: 'assigned', 'confirmed', 'cancelled', 'no_show', 'completed'

    # Confirmation
    confirmed_at = db.Column(db.DateTime)
    confirmation_method = db.Column(db.String(20))
    # Options: 'app', 'email', 'phone'

    # Pay information
    base_pay = db.Column(db.Numeric(6, 2))
    bonus_multiplier = db.Column(db.Numeric(3, 2), default=1.0)
    # 1.5 for emergency fill, etc.

    # Assignment tracking
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))

    # Notes for issues
    notes = db.Column(db.Text)

    # Cancellation tracking (for emergency fill notifications)
    was_previously_cancelled = db.Column(db.Boolean, default=False)
    cancelled_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))

    # Relationships
    game = db.relationship('Game', backref=db.backref('umpire_slots', lazy='dynamic'))
    umpire = db.relationship('UmpireProfile', back_populates='assignments',
                             foreign_keys=[umpire_profile_id])
    partner = db.relationship('UmpirePartner', back_populates='game_assignments',
                              foreign_keys=[partner_id])
    assigner = db.relationship('User', foreign_keys=[assigned_by])
    canceller = db.relationship('User', foreign_keys=[cancelled_by])

    # Status constants
    STATUS_ASSIGNED = 'assigned'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NO_SHOW = 'no_show'
    STATUS_COMPLETED = 'completed'
    STATUSES = [STATUS_ASSIGNED, STATUS_CONFIRMED, STATUS_CANCELLED,
                STATUS_NO_SHOW, STATUS_COMPLETED]

    # Role constants
    ROLE_PLATE = 'plate'
    ROLE_BASE = 'base'
    ROLE_UMPIRE = 'umpire'  # For single-umpire games
    ROLES = [ROLE_PLATE, ROLE_BASE, ROLE_UMPIRE]

    def __repr__(self):
        if self.umpire_profile_id:
            return f'<GameUmpire {self.id}: umpire {self.umpire_profile_id} on game {self.game_id}>'
        return f'<GameUmpire {self.id}: partner {self.partner_id} on game {self.game_id}>'

    @property
    def is_sdll_umpire(self):
        """Check if this is an SDLL umpire assignment."""
        return self.umpire_profile_id is not None

    @property
    def is_partner_assignment(self):
        """Check if this is a partner company assignment."""
        return self.partner_id is not None

    @property
    def is_confirmed(self):
        """Check if assignment is confirmed."""
        return self.status == self.STATUS_CONFIRMED

    @property
    def is_active(self):
        """Check if assignment is active (not cancelled/no-show)."""
        return self.status not in [self.STATUS_CANCELLED, self.STATUS_NO_SHOW]

    @property
    def total_pay(self):
        """Calculate total pay including bonus multiplier."""
        if self.base_pay:
            return float(self.base_pay) * float(self.bonus_multiplier or 1.0)
        return None

    @property
    def umpire_name(self):
        """Get the name of the assigned umpire or partner."""
        if self.umpire:
            return self.umpire.full_name
        if self.partner:
            return self.partner.name
        return None

    def confirm(self, method='app'):
        """Confirm this assignment.

        Args:
            method: How confirmation was received ('app', 'email', 'phone')
        """
        self.status = self.STATUS_CONFIRMED
        self.confirmed_at = datetime.utcnow()
        self.confirmation_method = method

    def cancel(self, user_id):
        """Cancel this assignment and mark for emergency fill notification.

        Args:
            user_id: ID of user who cancelled (umpire or coordinator)
        """
        self.status = self.STATUS_CANCELLED
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by = user_id
        self.was_previously_cancelled = True  # Next claim triggers coordinator notification

    def complete(self):
        """Mark assignment as completed (game finished)."""
        self.status = self.STATUS_COMPLETED

    def mark_no_show(self):
        """Mark umpire as no-show."""
        self.status = self.STATUS_NO_SHOW

    @classmethod
    def get_for_game(cls, game_id):
        """Get all active umpire assignments for a game."""
        return cls.query.filter_by(
            game_id=game_id
        ).filter(cls.status.notin_([cls.STATUS_CANCELLED])).all()

    @classmethod
    def get_for_umpire(cls, umpire_profile_id, future_only=False):
        """Get all game assignments for an umpire.

        Args:
            umpire_profile_id: ID of the umpire profile
            future_only: If True, only return future games

        Returns:
            List of GameUmpire assignments
        """
        from app.models.game import Game

        query = cls.query.filter_by(umpire_profile_id=umpire_profile_id)

        if future_only:
            query = query.join(Game).filter(Game.game_date > datetime.utcnow())

        return query.join(Game).order_by(Game.game_date).all()

    @classmethod
    def get_for_partner(cls, partner_id, future_only=False):
        """Get all game assignments for a partner.

        Args:
            partner_id: ID of the partner
            future_only: If True, only return future games

        Returns:
            List of GameUmpire assignments
        """
        from app.models.game import Game

        query = cls.query.filter_by(partner_id=partner_id)

        if future_only:
            query = query.join(Game).filter(Game.game_date > datetime.utcnow())

        return query.join(Game).order_by(Game.game_date).all()

    @classmethod
    def assign_umpire(cls, game_id, umpire_profile_id, role='umpire',
                      position=1, assigned_by=None, base_pay=None):
        """Create an SDLL umpire assignment.

        Args:
            game_id: ID of the game
            umpire_profile_id: ID of the umpire profile
            role: Umpire role ('plate', 'base', 'umpire')
            position: Position number (1 or 2)
            assigned_by: User ID who made the assignment
            base_pay: Base pay amount

        Returns:
            New GameUmpire object
        """
        assignment = cls(
            game_id=game_id,
            umpire_profile_id=umpire_profile_id,
            role=role,
            position_number=position,
            assigned_by=assigned_by,
            base_pay=base_pay,
            status=cls.STATUS_ASSIGNED
        )
        db.session.add(assignment)
        return assignment

    @classmethod
    def assign_partner(cls, game_id, partner_id, role='umpire',
                       position=1, assigned_by=None):
        """Create a partner company assignment.

        Args:
            game_id: ID of the game
            partner_id: ID of the partner
            role: Umpire role ('plate', 'base', 'umpire')
            position: Position number (1 or 2)
            assigned_by: User ID who made the assignment

        Returns:
            New GameUmpire object
        """
        assignment = cls(
            game_id=game_id,
            partner_id=partner_id,
            role=role,
            position_number=position,
            assigned_by=assigned_by,
            status=cls.STATUS_ASSIGNED
        )
        db.session.add(assignment)
        return assignment
