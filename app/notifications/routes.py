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
    """Generate human-friendly email content from grouped notifications."""
    if not grouped:
        return {
            'subject': 'No pending notifications',
            'body_text': 'There are no pending notifications to report.',
            'body_html': '<p>There are no pending notifications to report.</p>'
        }

    total_games = sum(len(games) for games in grouped.values())

    # Build a friendly subject
    if total_games == 1:
        subject = "SDLL Schedule Update"
    else:
        subject = f"SDLL Schedule Updates ({total_games} games)"

    # Build HTML body
    html_parts = [
        '<!DOCTYPE html>',
        '<html><head><style>',
        'body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; }',
        '.game-block { background: #f9f9f9; border-left: 4px solid #228B22; padding: 12px 15px; margin: 15px 0; border-radius: 0 4px 4px 0; }',
        '.game-info { font-weight: 600; color: #228B22; margin-bottom: 6px; }',
        '.change-detail { color: #555; margin: 4px 0; }',
        '.section-title { color: #FF8C00; font-size: 16px; font-weight: 600; margin: 25px 0 10px 0; border-bottom: 2px solid #FF8C00; padding-bottom: 5px; }',
        '</style></head>',
        '<body>',
        '<p>Hi,</p>',
        '<p>There have been some schedule changes that need to be communicated:</p>',
    ]

    text_parts = [
        "Hi,",
        "",
        "There have been some schedule changes that need to be communicated:",
        ""
    ]

    section_intros = {
        'coach': "The following games have changes that coaches need to know about:",
        'umpire': "The following assignments have changes:",
        'parent': "The following games have changes for team families:",
        'admin': "Admin notifications:",
        'partner': "The following assignments have changes for umpire partners:"
    }

    for rtype in ['coach', 'parent', 'umpire', 'partner', 'admin']:
        if rtype not in grouped:
            continue

        games = grouped[rtype]
        is_umpire_type = rtype in ('umpire', 'partner')

        # Section header
        section_name = rtype.title() + "s" if rtype != 'admin' else 'Admin'
        html_parts.append(f'<div class="section-title">{section_name}</div>')
        html_parts.append(f'<p>{section_intros.get(rtype, "")}</p>')

        text_parts.append("")
        text_parts.append(f"--- {section_name.upper()} ---")
        text_parts.append(section_intros.get(rtype, ""))
        text_parts.append("")

        for item in games:
            game = item['game']
            notifs = item['notifications']

            if not game:
                continue

            # Format game date/time
            if game.game_date:
                game_date_str = game.game_date.strftime('%A, %B %d').replace(' 0', ' ')
                game_time_str = game.game_date.strftime('%I:%M %p').lstrip('0')
            else:
                game_date_str = 'TBD'
                game_time_str = ''

            field = game.field_name or 'TBD'
            league = game.league or ''

            # For umpires, don't show team matchup - just time/field/league
            if is_umpire_type:
                game_title = f"{league} game on {game_date_str}"
                game_subtitle = f"{game_time_str} at {field}" if game_time_str else f"at {field}"
            else:
                # For coaches/parents, show the matchup
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'
                game_title = f"{home} vs {away}"
                game_subtitle = f"{game_date_str} at {game_time_str} - {field}"

            # Extract what changed from the notification
            change_descriptions = []
            for notif in notifs:
                # Parse the subject to get a cleaner change description
                subj = notif.subject
                if ':' in subj:
                    # e.g., "Game Time Changed: Mon Sep 8 at 6:00 PM" -> "Time changed"
                    change_type = subj.split(':')[0].replace('Game ', '').strip()
                    change_descriptions.append(change_type)
                else:
                    change_descriptions.append(subj)

            # Dedupe and join changes
            unique_changes = list(dict.fromkeys(change_descriptions))
            changes_text = ", ".join(unique_changes[:3])
            if len(unique_changes) > 3:
                changes_text += f" (+{len(unique_changes) - 3} more)"

            # HTML output
            html_parts.append('<div class="game-block">')
            html_parts.append(f'<div class="game-info">{game_title}</div>')
            html_parts.append(f'<div class="change-detail">{game_subtitle}</div>')
            html_parts.append(f'<div class="change-detail"><em>Change: {changes_text}</em></div>')
            html_parts.append('</div>')

            # Plain text output
            text_parts.append(f"  {game_title}")
            text_parts.append(f"  {game_subtitle}")
            text_parts.append(f"  Change: {changes_text}")
            text_parts.append("")

    # Closing
    html_parts.extend([
        '<p style="margin-top: 25px;">Please send these notifications when ready.</p>',
        '<p>Thanks,<br>SDLL Scheduler</p>',
        '</body></html>'
    ])

    text_parts.extend([
        "---",
        "",
        "Please send these notifications when ready.",
        "",
        "Thanks,",
        "SDLL Scheduler"
    ])

    return {
        'subject': subject,
        'body_text': '\n'.join(text_parts),
        'body_html': '\n'.join(html_parts)
    }
