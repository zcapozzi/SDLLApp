"""Notification queue management routes"""

from datetime import datetime, timedelta
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.notifications import notifications_bp
from app.models.notification_queue import NotificationQueue
from app.services.notification_service import NotificationService
from app.extensions import db


@notifications_bp.route('/queue')
@login_required
def queue():
    """View and manage the notification queue"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage notifications.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get filter parameters
    recipient_type = request.args.get('type')
    status = request.args.get('status', 'pending')

    # Date filter - parse cutoff date
    date_filter = request.args.get('date_filter', '')
    cutoff_date = None

    if date_filter == 'today':
        cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_filter == '3days':
        cutoff_date = datetime.utcnow() - timedelta(days=3)
    elif date_filter == '7days':
        cutoff_date = datetime.utcnow() - timedelta(days=7)
    elif date_filter == 'custom':
        custom_date = request.args.get('cutoff_date', '')
        if custom_date:
            try:
                cutoff_date = datetime.strptime(custom_date, '%Y-%m-%d')
            except ValueError:
                pass

    # Get notifications
    query = NotificationQueue.query

    if status:
        query = query.filter_by(status=status)
    if recipient_type:
        query = query.filter_by(recipient_type=recipient_type)
    if cutoff_date:
        query = query.filter(NotificationQueue.created_at >= cutoff_date)

    notifications = query.order_by(NotificationQueue.created_at.desc()).limit(200).all()

    # Get counts by type and status (with date filter if applied)
    pending_counts = _get_pending_counts_filtered(cutoff_date)
    service = NotificationService()

    return render_template(
        'notifications/queue.html',
        notifications=notifications,
        pending_counts=pending_counts,
        total_pending=sum(pending_counts.values()),
        current_type=recipient_type,
        current_status=status,
        date_filter=date_filter,
        cutoff_date=cutoff_date.strftime('%Y-%m-%d') if cutoff_date else '',
        is_configured=service.is_configured
    )


def _get_pending_counts_filtered(cutoff_date=None):
    """Get count of pending notifications by recipient type, optionally filtered by date."""
    from sqlalchemy import func

    query = db.session.query(
        NotificationQueue.recipient_type,
        func.count(NotificationQueue.id)
    ).filter(NotificationQueue.status == 'pending')

    if cutoff_date:
        query = query.filter(NotificationQueue.created_at >= cutoff_date)

    results = query.group_by(NotificationQueue.recipient_type).all()
    return {rtype: count for rtype, count in results}


@notifications_bp.route('/queue/send', methods=['POST'])
@login_required
def send_notifications():
    """Send notifications"""
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    action = request.form.get('action')
    service = NotificationService()

    if not service.is_configured:
        flash('Email service is not configured. Set GOOGLE_SERVICE_JSON environment variable.', 'error')
        return redirect(url_for('notifications.queue'))

    if action == 'send_selected':
        # Send selected notifications
        notification_ids = request.form.getlist('notification_ids')
        if notification_ids:
            notification_ids = [int(nid) for nid in notification_ids]
            results = service.send_by_ids(notification_ids)
            flash(f'Sent {results["sent"]} notifications, {results["failed"]} failed.', 'success')
        else:
            flash('No notifications selected.', 'error')

    elif action == 'send_type':
        # Send all of a specific type
        recipient_type = request.form.get('recipient_type')
        results = service.send_queued_notifications(recipient_type=recipient_type, batch_size=100)
        flash(f'Sent {results["sent"]} {recipient_type} notifications, {results["failed"]} failed.', 'success')

    elif action == 'send_all':
        # Send all pending
        results = service.send_queued_notifications(batch_size=100)
        flash(f'Sent {results["sent"]} notifications, {results["failed"]} failed.', 'success')

    elif action == 'skip_selected':
        # Skip selected notifications
        notification_ids = request.form.getlist('notification_ids')
        if notification_ids:
            notification_ids = [int(nid) for nid in notification_ids]
            skipped = service.skip_by_ids(notification_ids)
            flash(f'Skipped {skipped} notifications.', 'success')
        else:
            flash('No notifications selected.', 'error')

    elif action == 'skip_type':
        # Skip all of a specific type
        recipient_type = request.form.get('recipient_type')
        skipped = service.skip_all(recipient_type=recipient_type)
        flash(f'Skipped {skipped} {recipient_type} notifications.', 'success')

    elif action == 'skip_all':
        # Skip all pending
        skipped = service.skip_all()
        flash(f'Skipped {skipped} notifications.', 'success')

    elif action == 'retry_failed':
        # Retry failed notifications
        results = service.retry_failed(batch_size=50)
        flash(f'Retried {results["total"]} notifications: {results["sent"]} sent, {results["failed"]} still failed.', 'success')

    return redirect(url_for('notifications.queue'))


@notifications_bp.route('/queue/<int:notification_id>/preview')
@login_required
def preview_notification(notification_id):
    """Preview a notification's content"""
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    notification = NotificationQueue.query.get_or_404(notification_id)

    return render_template(
        'notifications/preview.html',
        notification=notification
    )


@notifications_bp.route('/api/queue/summary')
@login_required
def api_queue_summary():
    """API endpoint to get queue summary"""
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    service = NotificationService()
    summary = service.get_queue_summary()

    return jsonify({
        'success': True,
        'summary': summary
    })


@notifications_bp.route('/queue/draft-email')
@login_required
def draft_email():
    """Generate a draft email summarizing pending notifications.

    Groups notifications by recipient type and game, showing what changes
    need to be communicated. Supports date filtering to focus on recent changes.
    """
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage notifications.', 'error')
        return redirect(url_for('notifications.queue'))

    # Get filter parameters
    recipient_type = request.args.get('type')
    date_filter = request.args.get('date_filter', '')
    cutoff_date = None

    if date_filter == 'today':
        cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_filter == '3days':
        cutoff_date = datetime.utcnow() - timedelta(days=3)
    elif date_filter == '7days':
        cutoff_date = datetime.utcnow() - timedelta(days=7)
    elif date_filter == 'custom':
        custom_date = request.args.get('cutoff_date', '')
        if custom_date:
            try:
                cutoff_date = datetime.strptime(custom_date, '%Y-%m-%d')
            except ValueError:
                pass

    # Get pending notifications with filters
    query = NotificationQueue.query.filter_by(status='pending')

    if recipient_type:
        query = query.filter_by(recipient_type=recipient_type)
    if cutoff_date:
        query = query.filter(NotificationQueue.created_at >= cutoff_date)

    notifications = query.order_by(
        NotificationQueue.recipient_type,
        NotificationQueue.game_id,
        NotificationQueue.created_at
    ).all()

    # Group notifications by type and game
    grouped = _group_notifications_for_draft(notifications)

    # Generate email content
    email_data = _generate_draft_email_content(grouped, cutoff_date)

    return render_template(
        'notifications/draft_email.html',
        grouped=grouped,
        email_data=email_data,
        notification_count=len(notifications),
        current_type=recipient_type,
        date_filter=date_filter,
        cutoff_date=cutoff_date.strftime('%Y-%m-%d') if cutoff_date else ''
    )


def _group_notifications_for_draft(notifications):
    """Group notifications by recipient type and game for the draft email."""
    grouped = defaultdict(lambda: defaultdict(list))

    for notif in notifications:
        grouped[notif.recipient_type][notif.game_id].append(notif)

    # Convert to regular dict and add game info
    result = {}
    for rtype, games in grouped.items():
        result[rtype] = []
        for game_id, notifs in games.items():
            game = notifs[0].game if notifs else None
            result[rtype].append({
                'game': game,
                'notifications': notifs,
                'recipients': list(set(n.recipient_email for n in notifs))
            })

        # Sort by game date
        result[rtype].sort(key=lambda x: x['game'].game_date if x['game'] and x['game'].game_date else datetime.min)

    return result


def _generate_draft_email_content(grouped, cutoff_date=None):
    """Generate email subject and body from grouped notifications."""
    if not grouped:
        return {
            'subject': 'No pending notifications',
            'body_text': 'There are no pending notifications to report.',
            'body_html': '<p>There are no pending notifications to report.</p>'
        }

    total_games = sum(len(games) for games in grouped.values())
    total_notifications = sum(
        sum(len(g['notifications']) for g in games)
        for games in grouped.values()
    )

    # Date range description
    date_desc = ''
    if cutoff_date:
        date_desc = f" (since {cutoff_date.strftime('%b %d, %Y')})"

    subject = f"SDLL Schedule Changes Summary - {total_games} game(s) affected{date_desc}"

    # Build HTML body
    html_parts = [
        '<!DOCTYPE html>',
        '<html><head><style>',
        'body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }',
        '.section-header { background: #FF8C00; color: white; padding: 8px 12px; margin: 20px 0 10px 0; border-radius: 4px; }',
        '.game-card { background: #f9f9f9; border-left: 4px solid #228B22; padding: 12px; margin: 10px 0; }',
        '.game-title { font-weight: bold; color: #228B22; margin-bottom: 8px; }',
        '.recipient-list { font-size: 12px; color: #666; margin-top: 8px; }',
        '.change-item { margin: 4px 0; padding-left: 10px; }',
        '</style></head>',
        '<body>',
        f'<h2 style="color: #228B22;">Schedule Changes Summary</h2>',
        f'<p>The following games have pending notifications{date_desc}:</p>',
    ]

    text_parts = [
        f"Schedule Changes Summary{date_desc}",
        "=" * 50,
        "",
        f"Total: {total_games} game(s) with {total_notifications} notification(s)",
        ""
    ]

    type_labels = {
        'admin': 'Admin Notifications',
        'coach': 'Coach Notifications',
        'umpire': 'Umpire Notifications',
        'parent': 'Parent Notifications',
        'partner': 'Partner Notifications'
    }

    for rtype in ['coach', 'umpire', 'parent', 'admin', 'partner']:
        if rtype not in grouped:
            continue

        games = grouped[rtype]
        html_parts.append(f'<div class="section-header">{type_labels.get(rtype, rtype.title())} ({len(games)} game(s))</div>')
        text_parts.append(f"\n{type_labels.get(rtype, rtype.title())} ({len(games)} game(s))")
        text_parts.append("-" * 40)

        for item in games:
            game = item['game']
            notifs = item['notifications']
            recipients = item['recipients']

            if game:
                game_date = game.game_date.strftime('%a, %b %d at %I:%M %p').replace(' 0', ' ') if game.game_date else 'TBD'
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'
                field = game.field_name or 'TBD'
                league = game.league or ''

                html_parts.append('<div class="game-card">')
                html_parts.append(f'<div class="game-title">{league}: {home} vs {away}</div>')
                html_parts.append(f'<div>{game_date} at {field}</div>')

                # Show first notification subject as the change description
                if notifs:
                    change_desc = notifs[0].subject
                    html_parts.append(f'<div class="change-item">{change_desc}</div>')

                html_parts.append(f'<div class="recipient-list">Recipients: {", ".join(recipients[:5])}{"..." if len(recipients) > 5 else ""}</div>')
                html_parts.append('</div>')

                text_parts.append(f"\n  {league}: {home} vs {away}")
                text_parts.append(f"  {game_date} at {field}")
                if notifs:
                    text_parts.append(f"  Change: {notifs[0].subject}")
                text_parts.append(f"  Recipients: {', '.join(recipients[:5])}{'...' if len(recipients) > 5 else ''}")

    html_parts.extend([
        '<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">',
        '<p style="color: #888; font-size: 12px;">',
        f'Generated at {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}',
        '</p>',
        '</body></html>'
    ])

    text_parts.extend([
        "",
        "-" * 50,
        f"Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    ])

    return {
        'subject': subject,
        'body_text': '\n'.join(text_parts),
        'body_html': '\n'.join(html_parts)
    }
