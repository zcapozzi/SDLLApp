"""Notification mute model for suppressing repeated alerts.

Allows users to mute specific notifications so they don't receive
repeated alerts about known issues (e.g., a last-minute reschedule
that's unlikely to get an umpire).
"""

from datetime import datetime, date, timedelta
from typing import Optional, List
from app.extensions import db


class NotificationMute(db.Model):
    """Tracks muted notifications to suppress repeated alerts."""

    __tablename__ = 'sdll_notification_mutes'

    id = db.Column(db.Integer, primary_key=True)

    # What type of notification is muted
    # e.g., 'missing_umpire', 'red_flag', 'unassigned_umpire', 'coach_missing'
    notification_type = db.Column(db.String(50), nullable=False, index=True)

    # What entity is muted (optional - NULL means mute all of this type)
    entity_type = db.Column(db.String(30))  # 'game', 'team', 'umpire', etc.
    entity_id = db.Column(db.BigInteger)    # ID of the specific entity

    # When does the mute expire? NULL = indefinitely (or until entity date passes)
    muted_until = db.Column(db.DateTime)

    # Optional reason for muting (for audit trail)
    reason = db.Column(db.String(255))

    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Relationships
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.Index('idx_mute_lookup', 'notification_type', 'entity_type', 'entity_id'),
    )

    @classmethod
    def is_muted(cls, notification_type: str, entity_type: str = None,
                 entity_id: int = None) -> bool:
        """Check if a notification is currently muted.

        Args:
            notification_type: Type of notification (e.g., 'missing_umpire')
            entity_type: Optional entity type (e.g., 'game')
            entity_id: Optional entity ID

        Returns:
            True if the notification should be suppressed
        """
        now = datetime.utcnow()

        # Check for exact match (specific entity muted)
        if entity_type and entity_id:
            mute = cls.query.filter(
                cls.notification_type == notification_type,
                cls.entity_type == entity_type,
                cls.entity_id == entity_id,
                db.or_(cls.muted_until.is_(None), cls.muted_until > now)
            ).first()
            if mute:
                return True

        # Check for type-level mute (all notifications of this type muted)
        type_mute = cls.query.filter(
            cls.notification_type == notification_type,
            cls.entity_type.is_(None),
            cls.entity_id.is_(None),
            db.or_(cls.muted_until.is_(None), cls.muted_until > now)
        ).first()

        return type_mute is not None

    @classmethod
    def mute(cls, notification_type: str, entity_type: str = None,
             entity_id: int = None, muted_until: datetime = None,
             reason: str = None, user_id: int = None) -> 'NotificationMute':
        """Create or update a mute for a notification.

        Args:
            notification_type: Type of notification
            entity_type: Optional entity type
            entity_id: Optional entity ID
            muted_until: When mute expires (None = indefinitely)
            reason: Optional reason for muting
            user_id: User who created the mute

        Returns:
            The created or updated NotificationMute
        """
        # Check if mute already exists
        existing = cls.query.filter(
            cls.notification_type == notification_type,
            cls.entity_type == entity_type if entity_type else cls.entity_type.is_(None),
            cls.entity_id == entity_id if entity_id else cls.entity_id.is_(None)
        ).first()

        if existing:
            # Update existing mute
            existing.muted_until = muted_until
            existing.reason = reason or existing.reason
            db.session.commit()
            return existing

        # Create new mute
        mute = cls(
            notification_type=notification_type,
            entity_type=entity_type,
            entity_id=entity_id,
            muted_until=muted_until,
            reason=reason,
            created_by_user_id=user_id
        )
        db.session.add(mute)
        db.session.commit()
        return mute

    @classmethod
    def unmute(cls, notification_type: str, entity_type: str = None,
               entity_id: int = None) -> bool:
        """Remove a mute for a notification.

        Returns:
            True if a mute was removed, False if none existed
        """
        query = cls.query.filter(cls.notification_type == notification_type)

        if entity_type:
            query = query.filter(cls.entity_type == entity_type)
        else:
            query = query.filter(cls.entity_type.is_(None))

        if entity_id:
            query = query.filter(cls.entity_id == entity_id)
        else:
            query = query.filter(cls.entity_id.is_(None))

        mute = query.first()
        if mute:
            db.session.delete(mute)
            db.session.commit()
            return True
        return False

    @classmethod
    def get_active_mutes(cls, notification_type: str = None) -> List['NotificationMute']:
        """Get all active (non-expired) mutes.

        Args:
            notification_type: Optional filter by type

        Returns:
            List of active NotificationMute records
        """
        now = datetime.utcnow()
        query = cls.query.filter(
            db.or_(cls.muted_until.is_(None), cls.muted_until > now)
        )
        if notification_type:
            query = query.filter(cls.notification_type == notification_type)

        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def mute_game_until_played(cls, game_id: int, notification_type: str,
                               reason: str = None, user_id: int = None) -> 'NotificationMute':
        """Mute notifications for a game until it's played.

        Convenience method that sets muted_until to end of game day.
        """
        from app.models.game import Game
        game = Game.query.get(game_id)
        if game and game.game_date:
            # Mute until end of game day
            muted_until = datetime.combine(
                game.game_date.date() if isinstance(game.game_date, datetime) else game.game_date,
                datetime.max.time()
            )
        else:
            # Default to 7 days if no game date
            muted_until = datetime.utcnow() + timedelta(days=7)

        return cls.mute(
            notification_type=notification_type,
            entity_type='game',
            entity_id=game_id,
            muted_until=muted_until,
            reason=reason,
            user_id=user_id
        )

    @classmethod
    def cleanup_expired(cls) -> int:
        """Remove expired mutes.

        Returns:
            Number of mutes removed
        """
        now = datetime.utcnow()
        result = cls.query.filter(
            cls.muted_until.isnot(None),
            cls.muted_until <= now
        ).delete()
        db.session.commit()
        return result

    def __repr__(self):
        entity = f"{self.entity_type}:{self.entity_id}" if self.entity_type else "all"
        until = self.muted_until.strftime('%Y-%m-%d') if self.muted_until else "indefinitely"
        return f"<NotificationMute {self.notification_type} {entity} until {until}>"
