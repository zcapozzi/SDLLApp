"""Service for sending notifications via Gmail"""

import json
import os
import base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.extensions import db
from app.models.notification_queue import NotificationQueue


class GmailService:
    """Send emails via Gmail API using a Google Service Account"""

    SCOPES = ['https://www.googleapis.com/auth/gmail.send']

    def __init__(self):
        self.service = None
        self.sender_email = os.environ.get('GMAIL_SENDER', 'notifications@southdurhamlittleleague.org')
        self._initialized = False

    def _initialize(self):
        """Initialize the Gmail service lazily"""
        if self._initialized:
            return

        creds_json = os.environ.get('GOOGLE_SERVICE_JSON')
        if not creds_json:
            self._initialized = True
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=self.SCOPES
            )

            # Delegate to the sender email (requires domain-wide delegation)
            delegated_credentials = credentials.with_subject(self.sender_email)

            self.service = build('gmail', 'v1', credentials=delegated_credentials)
        except ImportError:
            # Google libraries not installed
            pass
        except Exception as e:
            print(f"Failed to initialize Gmail service: {e}")

        self._initialized = True

    @property
    def is_configured(self):
        """Check if Gmail service is properly configured"""
        self._initialize()
        return self.service is not None

    def send_email(self, to, subject, body_text, body_html=None):
        """
        Send an email via Gmail API.

        Args:
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: Optional HTML body

        Returns:
            True if sent successfully

        Raises:
            Exception if sending fails
        """
        self._initialize()

        if not self.service:
            raise Exception("Gmail service not configured. Set GOOGLE_SERVICE_JSON environment variable.")

        message = MIMEMultipart('alternative')
        message['to'] = to
        message['from'] = self.sender_email
        message['subject'] = subject

        # Add plain text part
        message.attach(MIMEText(body_text, 'plain'))

        # Add HTML part if provided
        if body_html:
            message.attach(MIMEText(body_html, 'html'))

        # Encode the message
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Send via Gmail API
        self.service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return True


class NotificationService:
    """Service for managing and sending queued notifications"""

    def __init__(self):
        self.gmail = GmailService()

    @property
    def is_configured(self):
        """Check if email sending is properly configured"""
        return self.gmail.is_configured

    def send_notification(self, notification):
        """
        Send a single notification.

        Args:
            notification: NotificationQueue object

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            self.gmail.send_email(
                to=notification.recipient_email,
                subject=notification.subject,
                body_text=notification.body_text,
                body_html=notification.body_html
            )
            notification.mark_sent()
            return True
        except Exception as e:
            notification.mark_failed(str(e))
            return False

    def send_queued_notifications(self, recipient_type=None, batch_size=50):
        """
        Send pending notifications from queue.

        Args:
            recipient_type: Optional filter by recipient type ('admin', 'coach', 'umpire', 'parent')
            batch_size: Maximum number of notifications to send

        Returns:
            Dictionary with 'sent' and 'failed' counts
        """
        notifications = NotificationQueue.get_pending(
            recipient_type=recipient_type,
            limit=batch_size
        )

        results = {'sent': 0, 'failed': 0, 'total': len(notifications)}

        for notification in notifications:
            if self.send_notification(notification):
                results['sent'] += 1
            else:
                results['failed'] += 1

        return results

    def send_by_ids(self, notification_ids):
        """
        Send specific notifications by ID.

        Args:
            notification_ids: List of notification IDs to send

        Returns:
            Dictionary with 'sent' and 'failed' counts
        """
        results = {'sent': 0, 'failed': 0}

        for notif_id in notification_ids:
            notification = NotificationQueue.query.get(notif_id)
            if notification and notification.status == 'pending':
                if self.send_notification(notification):
                    results['sent'] += 1
                else:
                    results['failed'] += 1

        return results

    def skip_by_ids(self, notification_ids):
        """
        Skip specific notifications (mark as skipped without sending).

        Args:
            notification_ids: List of notification IDs to skip

        Returns:
            Number of notifications skipped
        """
        skipped = 0
        for notif_id in notification_ids:
            notification = NotificationQueue.query.get(notif_id)
            if notification and notification.status == 'pending':
                notification.mark_skipped()
                skipped += 1
        return skipped

    def skip_all(self, recipient_type=None):
        """
        Skip all pending notifications (optionally filtered by type).

        Args:
            recipient_type: Optional filter by recipient type

        Returns:
            Number of notifications skipped
        """
        query = NotificationQueue.query.filter_by(status='pending')
        if recipient_type:
            query = query.filter_by(recipient_type=recipient_type)

        notifications = query.all()
        for notification in notifications:
            notification.status = 'skipped'

        db.session.commit()
        return len(notifications)

    def retry_failed(self, batch_size=50):
        """
        Retry failed notifications.

        Args:
            batch_size: Maximum number to retry

        Returns:
            Dictionary with 'sent' and 'failed' counts
        """
        notifications = NotificationQueue.query.filter_by(
            status='failed'
        ).limit(batch_size).all()

        results = {'sent': 0, 'failed': 0, 'total': len(notifications)}

        for notification in notifications:
            # Reset to pending and try again
            notification.status = 'pending'
            notification.error_message = None
            db.session.commit()

            if self.send_notification(notification):
                results['sent'] += 1
            else:
                results['failed'] += 1

        return results

    def get_queue_summary(self):
        """
        Get a summary of the notification queue.

        Returns:
            Dictionary with counts by status and type
        """
        from sqlalchemy import func

        # Counts by status
        status_counts = db.session.query(
            NotificationQueue.status,
            func.count(NotificationQueue.id)
        ).group_by(NotificationQueue.status).all()

        # Pending counts by type
        pending_by_type = NotificationQueue.get_pending_counts()

        return {
            'by_status': {status: count for status, count in status_counts},
            'pending_by_type': pending_by_type,
            'total_pending': sum(pending_by_type.values())
        }
