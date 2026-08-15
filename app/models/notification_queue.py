"""NotificationQueue model - stores pending notifications for review before sending"""

from datetime import datetime
from app.extensions import db


class NotificationQueue(db.Model):
    """Queued notifications waiting to be sent"""
    __tablename__ = 'sdll_notification_queue'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # What triggered this notification
    change_id = db.Column(db.Integer, db.ForeignKey('sdll_game_changes.id', ondelete='SET NULL'))
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'), nullable=False)

    # Recipient info
    recipient_type = db.Column(db.Enum('admin', 'coach', 'umpire', 'parent'), nullable=False)
    recipient_id = db.Column(db.Integer)  # user_id if applicable
    recipient_email = db.Column(db.String(255), nullable=False)
    recipient_name = db.Column(db.String(100))

    # Notification content
    subject = db.Column(db.String(255), nullable=False)
    body_text = db.Column(db.Text, nullable=False)
    body_html = db.Column(db.Text)

    # Status tracking
    status = db.Column(db.Enum('pending', 'sent', 'failed', 'skipped'), nullable=False, default='pending')
    sent_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    # Grouping for batch sends
    batch_id = db.Column(db.String(50))

    # Relationships
    game = db.relationship('Game', backref=db.backref('notifications', lazy='dynamic'))
    change = db.relationship('GameChange', backref=db.backref('notifications', lazy='dynamic'))

    def __repr__(self):
        return f'<NotificationQueue {self.id}: {self.recipient_type} - {self.status}>'

    def mark_sent(self):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
        db.session.commit()

    def mark_failed(self, error_message):
        """Mark notification as failed with error"""
        self.status = 'failed'
        self.error_message = error_message
        db.session.commit()

    def mark_skipped(self):
        """Mark notification as skipped (user chose not to send)"""
        self.status = 'skipped'
        db.session.commit()

    @classmethod
    def get_pending(cls, recipient_type=None, limit=100):
        """Get pending notifications, optionally filtered by type"""
        query = cls.query.filter_by(status='pending')
        if recipient_type:
            query = query.filter_by(recipient_type=recipient_type)
        return query.order_by(cls.created_at).limit(limit).all()

    @classmethod
    def get_pending_counts(cls):
        """Get count of pending notifications by recipient type"""
        from sqlalchemy import func
        results = db.session.query(
            cls.recipient_type,
            func.count(cls.id)
        ).filter_by(status='pending').group_by(cls.recipient_type).all()
        return {rtype: count for rtype, count in results}

    @classmethod
    def get_for_game(cls, game_id):
        """Get all notifications for a specific game"""
        return cls.query.filter_by(game_id=game_id).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_recent_sent(cls, days=7, limit=100):
        """Get recently sent notifications"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        return cls.query.filter(
            cls.status == 'sent',
            cls.sent_at >= cutoff
        ).order_by(cls.sent_at.desc()).limit(limit).all()

    @classmethod
    def get_failed(cls, limit=100):
        """Get failed notifications"""
        return cls.query.filter_by(status='failed').order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def create_for_change(cls, change, game, recipient_type, recipient_email, recipient_name=None, recipient_id=None):
        """Create a notification entry for a game change"""
        from app.services.notification_templates import render_change_notification

        subject, body_text, body_html = render_change_notification(change, game, recipient_type)

        notification = cls(
            change_id=change.id if change else None,
            game_id=game.ID,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            status='pending'
        )
        db.session.add(notification)
        db.session.commit()
        return notification
