"""NotificationDraft model - groups notifications into editable email drafts."""

from datetime import datetime
from app.extensions import db


class NotificationDraft(db.Model):
    """
    Groups related notifications into a single email draft.

    Each draft represents one email that will be sent to a recipient (or group).
    The draft content is auto-generated but can be edited before sending.
    """
    __tablename__ = 'sdll_notification_drafts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Recipient info
    recipient_email = db.Column(db.String(255), nullable=False)
    recipient_name = db.Column(db.String(100))
    recipient_type = db.Column(db.Enum('admin', 'coach', 'umpire', 'parent', 'partner'), nullable=False)

    # CC recipients (JSON array of emails)
    cc_emails = db.Column(db.JSON, default=list)

    # Editable email content
    subject = db.Column(db.String(255), nullable=False)
    body_text = db.Column(db.Text, nullable=False)
    body_html = db.Column(db.Text)

    # Status tracking
    status = db.Column(db.Enum('draft', 'sent', 'deleted'), nullable=False, default='draft')
    sent_at = db.Column(db.DateTime)

    # For regenerating content if needed
    auto_generated = db.Column(db.SmallInteger, default=1)  # 1 = not manually edited

    def __repr__(self):
        return f'<NotificationDraft {self.id}: {self.recipient_type} to {self.recipient_email} - {self.status}>'

    @property
    def notification_count(self):
        """Count of notifications in this draft."""
        return self.notifications.filter_by(status='pending').count()

    @property
    def game_count(self):
        """Count of unique games in this draft."""
        from sqlalchemy import func
        return db.session.query(func.count(func.distinct(NotificationQueue.game_id))).filter(
            NotificationQueue.draft_id == self.id,
            NotificationQueue.status == 'pending'
        ).scalar() or 0

    def mark_sent(self):
        """Mark draft and all its notifications as sent."""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()

        # Mark all linked notifications as sent
        for notif in self.notifications.filter_by(status='pending'):
            notif.status = 'sent'
            notif.sent_at = datetime.utcnow()

        db.session.commit()

    def mark_deleted(self):
        """Mark draft as deleted and skip all its notifications."""
        self.status = 'deleted'

        # Mark all linked notifications as skipped
        for notif in self.notifications.filter_by(status='pending'):
            notif.status = 'skipped'

        db.session.commit()

    def regenerate_content(self):
        """Regenerate the draft content from its notifications."""
        from app.notifications.routes import _format_change_description

        notifications = list(self.notifications.filter_by(status='pending').all())
        if not notifications:
            return

        # Group by game
        games = {}
        for notif in notifications:
            if notif.game_id not in games:
                games[notif.game_id] = {
                    'game': notif.game,
                    'notifications': []
                }
            games[notif.game_id]['notifications'].append(notif)

        is_umpire = self.recipient_type in ('umpire', 'partner')

        # Build email content
        if len(games) == 1:
            self.subject = "SDLL Schedule Update"
        else:
            self.subject = f"SDLL Schedule Updates ({len(games)} games)"

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head><style>',
            'body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }',
            '.game-block { background: #f9f9f9; border-left: 4px solid #228B22; padding: 12px 15px; margin: 15px 0; }',
            '.game-info { font-weight: 600; color: #228B22; margin-bottom: 6px; }',
            '.game-when { color: #555; }',
            '.change-detail { margin-top: 8px; padding: 8px; background: #fff3e0; border-radius: 4px; }',
            '</style></head>',
            '<body>',
            f'<p>Hi{" " + self.recipient_name.split()[0] if self.recipient_name else ""},</p>',
            '<p>There have been some schedule changes:</p>',
        ]

        text_parts = [
            f"Hi{' ' + self.recipient_name.split()[0] if self.recipient_name else ''},",
            "",
            "There have been some schedule changes:",
            ""
        ]

        for game_id, data in games.items():
            game = data['game']
            notifs = data['notifications']

            if not game:
                continue

            # Format game info
            if game.game_date:
                date_str = game.game_date.strftime('%A, %B %d').replace(' 0', ' ')
                time_str = game.game_date.strftime('%I:%M %p').lstrip('0')
            else:
                date_str = 'TBD'
                time_str = ''

            field = game.field_name or 'TBD'

            if is_umpire:
                title = f"{game.league or ''} game on {date_str}"
                when = f"{time_str} at {field}" if time_str else f"at {field}"
            else:
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'
                title = f"{home} vs {away}"
                when = f"{date_str} at {time_str} - {field}"

            change_desc = _format_change_description(notifs, game)

            html_parts.append('<div class="game-block">')
            html_parts.append(f'<div class="game-info">{title}</div>')
            html_parts.append(f'<div class="game-when">{when}</div>')
            html_parts.append(f'<div class="change-detail">{change_desc}</div>')
            html_parts.append('</div>')

            text_parts.extend([
                f"  {title}",
                f"  {when}",
                f"  >> {change_desc}",
                ""
            ])

        html_parts.extend([
            '<p style="margin-top: 20px;">Thanks,<br>SDLL</p>',
            '</body></html>'
        ])

        text_parts.extend([
            "Thanks,",
            "SDLL"
        ])

        self.body_html = '\n'.join(html_parts)
        self.body_text = '\n'.join(text_parts)
        self.auto_generated = 1

        db.session.commit()

    @classmethod
    def get_or_create_for_recipient(cls, recipient_email, recipient_type, recipient_name=None):
        """Get existing draft or create new one for a recipient."""
        draft = cls.query.filter_by(
            recipient_email=recipient_email,
            recipient_type=recipient_type,
            status='draft'
        ).first()

        if not draft:
            draft = cls(
                recipient_email=recipient_email,
                recipient_type=recipient_type,
                recipient_name=recipient_name,
                subject='',
                body_text='',
                body_html=''
            )
            db.session.add(draft)
            db.session.commit()

        return draft

    @classmethod
    def get_pending_drafts(cls, recipient_type=None):
        """Get all pending drafts, optionally filtered by type."""
        query = cls.query.filter_by(status='draft')
        if recipient_type:
            query = query.filter_by(recipient_type=recipient_type)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def generate_drafts_from_queue(cls):
        """
        Generate or update drafts from pending notifications.

        Groups notifications by recipient_email + recipient_type,
        creates/updates drafts for each group.

        Returns:
            Number of drafts created or updated
        """
        from sqlalchemy import func

        # Find all pending notifications without a draft
        pending = NotificationQueue.query.filter(
            NotificationQueue.status == 'pending',
            NotificationQueue.draft_id.is_(None)
        ).all()

        if not pending:
            return 0

        # Group by recipient
        groups = {}
        for notif in pending:
            key = (notif.recipient_email, notif.recipient_type)
            if key not in groups:
                groups[key] = {
                    'name': notif.recipient_name,
                    'notifications': []
                }
            groups[key]['notifications'].append(notif)

        count = 0
        for (email, rtype), data in groups.items():
            # Get or create draft
            draft = cls.get_or_create_for_recipient(email, rtype, data['name'])

            # Link notifications to draft
            for notif in data['notifications']:
                notif.draft_id = draft.id

            db.session.commit()

            # Regenerate content
            draft.regenerate_content()
            count += 1

        return count


# Import NotificationQueue for use in methods above
from app.models.notification_queue import NotificationQueue
