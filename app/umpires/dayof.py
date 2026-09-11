"""Day-of umpire notification routes.

Handles:
- Listing pending day-of notifications
- Previewing notification content
- Sending or skipping notifications
- Generating new notifications
"""

from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.umpire_dayof_notification import UmpireDayOfNotification
from app.services.dayof_notification_service import DayOfNotificationService

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

    try:
        notifications = service.generate_notifications(
            hours_ahead=hours_ahead,
            hours_start=hours_start
        )

        if notifications:
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
