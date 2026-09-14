"""AssignrWebhookEvent model - stores incoming Assignr webhooks for audit and processing.

Webhooks from Assignr are logged here for:
1. Audit trail of all received events
2. Tracking processing status
3. Recording notification history
"""

from datetime import datetime
from typing import Optional, List
from app.extensions import db


class AssignrWebhookEvent(db.Model):
    """Stores Assignr webhook events for processing and audit."""
    __tablename__ = 'sdll_assignr_webhook_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.BigInteger, nullable=False, unique=True)
    topic = db.Column(db.String(100), nullable=False)
    assignr_game_id = db.Column(db.String(20))
    assignr_assignment_id = db.Column(db.String(20))
    payload = db.Column(db.Text, nullable=False)

    # Processing status
    status = db.Column(
        db.Enum('received', 'processing', 'completed', 'failed', 'ignored'),
        default='received'
    )
    error_message = db.Column(db.Text)

    # Local references
    local_game_id = db.Column(db.BigInteger)

    # Notification tracking
    notification_sent = db.Column(db.SmallInteger, default=0)
    notification_reason = db.Column(db.String(100))

    # Timestamps
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<AssignrWebhookEvent {self.id}: {self.topic} ({self.status})>'

    @classmethod
    def create_from_webhook(
        cls,
        event_id: int,
        topic: str,
        payload: str,
        assignr_game_id: Optional[str] = None,
        assignr_assignment_id: Optional[str] = None
    ) -> 'AssignrWebhookEvent':
        """
        Create a new webhook event record.

        Args:
            event_id: Assignr webhook event ID
            topic: Event topic (e.g., 'game.official.changed')
            payload: Raw JSON payload as string
            assignr_game_id: Optional game ID extracted from payload
            assignr_assignment_id: Optional assignment ID from payload

        Returns:
            AssignrWebhookEvent instance (not yet committed)
        """
        event = cls(
            event_id=event_id,
            topic=topic,
            payload=payload,
            assignr_game_id=assignr_game_id,
            assignr_assignment_id=assignr_assignment_id,
            status='received'
        )
        db.session.add(event)
        return event

    @classmethod
    def get_by_event_id(cls, event_id: int) -> Optional['AssignrWebhookEvent']:
        """Find event by Assignr event ID."""
        return cls.query.filter_by(event_id=event_id).first()

    @classmethod
    def exists(cls, event_id: int) -> bool:
        """Check if an event with this ID already exists (for deduplication)."""
        return cls.query.filter_by(event_id=event_id).count() > 0

    @classmethod
    def get_pending(cls, limit: int = 100) -> List['AssignrWebhookEvent']:
        """Get events that are received but not yet processed."""
        return cls.query.filter_by(status='received').order_by(
            cls.received_at
        ).limit(limit).all()

    @classmethod
    def get_recent(cls, limit: int = 50) -> List['AssignrWebhookEvent']:
        """Get recent events for admin view."""
        return cls.query.order_by(cls.received_at.desc()).limit(limit).all()

    @classmethod
    def get_failed(cls, limit: int = 50) -> List['AssignrWebhookEvent']:
        """Get failed events that may need retry or investigation."""
        return cls.query.filter_by(status='failed').order_by(
            cls.received_at.desc()
        ).limit(limit).all()

    def mark_processing(self):
        """Mark event as currently being processed."""
        self.status = 'processing'
        db.session.commit()

    def mark_completed(
        self,
        local_game_id: Optional[int] = None,
        notification_sent: bool = False,
        notification_reason: Optional[str] = None
    ):
        """
        Mark event as successfully processed.

        Args:
            local_game_id: Local sdll_games.ID if found
            notification_sent: Whether an alert email was sent
            notification_reason: Reason for notification (e.g., 'accepted_within_48h')
        """
        self.status = 'completed'
        self.processed_at = datetime.utcnow()
        if local_game_id:
            self.local_game_id = local_game_id
        if notification_sent:
            self.notification_sent = 1
            self.notification_reason = notification_reason
        db.session.commit()

    def mark_failed(self, error_message: str):
        """
        Mark event as failed with error details.

        Args:
            error_message: Description of what went wrong
        """
        self.status = 'failed'
        self.processed_at = datetime.utcnow()
        self.error_message = error_message[:5000] if error_message else None
        db.session.commit()

    def mark_ignored(self, reason: str):
        """
        Mark event as ignored (e.g., no matching local game).

        Args:
            reason: Why the event was ignored
        """
        self.status = 'ignored'
        self.processed_at = datetime.utcnow()
        self.error_message = reason[:5000] if reason else None
        db.session.commit()

    def get_payload_dict(self) -> dict:
        """Parse and return the JSON payload as a dictionary."""
        import json
        try:
            return json.loads(self.payload) if self.payload else {}
        except json.JSONDecodeError:
            return {}

    @property
    def hours_since_received(self) -> float:
        """Calculate hours since event was received."""
        if not self.received_at:
            return 0
        delta = datetime.utcnow() - self.received_at
        return delta.total_seconds() / 3600
