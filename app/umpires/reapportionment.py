"""Umpire Game Reapportionment Routes.

Provides UI for redistributing Academy umpire games - taking games from
umpires with many assignments and giving them to umpires who need more.
"""

from datetime import datetime
from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

from app.umpires import umpires_bp, umpire_coordinator_required
from app.services.reapportionment_service import get_reapportionment_service
from app.services.assignr_service import get_assignr_service
from app.models.org_season import OrgSeason
from app.utils.logging import SDLLLogger

logger = SDLLLogger('umpires.reapportionment')


@umpires_bp.route('/reapportion/<int:org_season_id>')
@login_required
@umpire_coordinator_required
def reapportionment_dashboard(org_season_id):
    """Main reapportionment dashboard - view umpire game distribution."""
    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Get sport from query param, default to softball
    sport = request.args.get('sport', 'softball')
    if sport not in ('baseball', 'softball'):
        sport = 'softball'

    days_ahead = request.args.get('days', 30, type=int)
    if days_ahead < 7:
        days_ahead = 7
    elif days_ahead > 90:
        days_ahead = 90

    # Get dashboard data
    service = get_reapportionment_service()
    data = service.get_reapportionment_dashboard_data(
        sport=sport,
        org_season=org_season,
        days_ahead=days_ahead
    )

    # Get Academy umpires for the target dropdown
    assignr = get_assignr_service()
    academy_umpires = assignr.get_officials_by_group_name("SDLL Academy")
    academy_umpires.sort(key=lambda u: f"{u.get('first_name', '')} {u.get('last_name', '')}")

    return render_template(
        'umpires/reapportionment.html',
        org_season=org_season,
        org_season_id=org_season_id,
        season_name=org_season.season_desc,
        sport=sport,
        days_ahead=days_ahead,
        data=data,
        academy_umpires=academy_umpires
    )


@umpires_bp.route('/api/reapportion/preview', methods=['POST'])
@login_required
@umpire_coordinator_required
def reapportion_preview():
    """Preview a reassignment - get details about the game and umpires."""
    game_assignr_id = request.json.get('game_id')
    if not game_assignr_id:
        return jsonify({'success': False, 'error': 'Missing game_id'}), 400

    assignr = get_assignr_service()

    # Get game details
    game = assignr.get_game(int(game_assignr_id))
    if not game:
        return jsonify({'success': False, 'error': 'Game not found'}), 404

    # Get current assignments
    assignments = assignr.get_game_officials(int(game_assignr_id))

    # Build preview data
    current_umpires = []
    for assignment in assignments:
        embedded = assignment.get('_embedded', {}) or {}
        official = embedded.get('official', {}) or {}
        current_umpires.append({
            'id': official.get('id'),
            'name': f"{official.get('first_name', '')} {official.get('last_name', '')}".strip(),
            'accepted': assignment.get('accepted') in [True, 'True']
        })

    return jsonify({
        'success': True,
        'game': {
            'id': game.get('id'),
            'date': game.get('localized_date'),
            'time': game.get('localized_time'),
            'venue': game.get('_embedded', {}).get('venue', {}).get('name'),
            'home_team': game.get('home_team'),
            'away_team': game.get('away_team')
        },
        'current_umpires': current_umpires
    })


@umpires_bp.route('/api/reapportion/execute', methods=['POST'])
@login_required
@umpire_coordinator_required
def reapportion_execute():
    """Execute a reassignment - unassign and optionally assign to new umpire."""
    game_assignr_id = request.json.get('game_id')
    new_official_id = request.json.get('new_official_id')  # Optional
    send_notification = request.json.get('send_notification', False)
    notification_message = request.json.get('notification_message', '')

    if not game_assignr_id:
        return jsonify({'success': False, 'error': 'Missing game_id'}), 400

    service = get_reapportionment_service()
    assignr = get_assignr_service()

    # Get current assignment info before unassigning
    assignments = assignr.get_game_officials(int(game_assignr_id))
    current_official = None
    for assignment in assignments:
        embedded = assignment.get('_embedded', {}) or {}
        official = embedded.get('official', {}) or {}
        if official.get('id'):
            current_official = {
                'id': official.get('id'),
                'name': f"{official.get('first_name', '')} {official.get('last_name', '')}".strip()
            }
            break

    # Execute the reassignment
    if new_official_id:
        success, message = service.execute_reassign(
            int(game_assignr_id),
            int(new_official_id)
        )
    else:
        success, message = service.execute_unassign(int(game_assignr_id))

    if not success:
        return jsonify({'success': False, 'error': message}), 500

    # Send notifications if requested
    notifications_sent = []
    if send_notification and notification_message:
        # Notify the original umpire
        if current_official and current_official.get('id'):
            notif_success, notif_msg = service.send_notification(
                current_official['id'],
                "Game Reassignment Notice",
                notification_message
            )
            notifications_sent.append({
                'umpire': current_official['name'],
                'success': notif_success,
                'message': notif_msg
            })

        # Notify new umpire if assigned
        if new_official_id:
            # Get new official name
            new_official = assignr.get_official(int(new_official_id))
            if new_official:
                new_name = f"{new_official.get('first_name', '')} {new_official.get('last_name', '')}".strip()
                notif_success, notif_msg = service.send_notification(
                    int(new_official_id),
                    "New Game Assignment",
                    f"You have been assigned a new game. Please check Assignr for details."
                )
                notifications_sent.append({
                    'umpire': new_name,
                    'success': notif_success,
                    'message': notif_msg
                })

    logger.info(f"Reapportionment executed: game={game_assignr_id}, "
                f"from={current_official}, to={new_official_id}, "
                f"by={current_user.email}")

    return jsonify({
        'success': True,
        'message': message,
        'notifications': notifications_sent
    })


@umpires_bp.route('/api/reapportion/message', methods=['POST'])
@login_required
@umpire_coordinator_required
def reapportion_message():
    """Send a message to an umpire via Assignr."""
    official_id = request.json.get('official_id')
    subject = request.json.get('subject', 'Message from SDLL')
    body = request.json.get('body')

    if not official_id:
        return jsonify({'success': False, 'error': 'Missing official_id'}), 400
    if not body:
        return jsonify({'success': False, 'error': 'Missing message body'}), 400

    service = get_reapportionment_service()
    success, message = service.send_notification(int(official_id), subject, body)

    if success:
        logger.info(f"Message sent to official {official_id} by {current_user.email}")
        return jsonify({'success': True, 'message': 'Message sent successfully'})
    else:
        return jsonify({'success': False, 'error': message}), 500
