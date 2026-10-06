"""UmpireDayOfNotification model - day-of pregame emails for Academy umpires."""

import json
from datetime import datetime
from app.extensions import db


class UmpireDayOfNotification(db.Model):
    """Day-of pregame notification for Academy umpires.

    Tracks the generation and sending of pregame information emails
    to individual umpires assigned to games through Assignr.

    Workflow:
    - Notifications are created with status='scheduled' and scheduled_send_at set
    - After the scheduled time passes, cron auto-sends unless deactivated
    - Admin can deactivate individual notifications or all at once
    - If a game is postponed, notifications are auto-deactivated
    """
    __tablename__ = 'sdll_umpire_dayof_notifications'

    # Status constants
    STATUS_DRAFT = 'draft'  # Legacy - manual approval required
    STATUS_SCHEDULED = 'scheduled'  # Will auto-send at scheduled_send_at
    STATUS_SENT = 'sent'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [STATUS_DRAFT, STATUS_SCHEDULED, STATUS_SENT, STATUS_SKIPPED]

    # Deactivation reason constants
    REASON_MANUAL = 'manual'
    REASON_GAME_POSTPONED = 'game_postponed'
    REASON_GAME_CANCELLED = 'game_cancelled'
    REASON_BULK_DEACTIVATE = 'bulk_deactivate'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Game identification
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='SET NULL'))
    assignr_game_id = db.Column(db.Integer, nullable=False)

    # Umpire identification (from Assignr)
    assignr_official_id = db.Column(db.Integer, nullable=False)
    umpire_name = db.Column(db.String(200), nullable=False)

    # Season tracking
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)

    # Recipients (JSON array of email addresses)
    recipient_emails = db.Column(db.Text, nullable=False)

    # Content
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)

    # Game details for display
    game_date = db.Column(db.DateTime, nullable=False)
    game_location = db.Column(db.String(100))
    game_league = db.Column(db.String(50))
    home_team = db.Column(db.String(100))
    away_team = db.Column(db.String(100))

    # Workflow
    status = db.Column(db.Enum('draft', 'scheduled', 'sent', 'skipped'),
                       nullable=False, default='scheduled')
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID',
                        ondelete='SET NULL'))

    # Scheduling - for auto-send workflow
    scheduled_send_at = db.Column(db.DateTime)  # When to auto-send

    # Deactivation - admin can stop scheduled notifications
    deactivated = db.Column(db.Boolean, default=False)
    deactivated_at = db.Column(db.DateTime)
    deactivated_reason = db.Column(db.String(50))  # manual, game_postponed, etc.

    # Relationships
    game = db.relationship('Game', backref='dayof_notifications',
                          foreign_keys=[game_id])
    sender = db.relationship('User', foreign_keys=[sent_by])

    # Unique constraint: one notification per game per umpire
    __table_args__ = (
        db.UniqueConstraint('assignr_game_id', 'assignr_official_id',
                           name='uq_dayof_notification_game_official'),
    )

    def __repr__(self):
        return f'<UmpireDayOfNotification {self.umpire_name} game={self.assignr_game_id}>'

    @property
    def recipient_emails_list(self):
        """Parse recipient_emails JSON to list."""
        if not self.recipient_emails:
            return []
        try:
            return json.loads(self.recipient_emails)
        except (json.JSONDecodeError, TypeError):
            return [e.strip() for e in self.recipient_emails.split(',') if e.strip()]

    @recipient_emails_list.setter
    def recipient_emails_list(self, emails):
        """Set recipient_emails from a list."""
        self.recipient_emails = json.dumps(emails) if emails else '[]'

    @property
    def game_time_str(self):
        """Return formatted game time."""
        if self.game_date:
            time_str = self.game_date.strftime('%I:%M%p').lstrip('0')
            return time_str.replace(':00', '')
        return ''

    @property
    def arrive_time_str(self):
        """Return suggested arrival time (10 minutes before game)."""
        if self.game_date:
            from datetime import timedelta
            arrive = self.game_date - timedelta(minutes=10)
            time_str = arrive.strftime('%I:%M%p').lstrip('0')
            return time_str.replace(':00', '')
        return ''

    @property
    def game_date_display(self):
        """Return formatted game date."""
        if self.game_date:
            return self.game_date.strftime('%A, %B %d')
        return ''

    @property
    def is_draft(self):
        return self.status == self.STATUS_DRAFT

    @property
    def is_scheduled(self):
        return self.status == self.STATUS_SCHEDULED

    @property
    def is_sent(self):
        return self.status == self.STATUS_SENT

    @property
    def is_skipped(self):
        return self.status == self.STATUS_SKIPPED

    @property
    def can_send(self):
        """Check if notification can be sent."""
        if self.deactivated:
            return False
        if self.status not in [self.STATUS_DRAFT, self.STATUS_SCHEDULED]:
            return False
        return len(self.recipient_emails_list) > 0

    @property
    def is_ready_to_send(self):
        """Check if scheduled notification is ready to auto-send."""
        if self.status != self.STATUS_SCHEDULED:
            return False
        if self.deactivated:
            return False
        if not self.scheduled_send_at:
            return False
        # scheduled_send_at is stored in Eastern time, so compare to Eastern time
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_eastern = datetime.now(eastern).replace(tzinfo=None)
        return self.scheduled_send_at <= now_eastern

    @property
    def minutes_until_send(self):
        """Get minutes until scheduled send (negative if past due)."""
        if not self.scheduled_send_at:
            return None
        # scheduled_send_at is stored in Eastern time, so compare to Eastern time
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_eastern = datetime.now(eastern).replace(tzinfo=None)
        delta = self.scheduled_send_at - now_eastern
        return int(delta.total_seconds() / 60)

    @property
    def send_time_display(self):
        """Return formatted scheduled send time (Eastern time)."""
        if self.scheduled_send_at:
            return self.scheduled_send_at.strftime('%I:%M %p').lstrip('0')
        return ''

    def mark_sent(self, user_id=None):
        """Mark notification as sent."""
        self.status = self.STATUS_SENT
        self.sent_at = datetime.utcnow()
        self.sent_by = user_id
        db.session.commit()

    def mark_skipped(self):
        """Mark notification as skipped."""
        self.status = self.STATUS_SKIPPED
        db.session.commit()

    def deactivate(self, reason=None):
        """Deactivate this notification (prevent auto-send).

        Args:
            reason: Why deactivated (manual, game_postponed, etc.)
        """
        self.deactivated = True
        self.deactivated_at = datetime.utcnow()
        self.deactivated_reason = reason or self.REASON_MANUAL
        db.session.commit()

    def reactivate(self):
        """Reactivate a deactivated notification."""
        self.deactivated = False
        self.deactivated_at = None
        self.deactivated_reason = None
        db.session.commit()

    @classmethod
    def get_pending_for_today(cls):
        """Get all draft notifications for games today."""
        from datetime import date
        today = date.today()

        return cls.query.filter(
            cls.status == cls.STATUS_DRAFT,
            db.func.date(cls.game_date) == today
        ).order_by(cls.game_date, cls.umpire_name).all()

    @classmethod
    def get_for_date(cls, target_date):
        """Get all notifications for games on a specific date."""
        return cls.query.filter(
            db.func.date(cls.game_date) == target_date
        ).order_by(cls.game_date, cls.umpire_name).all()

    @classmethod
    def get_for_game(cls, assignr_game_id):
        """Get all notifications for a specific game."""
        return cls.query.filter_by(
            assignr_game_id=assignr_game_id
        ).order_by(cls.umpire_name).all()

    @classmethod
    def exists_for_game_umpire(cls, assignr_game_id, assignr_official_id):
        """Check if a sent, draft, or scheduled notification exists for this game/umpire combo.

        Returns False for skipped notifications so they can be regenerated.
        """
        return cls.query.filter(
            cls.assignr_game_id == assignr_game_id,
            cls.assignr_official_id == assignr_official_id,
            cls.status.in_([cls.STATUS_DRAFT, cls.STATUS_SCHEDULED, cls.STATUS_SENT])
        ).first() is not None

    @classmethod
    def get_scheduled_for_today(cls):
        """Get all scheduled (pending auto-send) notifications for today."""
        from datetime import date
        today = date.today()

        return cls.query.filter(
            cls.status == cls.STATUS_SCHEDULED,
            cls.deactivated == False,
            db.func.date(cls.game_date) == today
        ).order_by(cls.game_date, cls.umpire_name).all()

    @classmethod
    def get_ready_to_send_all(cls):
        """Get all notifications ready to auto-send (scheduled time has passed)."""
        # scheduled_send_at is stored in Eastern time, so compare to Eastern time
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_eastern = datetime.now(eastern).replace(tzinfo=None)
        return cls.query.filter(
            cls.status == cls.STATUS_SCHEDULED,
            cls.deactivated == False,
            cls.scheduled_send_at <= now_eastern
        ).order_by(cls.scheduled_send_at).all()

    @classmethod
    def deactivate_for_game(cls, game_id, reason=None):
        """Deactivate all scheduled notifications for a game.

        Used when a game is postponed or cancelled.

        Args:
            game_id: Local game ID (not Assignr ID)
            reason: Why deactivated

        Returns:
            int: Number of notifications deactivated
        """
        notifications = cls.query.filter(
            cls.game_id == game_id,
            cls.status == cls.STATUS_SCHEDULED,
            cls.deactivated == False
        ).all()

        count = 0
        for notif in notifications:
            notif.deactivated = True
            notif.deactivated_at = datetime.utcnow()
            notif.deactivated_reason = reason or cls.REASON_GAME_POSTPONED
            count += 1

        if count > 0:
            db.session.commit()

        return count

    @classmethod
    def deactivate_all_scheduled(cls, reason=None):
        """Deactivate all currently scheduled notifications.

        Args:
            reason: Why deactivated

        Returns:
            int: Number of notifications deactivated
        """
        from datetime import date
        today = date.today()

        notifications = cls.query.filter(
            cls.status == cls.STATUS_SCHEDULED,
            cls.deactivated == False,
            db.func.date(cls.game_date) == today
        ).all()

        count = 0
        for notif in notifications:
            notif.deactivated = True
            notif.deactivated_at = datetime.utcnow()
            notif.deactivated_reason = reason or cls.REASON_BULK_DEACTIVATE
            count += 1

        if count > 0:
            db.session.commit()

        return count
