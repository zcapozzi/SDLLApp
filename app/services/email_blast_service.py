"""Email Blast Service - handles gathering recipients and sending coach email blasts."""

import re
from datetime import datetime
from collections import defaultdict

from app.extensions import db
from app.models.scheduled_email import ScheduledEmail
from app.models.team import TeamSeason
from app.models.coach import CoachSeason
from app.models.user import User
from app.services.notification_service import GmailService
from sqlalchemy.orm import joinedload


def get_coaches_by_leagues(year, is_spring, leagues):
    """
    Get all coaches for the specified leagues in a season.

    Returns a list of dicts with coach info:
    [
        {
            'email': 'coach@email.com',
            'name': 'John Smith',
            'team': 'BB Majors Team 1',
            'league': 'BB Majors',
            'role': 'head'
        },
        ...
    ]
    """
    coaches = []
    seen_emails = set()

    # Get teams for the specified leagues
    teams = TeamSeason.query.filter(
        TeamSeason.year == year,
        TeamSeason.is_spring == is_spring,
        TeamSeason.active == 1,
        TeamSeason.is_placeholder == 0,
        TeamSeason.league.in_(leagues) if leagues else True
    ).options(
        joinedload(TeamSeason.coaches)
    ).all()

    for team in teams:
        for coach_season in team.coaches:
            email = coach_season.email
            if not email:
                continue

            # Avoid duplicates (same coach on multiple teams)
            email_lower = email.lower()
            if email_lower in seen_emails:
                continue
            seen_emails.add(email_lower)

            coaches.append({
                'email': email,
                'name': coach_season.name or 'Coach',
                'team': team.scheduler_display_name or team.display_name,
                'league': team.league,
                'role': coach_season.role or 'coach'
            })

    return coaches


def get_coaches_grouped_by_team(year, is_spring, leagues):
    """
    Get coaches grouped by team for individual mode sending.

    Returns a dict:
    {
        'BB Majors Team 1': [
            {'email': '...', 'name': '...', 'role': 'head'},
            {'email': '...', 'name': '...', 'role': 'assistant'}
        ],
        ...
    }
    """
    teams_data = defaultdict(list)

    teams = TeamSeason.query.filter(
        TeamSeason.year == year,
        TeamSeason.is_spring == is_spring,
        TeamSeason.active == 1,
        TeamSeason.is_placeholder == 0,
        TeamSeason.league.in_(leagues) if leagues else True
    ).options(
        joinedload(TeamSeason.coaches)
    ).all()

    for team in teams:
        team_key = f"{team.league} - {team.scheduler_display_name or team.display_name}"
        for coach_season in team.coaches:
            email = coach_season.email
            if not email:
                continue
            teams_data[team_key].append({
                'email': email,
                'name': coach_season.name or 'Coach',
                'role': coach_season.role or 'coach'
            })

    return dict(teams_data)


def html_to_plain_text(html):
    """
    Convert HTML to plain text for email fallback.

    Simple conversion - removes tags, converts common elements.
    """
    if not html:
        return ''

    text = html

    # Convert line breaks and paragraphs
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)

    # Convert links to text with URL
    text = re.sub(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
                  r'\2 (\1)', text, flags=re.IGNORECASE)

    # Convert headers to uppercase
    text = re.sub(r'<h[1-6][^>]*>([^<]+)</h[1-6]>',
                  lambda m: '\n' + m.group(1).upper() + '\n', text, flags=re.IGNORECASE)

    # Convert lists
    text = re.sub(r'<li[^>]*>', '  - ', text, flags=re.IGNORECASE)

    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)

    return text.strip()


def wrap_html_for_email(html):
    """
    Wrap HTML content with proper email styling.

    Normalizes Quill.js output (which uses <p> tags with default margins)
    to have cleaner line spacing in email clients.
    """
    if not html:
        return html

    return f'''<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.5; }}
  p {{ margin: 0 0 0.5em 0; }}
  p:last-child {{ margin-bottom: 0; }}
  p br {{ display: none; }}
  p:empty {{ display: none; }}
</style>
</head>
<body>
{html}
</body>
</html>'''


def parse_manual_recipients(text):
    """
    Parse manual recipients from text input.

    Accepts emails separated by commas, semicolons, or newlines.
    Returns list of valid email addresses.
    """
    if not text:
        return []

    # Split by common delimiters
    emails = re.split(r'[,;\n\r]+', text)

    valid_emails = []
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

    for email in emails:
        email = email.strip()
        if email and email_pattern.match(email):
            valid_emails.append(email)

    return valid_emails


def send_scheduled_email(email_record):
    """
    Process and send a scheduled email.

    This is the main entry point for sending emails.
    Called by the cron job to process pending emails.
    """
    if email_record.attempted_at:
        return  # Already attempted, skip

    email_record.mark_attempted()

    try:
        if email_record.send_mode == ScheduledEmail.MODE_INDIVIDUAL:
            results = _send_individual_mode(email_record)
        else:
            results = _send_bulk_mode(email_record)

        email_record.mark_sent(results['sent'], results['failed'])

        # Notify on failure
        if results['failed'] > 0:
            notify_failure(email_record, results)

    except Exception as e:
        email_record.mark_failed(str(e))
        notify_failure(email_record, {'error': str(e)})


def _send_bulk_mode(email_record):
    """
    Send email in bulk mode (CC or BCC).

    All recipients in one email.
    """
    gmail = GmailService()
    if not gmail.is_configured:
        raise Exception("Email service not configured")

    # Get all recipient emails
    all_emails = email_record.all_recipient_emails

    if not all_emails:
        return {'sent': 0, 'failed': 0}

    try:
        # For CC mode, use first email as TO, rest as CC
        # For BCC mode, use first email as TO, rest as BCC
        to_email = all_emails[0]
        other_emails = all_emails[1:] if len(all_emails) > 1 else None

        # Wrap HTML for proper email formatting
        wrapped_html = wrap_html_for_email(email_record.body_html)

        # Send via Resend with CC/BCC support
        _send_with_cc_bcc(
            gmail=gmail,
            to=to_email,
            cc=other_emails if email_record.send_mode == ScheduledEmail.MODE_CC else None,
            bcc=other_emails if email_record.send_mode == ScheduledEmail.MODE_BCC else None,
            subject=email_record.subject,
            body_html=wrapped_html,
            body_text=email_record.body_text,
            reply_to=email_record.reply_to
        )

        return {'sent': len(all_emails), 'failed': 0}

    except Exception as e:
        print(f"Bulk send error: {e}")
        return {'sent': 0, 'failed': len(all_emails), 'error': str(e)}


def _send_individual_mode(email_record):
    """
    Send email in individual mode (one per team).

    Each team gets ONE email with all their coaches CC'd together.
    """
    gmail = GmailService()
    if not gmail.is_configured:
        raise Exception("Email service not configured")

    # Group recipients by team
    recipients_by_team = defaultdict(list)
    for r in email_record.recipients:
        team = r.get('team', 'Unknown')
        recipients_by_team[team].append(r)

    results = {'sent': 0, 'failed': 0}

    # Wrap HTML for proper email formatting
    wrapped_html = wrap_html_for_email(email_record.body_html)

    for team_name, coaches in recipients_by_team.items():
        emails = [c['email'] for c in coaches if c.get('email')]
        if not emails:
            continue

        try:
            # First coach as TO, rest as CC
            to_email = emails[0]
            cc_emails = emails[1:] if len(emails) > 1 else None

            _send_with_cc_bcc(
                gmail=gmail,
                to=to_email,
                cc=cc_emails,
                bcc=None,
                subject=email_record.subject,
                body_html=wrapped_html,
                body_text=email_record.body_text,
                reply_to=email_record.reply_to
            )

            results['sent'] += len(emails)

        except Exception as e:
            print(f"Individual send error for {team_name}: {e}")
            results['failed'] += len(emails)

    # Also send to manual recipients (individually)
    for email in email_record.manual_recipients:
        try:
            gmail.send_email(
                to=email,
                subject=email_record.subject,
                body_text=email_record.body_text,
                body_html=wrapped_html,
                reply_to=email_record.reply_to
            )
            results['sent'] += 1
        except Exception as e:
            print(f"Manual recipient send error for {email}: {e}")
            results['failed'] += 1

    return results


def _send_with_cc_bcc(gmail, to, cc, bcc, subject, body_html, body_text, reply_to):
    """
    Send email with CC/BCC support via Resend API.

    Extends GmailService to support CC/BCC fields.
    """
    import json
    import os
    import urllib.request
    import urllib.error

    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        # Fall back to basic send if no Resend
        return gmail.send_email(to, subject, body_text, body_html, reply_to)

    sender_name = os.environ.get('GMAIL_SENDER_NAME', 'SDLL')
    sender_email = os.environ.get('GMAIL_SENDER', 'umpires@sdll.org')
    from_address = f"{sender_name} <{sender_email}>"

    payload = {
        "from": from_address,
        "to": [to] if isinstance(to, str) else to,
        "subject": subject,
        "text": body_text,
    }

    if body_html:
        payload["html"] = body_html
    if reply_to:
        payload["reply_to"] = reply_to
    if cc:
        payload["cc"] = cc if isinstance(cc, list) else [cc]
    if bcc:
        payload["bcc"] = bcc if isinstance(bcc, list) else [bcc]

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
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"Resend email sent with CC/BCC: {result.get('id')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Resend CC/BCC error: {e.code} - {error_body}")
        raise Exception(f"Resend API error: {e.code} - {error_body}")


def notify_failure(email_record, results):
    """
    Notify sender and admins of send failure.

    Only notifies once per email (tracks with failure_notified flag).
    """
    if email_record.failure_notified:
        return

    try:
        # Get sender
        sender = User.query.get(email_record.created_by)
        if not sender:
            return

        # Get all admins
        admins = User.query.filter_by(role='admin', active=1).all()

        # Build notification
        subject = f"Email Send Failed: {email_record.subject}"

        error_detail = results.get('error', email_record.error_message or 'Unknown error')

        body_text = f"""Your scheduled email failed to send completely.

Subject: {email_record.subject}
Scheduled: {email_record.scheduled_for or 'Immediate'}
Recipients: {email_record.recipient_count}
Sent: {email_record.sent_count}
Failed: {email_record.failed_count}

Error: {error_detail}

Please review and try again if needed.

- SDLL Automated Alert
"""

        body_html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
<h2 style="color: #c33;">Email Send Failed</h2>
<p>Your scheduled email failed to send completely.</p>

<table style="border-collapse: collapse; margin: 20px 0;">
<tr><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;"><strong>Subject:</strong></td><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;">{email_record.subject}</td></tr>
<tr><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;"><strong>Scheduled:</strong></td><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;">{email_record.scheduled_for or 'Immediate'}</td></tr>
<tr><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;"><strong>Recipients:</strong></td><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;">{email_record.recipient_count}</td></tr>
<tr><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;"><strong>Sent:</strong></td><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;">{email_record.sent_count}</td></tr>
<tr><td style="padding: 5px 15px; border-bottom: 1px solid #ddd;"><strong>Failed:</strong></td><td style="padding: 5px 15px; border-bottom: 1px solid #ddd; color: #c33;">{email_record.failed_count}</td></tr>
<tr><td style="padding: 5px 15px;"><strong>Error:</strong></td><td style="padding: 5px 15px; color: #c33;">{error_detail}</td></tr>
</table>

<p>Please review and try again if needed.</p>
<hr>
<p style="color: #888; font-size: 12px;">SDLL Automated Alert</p>
</body>
</html>
"""

        # Collect unique recipients
        recipients = set()
        if sender.email:
            recipients.add(sender.email)
        for admin in admins:
            if admin.email and admin.email != sender.email:
                recipients.add(admin.email)

        # Send notification
        gmail = GmailService()
        if gmail.is_configured and recipients:
            for recipient in recipients:
                try:
                    gmail.send_email(recipient, subject, body_text, body_html)
                except Exception as e:
                    print(f"Failed to send failure notification to {recipient}: {e}")

        email_record.failure_notified = 1
        db.session.commit()

    except Exception as e:
        print(f"Error sending failure notification: {e}")


def process_pending_emails():
    """
    Process all pending scheduled emails that are ready to send.

    Called by cron job. Each email is attempted exactly once.

    Returns list of results.
    """
    ready_emails = ScheduledEmail.get_ready_to_send()
    results = []

    for email_record in ready_emails:
        try:
            send_scheduled_email(email_record)
            results.append({
                'id': email_record.id,
                'status': email_record.status,
                'sent': email_record.sent_count,
                'failed': email_record.failed_count
            })
        except Exception as e:
            results.append({
                'id': email_record.id,
                'status': 'error',
                'error': str(e)
            })

    return results
