"""Service for sending notifications via Resend, SMTP, or Gmail API"""

import json
import os
import smtplib
import base64
import urllib.request
import urllib.error
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.extensions import db
from app.models.notification_queue import NotificationQueue


class GmailService:
    """Send emails via Resend (preferred), SMTP, or Gmail API"""

    def __init__(self):
        self.sender_email = os.environ.get('GMAIL_SENDER', 'umpires@sdll.org')
        self.sender_name = os.environ.get('GMAIL_SENDER_NAME', 'SDLL Umpires')

    @property
    def is_configured(self):
        """Check if email sending is properly configured"""
        return self._check_resend() or self._check_smtp() or self._check_api()

    def _check_resend(self):
        """Check if Resend is configured"""
        return bool(os.environ.get('RESEND_API_KEY'))

    def _check_smtp(self):
        """Check if SMTP is configured"""
        host = os.environ.get('SMTP_HOST')
        user = os.environ.get('SMTP_USER')
        password = os.environ.get('SMTP_PASSWORD')
        configured = all([host, user, password])
        if not configured:
            print(f"SMTP check: host={bool(host)}, user={bool(user)}, password={bool(password)}")
        return configured

    def _check_api(self):
        """Check if Gmail API is configured"""
        return bool(os.environ.get('GOOGLE_SERVICE_JSON'))

    def send_email(self, to, subject, body_text, body_html=None):
        """
        Send an email via Resend (preferred), SMTP, or Gmail API.

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
        # Try Resend first (Railway-approved, most reliable)
        if self._check_resend():
            return self._send_via_resend(to, subject, body_text, body_html)

        # Try SMTP
        if self._check_smtp():
            return self._send_via_smtp(to, subject, body_text, body_html)

        # Fall back to Gmail API
        if self._check_api():
            return self._send_via_api(to, subject, body_text, body_html)

        raise Exception("Email not configured. Set RESEND_API_KEY, SMTP_*, or GOOGLE_SERVICE_JSON.")

    def _send_via_resend(self, to, subject, body_text, body_html=None):
        """Send email via Resend API"""
        api_key = os.environ.get('RESEND_API_KEY', '').strip()

        # Resend requires format: "Display Name <email@domain.com>"
        from_address = f"{self.sender_name} <{self.sender_email}>"

        payload = {
            "from": from_address,
            "to": [to] if isinstance(to, str) else to,
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            payload["html"] = body_html

        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(
            'https://api.resend.com/emails',
            data=data,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'SDLL-App/1.0'
            },
            method='POST'
        )

        try:
            print(f"Resend: sending from '{from_address}' to '{to}'")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                print(f"Resend email sent: {result.get('id')}")
                return True
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"Resend error - from: '{from_address}', to: '{to}', error: {error_body}")
            raise Exception(f"Resend API error: {e.code} - {error_body}")

    def _send_via_smtp(self, to, subject, body_text, body_html=None):
        """Send email via SMTP (supports both TLS on 587 and SSL on 465)"""
        smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', 465))
        smtp_user = os.environ.get('SMTP_USER')
        smtp_password = os.environ.get('SMTP_PASSWORD')

        message = MIMEMultipart('alternative')
        message['To'] = to
        message['From'] = self.sender_email
        message['Subject'] = subject

        # Add plain text part
        message.attach(MIMEText(body_text, 'plain'))

        # Add HTML part if provided
        if body_html:
            message.attach(MIMEText(body_html, 'html'))

        # Use SSL for port 465, STARTTLS for port 587
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(self.sender_email, to, message.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(self.sender_email, to, message.as_string())

        return True

    def _send_via_api(self, to, subject, body_text, body_html=None):
        """Send email via Gmail API (requires domain-wide delegation)"""
        creds_json = os.environ.get('GOOGLE_SERVICE_JSON')
        if not creds_json:
            raise Exception("GOOGLE_SERVICE_JSON not configured")

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/gmail.send']
            )

            # Delegate to the sender email (requires domain-wide delegation)
            delegated_credentials = credentials.with_subject(self.sender_email)
            service = build('gmail', 'v1', credentials=delegated_credentials)

            message = MIMEMultipart('alternative')
            message['to'] = to
            message['from'] = self.sender_email
            message['subject'] = subject

            message.attach(MIMEText(body_text, 'plain'))
            if body_html:
                message.attach(MIMEText(body_html, 'html'))

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()

            return True
        except ImportError:
            raise Exception("Google API libraries not installed")
        except Exception as e:
            raise Exception(f"Gmail API error: {e}")


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
