"""Day-of umpire notification routes.

Handles:
- Listing pending day-of notifications
- Previewing notification content
- Sending or skipping notifications
- Generating new notifications
- League-wide rainout notifications
"""

from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.umpire_dayof_notification import UmpireDayOfNotification
from app.models.game_umpire import GameUmpire
from app.models.game import Game
from app.services.dayof_notification_service import DayOfNotificationService
from app.services.notification_service import GmailService

from . import umpires_bp, umpire_coordinator_required


@umpires_bp.route('/dayof')
@login_required
@umpire_coordinator_required
def dayof_notifications():
    """List day-of notifications inbox."""
    # Get target date from query param or default to today
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # Get notifications for the target date
    notifications = UmpireDayOfNotification.get_for_date(target_date)

    # Group by status
    draft_notifications = [n for n in notifications if n.is_draft]
    sent_notifications = [n for n in notifications if n.is_sent]
    skipped_notifications = [n for n in notifications if n.is_skipped]

    return render_template(
        'umpires/dayof_inbox.html',
        target_date=target_date,
        draft_notifications=draft_notifications,
        sent_notifications=sent_notifications,
        skipped_notifications=skipped_notifications
    )


@umpires_bp.route('/dayof/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_dayof_notifications():
    """Generate day-of notifications for upcoming games."""
    service = DayOfNotificationService()

    # Get time window from form
    hours_ahead = int(request.form.get('hours_ahead', 7))
    hours_start = int(request.form.get('hours_start', 0))
    regenerate_existing = request.form.get('regenerate_existing') == '1'

    try:
        notifications = service.generate_notifications(
            hours_ahead=hours_ahead,
            hours_start=hours_start,
            regenerate_existing=regenerate_existing
        )

        if notifications:
            if regenerate_existing:
                flash(f'Regenerated {len(notifications)} day-of notification(s)', 'success')
            else:
                flash(f'Generated {len(notifications)} day-of notification(s)', 'success')
        else:
            flash('No new notifications to generate', 'info')

    except Exception as e:
        flash(f'Error generating notifications: {e}', 'error')

    return redirect(url_for('umpires.dayof_notifications'))


@umpires_bp.route('/dayof/<int:id>')
@login_required
@umpire_coordinator_required
def dayof_preview(id):
    """Preview a specific day-of notification."""
    notification = UmpireDayOfNotification.query.get_or_404(id)

    return render_template(
        'umpires/dayof_preview.html',
        notification=notification
    )


@umpires_bp.route('/dayof/<int:id>', methods=['POST'])
@login_required
@umpire_coordinator_required
def dayof_action(id):
    """Handle day-of notification actions: send, skip."""
    notification = UmpireDayOfNotification.query.get_or_404(id)
    action = request.form.get('action')

    service = DayOfNotificationService()

    if action == 'send':
        if service.send_notification(notification, current_user.ID):
            flash(f'Email sent to {notification.umpire_name}', 'success')
        else:
            flash('Failed to send email. Check email configuration.', 'error')

    elif action == 'skip':
        notification.mark_skipped()
        flash(f'Notification skipped for {notification.umpire_name}', 'success')

    elif action == 'regenerate':
        if service.regenerate_notification(notification):
            flash(f'Notification regenerated for {notification.umpire_name}', 'success')
        else:
            flash('Failed to regenerate notification. Check that the game still exists in Assignr.', 'error')

    return redirect(url_for('umpires.dayof_preview', id=id))


@umpires_bp.route('/dayof/send-all', methods=['POST'])
@login_required
@umpire_coordinator_required
def send_all_dayof():
    """Send all pending day-of notifications."""
    service = DayOfNotificationService()

    sent, failed = service.send_all_pending(current_user.ID)

    if sent > 0:
        flash(f'Sent {sent} day-of notification(s)', 'success')
    if failed > 0:
        flash(f'Failed to send {failed} notification(s)', 'error')
    if sent == 0 and failed == 0:
        flash('No pending notifications to send', 'info')

    return redirect(url_for('umpires.dayof_notifications'))


@umpires_bp.route('/rainout-notification')
@login_required
@umpire_coordinator_required
def rainout_notification():
    """Show rainout notification form for league-wide cancellations."""
    # Get target date (default to today)
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # Get all SDL umpire assignments for games on target date
    # Only assigned/confirmed (not cancelled)
    assignments = GameUmpire.query.join(Game).filter(
        GameUmpire.umpire_profile_id.isnot(None),  # SDL umpires only
        db.func.date(Game.game_date) == target_date,
        GameUmpire.status.in_([GameUmpire.STATUS_ASSIGNED, GameUmpire.STATUS_CONFIRMED]),
        Game.status.in_(['scheduled', 'confirmed'])  # Not already cancelled/postponed
    ).all()

    # Collect unique umpires with their contact info
    umpires = {}
    for assignment in assignments:
        profile = assignment.umpire
        if profile and profile.id not in umpires:
            email = profile.contact_email
            if email:  # Only include if we have an email
                umpires[profile.id] = {
                    'profile': profile,
                    'name': profile.full_name,
                    'email': email,
                    'games': []
                }
        if profile and profile.id in umpires:
            game = assignment.game
            umpires[profile.id]['games'].append({
                'time': game.game_date.strftime('%I:%M %p').lstrip('0'),
                'league': game.league,
                'field': game.field_name
            })

    # Sort by name
    umpire_list = sorted(umpires.values(), key=lambda x: x['name'])

    # Default message
    default_message = f"All SDLL games for {target_date.strftime('%A, %B %d')} have been cancelled due to weather. We will notify you when games are rescheduled."

    return render_template(
        'umpires/rainout_notification.html',
        target_date=target_date,
        umpires=umpire_list,
        default_message=default_message
    )


@umpires_bp.route('/rainout-notification/send', methods=['POST'])
@login_required
@umpire_coordinator_required
def send_rainout_notification():
    """Send rainout notification to all SDL umpires with games on target date."""
    import os
    import json
    import urllib.request
    import urllib.error

    target_date_str = request.form.get('target_date')
    message = request.form.get('message', '').strip()
    subject = request.form.get('subject', '').strip()

    if not target_date_str:
        flash('Missing target date', 'error')
        return redirect(url_for('umpires.rainout_notification'))

    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('umpires.rainout_notification'))

    if not message:
        flash('Message cannot be empty', 'error')
        return redirect(url_for('umpires.rainout_notification', date=target_date_str))

    if not subject:
        subject = f"SDLL Games Cancelled - {target_date.strftime('%B %d, %Y')}"

    # Get all SDL umpire assignments for games on target date
    assignments = GameUmpire.query.join(Game).filter(
        GameUmpire.umpire_profile_id.isnot(None),
        db.func.date(Game.game_date) == target_date,
        GameUmpire.status.in_([GameUmpire.STATUS_ASSIGNED, GameUmpire.STATUS_CONFIRMED]),
        Game.status.in_(['scheduled', 'confirmed'])
    ).all()

    # Collect unique emails
    emails = set()
    for assignment in assignments:
        profile = assignment.umpire
        if profile:
            email = profile.contact_email
            if email:
                emails.add(email)

    if not emails:
        flash('No umpires with games on this date', 'warning')
        return redirect(url_for('umpires.rainout_notification', date=target_date_str))

    # Build email content
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #c33;">Games Cancelled</h2>
        <p style="font-size: 16px; line-height: 1.6;">{message}</p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
        <p style="color: #666; font-size: 14px;">
            South Durham Little League<br>
            <a href="https://www.southdurhamlittleleague.org">www.southdurhamlittleleague.org</a>
        </p>
    </div>
    </body>
    </html>
    """
    body_text = message

    # Send via BCC using Resend
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        flash('Email not configured (RESEND_API_KEY missing)', 'error')
        return redirect(url_for('umpires.rainout_notification', date=target_date_str))

    sender_name = os.environ.get('GMAIL_SENDER_NAME', 'SDLL Umpires')
    sender_email = os.environ.get('GMAIL_SENDER', 'umpires@sdll.org')
    from_address = f"{sender_name} <{sender_email}>"

    # Send to coordinator, BCC all umpires
    email_list = list(emails)
    payload = {
        "from": from_address,
        "to": [sender_email],  # Send to ourselves
        "bcc": email_list,     # BCC all umpires
        "subject": subject,
        "text": body_text,
        "html": body_html,
        "reply_to": sender_email
    }

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
            flash(f'Rainout notification sent to {len(email_list)} umpire(s)', 'success')
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        flash(f'Failed to send email: {error_body}', 'error')

    return redirect(url_for('umpires.rainout_notification', date=target_date_str))
