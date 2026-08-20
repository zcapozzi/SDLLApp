"""Service for sending error digest emails.

This service generates and sends periodic summary emails of Tier II errors.
Can be triggered manually or via a scheduled job.
"""

import os
from datetime import datetime
from app.extensions import db
from app.models.app_error import AppError
from app.utils.errors import get_error_digest_html


# Default admin email recipients
DEFAULT_ADMIN_EMAILS = ['zac@southdurhamlittleleague.org']


def get_admin_emails():
    """Get list of admin email addresses for error digests.

    Can be configured via environment variable ERROR_DIGEST_EMAILS
    as comma-separated list.
    """
    env_emails = os.environ.get('ERROR_DIGEST_EMAILS', '')
    if env_emails:
        return [e.strip() for e in env_emails.split(',') if e.strip()]
    return DEFAULT_ADMIN_EMAILS


def send_error_digest(hours=24, force=False):
    """Send error digest email to admins.

    Args:
        hours: Look back this many hours for errors
        force: If True, send even if no errors

    Returns:
        Dict with status info
    """
    from app.services.notification_service import GmailService

    result = {
        'sent': False,
        'error_count': 0,
        'recipients': [],
        'error': None
    }

    try:
        # Get digest summary
        summary = AppError.get_digest_summary(since_hours=hours)
        result['error_count'] = summary['total_count']

        # Skip if no errors and not forcing
        if summary['total_count'] == 0 and not force:
            result['sent'] = False
            return result

        # Generate HTML digest
        html_content = get_error_digest_html(hours)
        if not html_content:
            if force:
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>SDLL Error Digest</h2>
                <p>No errors in the last {hours} hours.</p>
                </body>
                </html>
                """
            else:
                return result

        # Send email
        gmail = GmailService()
        if not gmail.is_configured:
            result['error'] = 'Gmail service not configured'
            return result

        recipients = get_admin_emails()
        result['recipients'] = recipients

        subject = f"SDLL Error Digest - {summary['total_count']} errors"
        plain_text = f"SDLL Error Digest\n\n{summary['total_count']} errors in the last {hours} hours.\n\nView details at https://www.southdurhamlittleleague.org/admin/errors"

        for email in recipients:
            try:
                gmail.send_email(
                    to=email,
                    subject=subject,
                    body_text=plain_text,
                    body_html=html_content
                )
            except Exception as e:
                result['error'] = str(e)

        # Mark errors as notified
        if summary['total_count'] > 0:
            unnotified = AppError.get_unnotified_tier2()
            error_ids = [e.id for e in unnotified]
            AppError.mark_notified(error_ids)

        result['sent'] = True
        return result

    except Exception as e:
        result['error'] = str(e)
        return result


def should_send_digest():
    """Check if we should send a digest now.

    Logic:
    - Send once per day at configured hour (default 8 AM UTC)
    - Don't send if already sent today
    - Send if there are unnotified errors

    Returns:
        bool: True if digest should be sent
    """
    # Check for unnotified errors
    unnotified = AppError.get_unnotified_tier2()
    return len(unnotified) > 0


def cleanup_old_errors(days=90):
    """Delete old resolved errors.

    Args:
        days: Delete resolved errors older than this

    Returns:
        Number of errors deleted
    """
    try:
        return AppError.cleanup_old(days=days)
    except Exception:
        return 0
