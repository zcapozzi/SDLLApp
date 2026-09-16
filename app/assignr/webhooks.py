"""Assignr Webhook Routes.

Provides:
- Public webhook endpoint for receiving Assignr events
- Admin views for monitoring webhook activity
"""

from flask import request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime

from app.extensions import db
from app.models.assignr_webhook_event import AssignrWebhookEvent
from app.services.assignr_webhook_service import get_webhook_service
from app.utils.logging import SDLLLogger
from . import assignr_bp

logger = SDLLLogger('assignr_webhook')


def umpire_coordinator_required(f):
    """Decorator to require umpire coordinator or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.can_manage_umpires():
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@assignr_bp.route('/webhook', methods=['POST'])
def receive_webhook():
    """
    Public endpoint to receive Assignr webhooks.

    No login required - secured via HMAC signature verification.
    Returns 200 OK quickly, then processes asynchronously.
    """
    service = get_webhook_service()

    # Verify signature
    is_valid, error = service.verify_signature(request)
    if not is_valid:
        logger.warning(f"Invalid webhook signature: {error}")
        return jsonify({'error': error}), 401

    # Parse payload
    payload, error = service.parse_webhook_payload(request)
    if not payload:
        logger.warning(f"Invalid webhook payload: {error}")
        return jsonify({'error': error}), 400

    event_id = payload.get('id')
    topic = payload.get('topic')

    # Check for duplicate
    if AssignrWebhookEvent.exists(event_id):
        logger.info(f"Duplicate webhook event {event_id}, acknowledging")
        return jsonify({'status': 'duplicate', 'event_id': event_id}), 200

    # Extract IDs from links
    game_id, assignment_id = service.extract_ids_from_payload(payload)

    # Store the event
    event = service.store_event(
        event_id=event_id,
        topic=topic,
        payload=payload,
        game_id=game_id,
        assignment_id=assignment_id
    )

    # Process the event immediately (synchronous for now)
    # In production, this could be queued for async processing
    try:
        service.process_event(event)
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {e}")
        # Don't fail the webhook - we've stored it for retry

    return jsonify({
        'status': 'received',
        'event_id': event_id,
        'topic': topic
    }), 200


@assignr_bp.route('/webhooks')
@login_required
@umpire_coordinator_required
def webhook_list():
    """Admin view: List recent webhook events."""
    from app.models.game import Game

    # Get filter from query params
    status_filter = request.args.get('status', '')
    limit = int(request.args.get('limit', 50))

    # Build query
    query = AssignrWebhookEvent.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    events = query.order_by(
        AssignrWebhookEvent.received_at.desc()
    ).limit(limit).all()

    # Get counts by status
    status_counts = {}
    for status in ['received', 'processing', 'completed', 'failed', 'ignored']:
        status_counts[status] = AssignrWebhookEvent.query.filter_by(
            status=status
        ).count()

    # Pre-fetch local games for all events that have local_game_id
    local_game_ids = [e.local_game_id for e in events if e.local_game_id]
    games_by_id = {}
    if local_game_ids:
        from sqlalchemy.orm import joinedload
        games = Game.query.options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel)
        ).filter(Game.ID.in_(local_game_ids)).all()
        games_by_id = {g.ID: g for g in games}

    return render_template(
        'assignr/webhooks.html',
        events=events,
        status_filter=status_filter,
        status_counts=status_counts,
        games_by_id=games_by_id
    )


@assignr_bp.route('/webhooks/<int:event_id>')
@login_required
@umpire_coordinator_required
def webhook_detail(event_id):
    """Admin view: View details of a specific webhook event."""
    event = AssignrWebhookEvent.query.get_or_404(event_id)

    # Parse payload for display
    payload_dict = event.get_payload_dict()

    return render_template(
        'assignr/webhook_detail.html',
        event=event,
        payload=payload_dict
    )


@assignr_bp.route('/webhooks/<int:event_id>/retry', methods=['POST'])
@login_required
@umpire_coordinator_required
def webhook_retry(event_id):
    """Retry processing a failed webhook event."""
    event = AssignrWebhookEvent.query.get_or_404(event_id)

    if event.status not in ['failed', 'ignored']:
        flash(f'Cannot retry event in {event.status} status.', 'error')
        return redirect(url_for('assignr.webhook_detail', event_id=event_id))

    # Reset status and retry
    event.status = 'received'
    event.error_message = None
    event.processed_at = None
    db.session.commit()

    service = get_webhook_service()
    success = service.process_event(event)

    if success:
        flash('Event reprocessed successfully.', 'success')
    else:
        flash(f'Event processing failed: {event.error_message}', 'error')

    return redirect(url_for('assignr.webhook_detail', event_id=event_id))


@assignr_bp.route('/webhooks/test', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def webhook_test():
    """Admin view: Test webhook processing with a simulated event."""
    from app.services.assignr_service import get_assignr_service

    assignr = get_assignr_service()

    if request.method == 'POST':
        game_id = request.form.get('game_id', '').strip()
        if not game_id:
            flash('Please enter a game ID.', 'error')
            return redirect(url_for('assignr.webhook_test'))

        # Fetch the game from Assignr
        game = assignr.get_game(int(game_id))
        if not game:
            flash(f'Game {game_id} not found in Assignr.', 'error')
            return redirect(url_for('assignr.webhook_test'))

        # Get assignments
        assignments = assignr.get_game_officials(int(game_id))

        # Create a test event (not from actual webhook)
        test_event_id = int(datetime.now().timestamp() * 1000)  # Unique ID

        event = AssignrWebhookEvent.create_from_webhook(
            event_id=test_event_id,
            topic='game.official.changed',
            payload='{"test": true, "game_id": "' + game_id + '"}',
            assignr_game_id=game_id,
            assignr_assignment_id=str(assignments[0]['id']) if assignments else None
        )
        db.session.commit()

        # Process it
        service = get_webhook_service()
        success = service.process_event(event)

        if success:
            flash(f'Test event processed. Status: {event.status}', 'success')
        else:
            flash(f'Test event failed: {event.error_message}', 'error')

        return redirect(url_for('assignr.webhook_detail', event_id=event.id))

    # GET - show test form
    return render_template('assignr/webhook_test.html')


@assignr_bp.route('/webhooks/process-pending', methods=['POST'])
@login_required
@umpire_coordinator_required
def process_pending():
    """Process any pending webhook events."""
    service = get_webhook_service()
    results = service.process_pending_events(limit=20)

    flash(
        f"Processed {results['processed']} events, {results['failed']} failed.",
        'success' if results['failed'] == 0 else 'warning'
    )

    return redirect(url_for('assignr.webhook_list'))
