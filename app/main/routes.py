"""Main routes - dashboard and home"""

from flask import Blueprint, render_template, redirect, url_for, jsonify, request, flash
from flask_login import login_required, current_user
from app.models.game import Game
from app.models.team import TeamSeason
from app.extensions import db

main_bp = Blueprint('main', __name__)


def admin_required(f):
    """Decorator to require admin access."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_edit_schedule():
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@main_bp.route('/health')
def health():
    """Health check endpoint for Railway/load balancers."""
    return jsonify({'status': 'healthy'}), 200


# ============================================================================
# Cron Job Endpoints (called by external scheduler)
# ============================================================================

@main_bp.route('/cron/check-new-games')
def cron_check_new_games():
    """
    Cron endpoint to check for new games needing umpires.

    Protected by CRON_SECRET token. Call with ?token=YOUR_SECRET

    Set up an external cron service (cron-job.org, etc.) to hit this every 2 hours:
    https://your-app.railway.app/cron/check-new-games?token=YOUR_CRON_SECRET
    """
    import os
    from datetime import datetime, timedelta
    from app.models.league import League
    from app.services.notification_service import GmailService

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    # Get parameters
    hours = request.args.get('hours', 2, type=int)
    recipient = request.args.get('recipient', 'sdll.umpires@gmail.com')

    # Find games added in the last N hours that need umpires
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    recent_games = Game.query.filter(
        Game.date_added >= cutoff,
        Game.active == 1,
        Game.game_type != 'practice'
    ).all()

    games_needing_umpires = []
    for game in recent_games:
        league = League.get_by_name(game.league)
        if league and league.needs_umpires:
            games_needing_umpires.append((game, league))

    if not games_needing_umpires:
        return jsonify({
            'status': 'ok',
            'message': 'No new games needing umpires',
            'games_checked': len(recent_games),
            'hours': hours
        }), 200

    # Send alert email
    gmail = GmailService()
    if not gmail.is_configured:
        return jsonify({'error': 'Email service not configured'}), 500

    # Group by league
    by_league = {}
    for game, league in games_needing_umpires:
        league_name = league.display_name
        if league_name not in by_league:
            by_league[league_name] = []
        by_league[league_name].append(game)

    count = len(games_needing_umpires)
    subject = f"SDLL Alert: {count} new game(s) added needing umpires"

    # Build email body
    body_lines = [f"{count} game(s) added in the last {hours} hour(s) for leagues requiring umpires:", ""]
    for league_name, games in sorted(by_league.items()):
        body_lines.append(f"{league_name} ({len(games)} game(s)):")
        for game in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            body_lines.append(f"  - {game_date}")
        body_lines.append("")
    body_lines.extend(["Please review and ensure umpire assignments are in place.", "", "- SDLL Automated Alert"])
    body_text = '\n'.join(body_lines)

    # HTML version
    html_parts = [
        '<!DOCTYPE html><html><body style="font-family: Arial, sans-serif; color: #333;">',
        f'<h2 style="color: #228B22;">{count} New Game(s) Need Umpires</h2>',
        f'<p>Added in the last {hours} hour(s):</p>'
    ]
    for league_name, games in sorted(by_league.items()):
        html_parts.append(f'<h3 style="color: #FF8C00;">{league_name}</h3><ul>')
        for game in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            html_parts.append(f'<li>{game_date}</li>')
        html_parts.append('</ul>')
    html_parts.append('<p>Please review and ensure umpire assignments are in place.</p>')
    html_parts.append('<hr><p style="color: #888; font-size: 12px;">SDLL Automated Alert</p></body></html>')
    body_html = '\n'.join(html_parts)

    try:
        gmail.send_email(recipient, subject, body_text, body_html)
        return jsonify({
            'status': 'ok',
            'message': f'Alert sent for {count} games',
            'games': count,
            'recipient': recipient
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500


@main_bp.route('/cron/unassigned-umpires')
def cron_unassigned_umpires():
    """
    Cron endpoint to check for upcoming games needing umpires but without assignments.

    Finds games that:
    - Are in leagues requiring umpires (umpire_count > 0)
    - Don't have umpire_override set (no delegation decision made)
    - Don't have umpire_count_override = 0 (not flagged as no-umpires)
    - Are scheduled and upcoming (within next N days)
    - Don't have umpire assignments yet

    Call with ?token=YOUR_SECRET&days=7
    """
    import os
    from datetime import datetime, timedelta
    from app.models.league import League
    from app.models.game_umpire import GameUmpire
    from app.services.notification_service import GmailService

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    # Get parameters
    days = request.args.get('days', 7, type=int)
    recipient = request.args.get('recipient', 'sdll.umpires@gmail.com')

    # Find upcoming games in date range
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)

    upcoming_games = Game.query.filter(
        Game.game_date >= now,
        Game.game_date <= cutoff,
        Game.active == 1,
        Game.status == 'scheduled',
        Game.game_type != 'practice'
    ).all()

    # Filter to games needing umpires but missing assignments
    games_needing_umpires = []

    for game in upcoming_games:
        # Skip scrimmages
        if game.is_scrimmage:
            continue

        # Skip if explicitly marked as no umpires needed
        if game.umpire_count_override == 0:
            continue

        # Get league to check if it needs umpires
        league = League.get_by_name(game.league)
        if not league or not league.needs_umpires:
            continue

        # Skip if umpire_override is already set (delegation decision made)
        if game.umpire_override:
            continue

        # Check if game has any active umpire assignments
        active_assignments = GameUmpire.query.filter(
            GameUmpire.game_id == game.ID,
            GameUmpire.status.notin_(['cancelled'])
        ).count()

        # Get required umpire count
        required_count = game.umpire_count

        # If no assignments or fewer than required, add to list
        if active_assignments < required_count:
            games_needing_umpires.append((game, league, required_count, active_assignments))

    if not games_needing_umpires:
        return jsonify({
            'status': 'ok',
            'message': 'All upcoming games have umpire assignments',
            'games_checked': len(upcoming_games),
            'days': days
        }), 200

    # Send alert email
    gmail = GmailService()
    if not gmail.is_configured:
        return jsonify({'error': 'Email service not configured'}), 500

    # Group by league
    by_league = {}
    for game, league, required, assigned in games_needing_umpires:
        league_name = league.display_name
        if league_name not in by_league:
            by_league[league_name] = []
        by_league[league_name].append((game, required, assigned))

    count = len(games_needing_umpires)
    subject = f"SDLL Alert: {count} game(s) need umpire assignments"

    # Build email body
    body_lines = [f"{count} upcoming game(s) in the next {days} days need umpire assignments:", ""]
    for league_name, games in sorted(by_league.items()):
        body_lines.append(f"{league_name} ({len(games)} game(s)):")
        for game, required, assigned in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            body_lines.append(f"  - {game_date} (need {required}, have {assigned})")
        body_lines.append("")
    body_lines.extend(["Please assign umpires or delegate to a partner.", "", "- SDLL Automated Alert"])
    body_text = '\n'.join(body_lines)

    # HTML version
    html_parts = [
        '<!DOCTYPE html><html><body style="font-family: Arial, sans-serif; color: #333;">',
        f'<h2 style="color: #c33;">{count} Game(s) Need Umpire Assignments</h2>',
        f'<p>The following games in the next {days} days need umpires:</p>'
    ]
    for league_name, games in sorted(by_league.items()):
        html_parts.append(f'<h3 style="color: #FF8C00;">{league_name}</h3><ul>')
        for game, required, assigned in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            html_parts.append(f'<li>{game_date} <span style="color: #c33;">(need {required}, have {assigned})</span></li>')
        html_parts.append('</ul>')
    html_parts.append('<p>Please assign umpires or delegate to a partner.</p>')
    html_parts.append('<hr><p style="color: #888; font-size: 12px;">SDLL Automated Alert</p></body></html>')
    body_html = '\n'.join(html_parts)

    try:
        gmail.send_email(recipient, subject, body_text, body_html)
        return jsonify({
            'status': 'ok',
            'message': f'Alert sent for {count} games',
            'games': count,
            'recipient': recipient
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500


@main_bp.route('/cron/diagnose-email')
def cron_diagnose_email():
    """
    Diagnostic endpoint to debug email configuration.

    Call with ?token=YOUR_CRON_SECRET to check Resend setup.
    """
    import os
    import json
    import urllib.request
    import urllib.error

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    diagnostics = {
        'environment': {},
        'resend_domains': None,
        'resend_api_keys': None,
        'test_send': None
    }

    # Check environment variables
    resend_key = os.environ.get('RESEND_API_KEY')
    gmail_sender = os.environ.get('GMAIL_SENDER', 'umpires@sdll.org')
    gmail_sender_name = os.environ.get('GMAIL_SENDER_NAME', 'SDLL Umpires')

    diagnostics['environment'] = {
        'RESEND_API_KEY': f"{'set' if resend_key else 'NOT SET'} ({len(resend_key) if resend_key else 0} chars)",
        'GMAIL_SENDER': gmail_sender,
        'GMAIL_SENDER_NAME': gmail_sender_name,
        'from_address_would_be': f"{gmail_sender_name} <{gmail_sender}>"
    }

    if not resend_key:
        diagnostics['error'] = 'RESEND_API_KEY not set'
        return jsonify(diagnostics), 500

    # Query Resend API for domains
    try:
        req = urllib.request.Request(
            'https://api.resend.com/domains',
            headers={
                'Authorization': f'Bearer {resend_key}',
                'Content-Type': 'application/json'
            },
            method='GET'
        )
        with urllib.request.urlopen(req) as response:
            domains_data = json.loads(response.read().decode('utf-8'))
            diagnostics['resend_domains'] = domains_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        diagnostics['resend_domains'] = {'error': f'{e.code}: {error_body}'}
    except Exception as e:
        diagnostics['resend_domains'] = {'error': str(e)}

    # Query Resend API for API keys info
    try:
        req = urllib.request.Request(
            'https://api.resend.com/api-keys',
            headers={
                'Authorization': f'Bearer {resend_key}',
                'Content-Type': 'application/json'
            },
            method='GET'
        )
        with urllib.request.urlopen(req) as response:
            keys_data = json.loads(response.read().decode('utf-8'))
            diagnostics['resend_api_keys'] = keys_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        diagnostics['resend_api_keys'] = {'error': f'{e.code}: {error_body}'}
    except Exception as e:
        diagnostics['resend_api_keys'] = {'error': str(e)}

    # Optional: Try test send if requested
    test_to = request.args.get('test_to')
    if test_to:
        try:
            from_address = f"{gmail_sender_name} <{gmail_sender}>"
            payload = {
                "from": from_address,
                "to": [test_to],
                "subject": "SDLL Email Test",
                "text": "This is a test email from the SDLL diagnostic endpoint."
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                'https://api.resend.com/emails',
                data=data,
                headers={
                    'Authorization': f'Bearer {resend_key}',
                    'Content-Type': 'application/json'
                },
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                diagnostics['test_send'] = {'success': True, 'result': result}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            diagnostics['test_send'] = {'success': False, 'error': f'{e.code}: {error_body}'}
        except Exception as e:
            diagnostics['test_send'] = {'success': False, 'error': str(e)}

    return jsonify(diagnostics), 200


@main_bp.route('/')
def index():
    """Home page - redirect to dashboard if logged in"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard view"""
    # Get upcoming games
    upcoming_games = Game.get_upcoming(limit=10)

    # Format game leagues for display
    for game in upcoming_games:
        game.league_display = game.league.upper() if game.league else 'TBD'

    # Get season summary
    seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring,
        db.func.count(TeamSeason.team_ID).label('team_count')
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).order_by(
        TeamSeason.year.desc(),
        TeamSeason.is_spring.desc()
    ).all()

    # Format seasons for display
    season_data = []
    for year, is_spring, team_count in seasons:
        season_name = 'Spring' if is_spring else 'Fall'
        season_data.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{season_name} {year}',
            'team_count': team_count
        })

    return render_template(
        'main/dashboard.html',
        upcoming_games=upcoming_games,
        seasons=season_data
    )


@main_bp.route('/privacy')
def privacy():
    """Public privacy policy page - no authentication required."""
    return render_template('public/privacy.html')


# ============================================================================
# Admin Error Management Routes
# ============================================================================

@main_bp.route('/admin/errors')
@login_required
@admin_required
def error_list():
    """View list of application errors."""
    from app.models.app_error import AppError

    tier = request.args.get('tier', type=int)
    resolved = request.args.get('resolved', 'false') == 'true'

    query = AppError.query

    if tier is not None:
        query = query.filter_by(tier=tier)

    query = query.filter_by(resolved=resolved)

    errors = query.order_by(AppError.created_at.desc()).limit(200).all()

    # Get summary counts
    counts = AppError.get_recent_counts(hours=24)

    return render_template(
        'admin/errors.html',
        errors=errors,
        counts=counts,
        filter_tier=tier,
        show_resolved=resolved
    )


@main_bp.route('/admin/errors/<int:error_id>')
@login_required
@admin_required
def error_detail(error_id):
    """View details of a specific error."""
    from app.models.app_error import AppError

    error = AppError.query.get_or_404(error_id)
    return render_template('admin/error_detail.html', error=error)


@main_bp.route('/admin/errors/<int:error_id>/resolve', methods=['POST'])
@login_required
@admin_required
def resolve_error(error_id):
    """Mark an error as resolved."""
    from app.models.app_error import AppError

    AppError.mark_resolved(error_id, current_user.id)
    flash('Error marked as resolved.', 'success')

    return redirect(request.referrer or url_for('main.error_list'))


@main_bp.route('/admin/errors/digest')
@login_required
@admin_required
def error_digest():
    """View error digest summary."""
    from app.models.app_error import AppError

    hours = request.args.get('hours', 24, type=int)
    summary = AppError.get_digest_summary(since_hours=hours)

    return render_template(
        'admin/error_digest.html',
        summary=summary,
        hours=hours
    )


@main_bp.route('/admin/test-error')
@login_required
@admin_required
def test_error():
    """
    Intentionally raise an error for testing the error diagnosis system.

    This creates a Tier I error that will be:
    1. Logged to sdll_app_errors table
    2. Sent as Telegram alert
    3. Exported by poll_errors.py for diagnosis

    Usage: Visit /admin/test-error while logged in as admin
    """
    # Raise a deliberate error with a recognizable message
    raise ValueError("TEST ERROR: This is a deliberate test error for the error diagnosis system. Error ID: test-" + str(int(__import__('time').time())))
