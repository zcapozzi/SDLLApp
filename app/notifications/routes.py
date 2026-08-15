"""Notification queue management routes"""

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

    # Get notifications
    query = NotificationQueue.query

    if status:
        query = query.filter_by(status=status)
    if recipient_type:
        query = query.filter_by(recipient_type=recipient_type)

    notifications = query.order_by(NotificationQueue.created_at.desc()).limit(200).all()

    # Get counts by type and status
    pending_counts = NotificationQueue.get_pending_counts()
    service = NotificationService()

    return render_template(
        'notifications/queue.html',
        notifications=notifications,
        pending_counts=pending_counts,
        total_pending=sum(pending_counts.values()),
        current_type=recipient_type,
        current_status=status,
        is_configured=service.is_configured
    )


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
