"""UmpireDayOfNotification model - day-of pregame emails for Academy umpires."""

import json
from datetime import datetime
from app.extensions import db


class UmpireDayOfNotification(db.Model):
    """Day-of pregame notification for Academy umpires.

    Tracks the generation and sending of pregame information emails
    to individual umpires assigned to games through Assignr.
    """
    __tablename__ = 'sdll_umpire_dayof_notifications'

    # Status constants
    STATUS_DRAFT = 'draft'
    STATUS_SENT = 'sent'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [STATUS_DRAFT, STATUS_SENT, STATUS_SKIPPED]

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
    status = db.Column(db.Enum('draft', 'sent', 'skipped'),
                       nullable=False, default='draft')
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID',
                        ondelete='SET NULL'))

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
        """Return suggested arrival time (15 minutes before game)."""
        if self.game_date:
            from datetime import timedelta
            arrive = self.game_date - timedelta(minutes=15)
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
    def is_sent(self):
        return self.status == self.STATUS_SENT

    @property
    def is_skipped(self):
        return self.status == self.STATUS_SKIPPED

    @property
    def can_send(self):
        """Check if notification can be sent."""
        return self.status == self.STATUS_DRAFT and len(self.recipient_emails_list) > 0

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
        """Check if a sent or draft notification exists for this game/umpire combo.

        Returns False for skipped notifications so they can be regenerated.
        """
        return cls.query.filter(
            cls.assignr_game_id == assignr_game_id,
            cls.assignr_official_id == assignr_official_id,
            cls.status.in_([cls.STATUS_DRAFT, cls.STATUS_SENT])
        ).first() is not None
