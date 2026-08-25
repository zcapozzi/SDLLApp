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
    from sqlalchemy.orm import joinedload
    from app.models.league import League
    from app.models.game_umpire import GameUmpire
    from app.models.field_slot import FieldSlot
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

    # Find upcoming games in date range with eager loading
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)

    upcoming_games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.game_date >= now,
        Game.game_date <= cutoff,
        Game.active == 1,
        Game.status == 'scheduled',
        Game.game_type != 'practice'
    ).all()

    # Pre-load field slots for the season to check ownership
    if upcoming_games:
        sample_game = upcoming_games[0]
        field_slots = FieldSlot.query.filter_by(
            year=sample_game.year,
            is_spring=1 if sample_game.is_spring else 0,
            active=1
        ).all()
        # Build lookup: (field_id, day_of_week, hour, minute) -> is_owned
        slot_ownership = {}
        for slot in field_slots:
            key = (slot.field_ID, slot.day_of_week, slot.start_time.hour, slot.start_time.minute)
            slot_ownership[key] = slot.is_owned
    else:
        slot_ownership = {}

    def is_slot_sdll_owned(game):
        """Check if the game's time slot is SDLL-owned."""
        if not game.game_date or not game.field_id:
            return True  # Assume owned if we can't determine
        day_of_week = game.game_date.weekday()
        hour = game.game_date.hour
        minute = game.game_date.minute
        key = (game.field_id, day_of_week, hour, minute)
        return slot_ownership.get(key, 1) == 1

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
            is_owned = is_slot_sdll_owned(game)
            games_needing_umpires.append((game, league, required_count, active_assignments, is_owned))

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
    for game, league, required, assigned, is_owned in games_needing_umpires:
        league_name = league.display_name
        if league_name not in by_league:
            by_league[league_name] = []
        by_league[league_name].append((game, required, assigned, is_owned))

    count = len(games_needing_umpires)
    owned_count = sum(1 for _, _, _, _, is_owned in games_needing_umpires if is_owned)
    away_count = count - owned_count
    subject = f"SDLL Alert: {count} game(s) need umpire assignments"
    if away_count > 0:
        subject += f" ({away_count} away-only)"

    # Base URL for links
    base_url = os.environ.get('APP_URL', 'https://www.southdurhamlittleleague.org')

    # Build email body
    body_lines = [f"{count} upcoming game(s) in the next {days} days need umpire assignments:", ""]
    if away_count > 0:
        body_lines.append(f"Note: {away_count} game(s) are in AWAY-ONLY slots and may not require SDLL umpires.")
        body_lines.append("")
    for league_name, games in sorted(by_league.items()):
        body_lines.append(f"{league_name} ({len(games)} game(s)):")
        for game, required, assigned, is_owned in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            field = game.field_rel.location_title if game.field_rel else (game.location or 'TBD')
            home = game.home_team.display_name if game.home_team else 'TBD'
            away = game.away_team.display_name if game.away_team else 'TBD'
            owned_tag = "" if is_owned else " [AWAY-ONLY SLOT]"
            body_lines.append(f"  - {game_date} @ {field}{owned_tag}")
            body_lines.append(f"    {away} vs {home} (need {required}, have {assigned})")
        body_lines.append("")
    body_lines.extend(["Please assign umpires or delegate to a partner.", "", "- SDLL Automated Alert"])
    body_text = '\n'.join(body_lines)

    # HTML version
    html_parts = [
        '<!DOCTYPE html><html><body style="font-family: Arial, sans-serif; color: #333;">',
        f'<h2 style="color: #c33;">{count} Game(s) Need Umpire Assignments</h2>',
        f'<p>The following games in the next {days} days need umpires:</p>'
    ]
    if away_count > 0:
        html_parts.append(
            f'<p style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">'
            f'<strong>Note:</strong> {away_count} game(s) are in <strong>AWAY-ONLY</strong> slots '
            f'and may not require SDLL umpires. These are marked with a yellow badge below.</p>'
        )
    for league_name, games in sorted(by_league.items()):
        html_parts.append(f'<h3 style="color: #FF8C00; margin-bottom: 8px;">{league_name}</h3>')
        html_parts.append('<table style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
        for game, required, assigned, is_owned in games:
            game_date = game.game_date.strftime('%a, %b %d') if game.game_date else 'TBD'
            game_time = game.game_date.strftime('%I:%M %p').lstrip('0') if game.game_date else ''
            field = game.field_rel.location_title if game.field_rel else (game.location or 'TBD')
            home = game.home_team.display_name if game.home_team else 'TBD'
            away = game.away_team.display_name if game.away_team else 'TBD'

            # Build links
            calendar_date = game.game_date.strftime('%Y-%m-%d') if game.game_date else ''
            calendar_url = f"{base_url}/umpires/{game.year}/{1 if game.is_spring else 0}/calendar?week={calendar_date}"

            # Slot ownership badge
            if is_owned:
                owned_badge = ''
            else:
                owned_badge = '<span style="background: #ffc107; color: #000; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 8px;">AWAY-ONLY</span>'

            html_parts.append(
                f'<tr style="border-bottom: 1px solid #eee;">'
                f'<td style="padding: 8px 0;">'
                f'<strong>{game_date}</strong> {game_time} @ {field}{owned_badge}<br>'
                f'<span style="color: #555;">{away} vs {home}</span><br>'
                f'<span style="color: #c33; font-size: 12px;">Need {required}, have {assigned}</span>'
                f'</td>'
                f'<td style="padding: 8px; text-align: right; vertical-align: top;">'
                f'<a href="{calendar_url}" style="color: #1976d2; text-decoration: none; font-size: 13px;">View in Calendar</a>'
                f'</td>'
                f'</tr>'
            )
        html_parts.append('</table>')
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

    # Show first 8 chars of key to verify which key is loaded
    key_prefix = resend_key[:8] if resend_key else 'N/A'
    key_suffix = resend_key[-4:] if resend_key else 'N/A'
    # Check for hidden characters
    key_repr = repr(resend_key) if resend_key else 'N/A'
    has_whitespace = any(c in resend_key for c in [' ', '\t', '\n', '\r']) if resend_key else False

    diagnostics['environment'] = {
        'RESEND_API_KEY': f"{'set' if resend_key else 'NOT SET'} ({len(resend_key) if resend_key else 0} chars, starts: {key_prefix}..., ends: ...{key_suffix})",
        'RESEND_API_KEY_has_whitespace': has_whitespace,
        'RESEND_API_KEY_repr_length': len(key_repr) if resend_key else 0,
        'GMAIL_SENDER': gmail_sender,
        'GMAIL_SENDER_NAME': gmail_sender_name,
        'from_address_would_be': f"{gmail_sender_name} <{gmail_sender}>"
    }

    if not resend_key:
        diagnostics['error'] = 'RESEND_API_KEY not set'
        return jsonify(diagnostics), 500

    # Strip whitespace from key just in case
    clean_key = resend_key.strip() if resend_key else ''

    # Test with a simple curl-like request to see raw response
    import socket
    diagnostics['railway_ip'] = None
    try:
        diagnostics['railway_ip'] = socket.gethostbyname(socket.gethostname())
    except:
        pass

    # Query Resend API for domains
    try:
        req = urllib.request.Request(
            'https://api.resend.com/domains',
            headers={
                'Authorization': f'Bearer {clean_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'SDLL-App/1.0'
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
                'Authorization': f'Bearer {clean_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'SDLL-App/1.0'
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
                    'Authorization': f'Bearer {clean_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'SDLL-App/1.0'
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
    # Check if user has access to full dashboard
    has_full_access = (
        current_user.can_edit_schedule() or
        current_user.is_umpire() or
        current_user.can_manage_umpires()
    )

    if not has_full_access:
        # Show placeholder page for regular users
        return render_template('main/placeholder.html')

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


@main_bp.route('/contact', methods=['POST'])
@login_required
def contact():
    """Handle contact form submission from placeholder page."""
    from app.services.notification_service import GmailService

    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()

    if not subject or not message:
        flash('Please fill in both subject and message.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get user info
    user_name = current_user.name or 'Unknown'
    user_email = current_user.email or 'Unknown'

    # Build email
    email_subject = f"[SDLL Feedback] {subject}"
    email_body = f"""Message from: {user_name}
Email: {user_email}

Subject: {subject}

Message:
{message}
"""

    gmail = GmailService()
    if not gmail.is_configured:
        flash('Email service is not configured. Please try again later.', 'error')
        return redirect(url_for('main.dashboard'))

    try:
        gmail.send_email(
            to='umpires@sdll.org',
            subject=email_subject,
            body_text=email_body,
            reply_to=user_email
        )
        flash('Thank you! Your message has been sent.', 'success')
    except Exception as e:
        flash(f'Failed to send message. Please try again later.', 'error')
        print(f"Contact form error: {e}")

    return redirect(url_for('main.dashboard'))


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


@main_bp.route('/cron/process-scheduled-emails')
def cron_process_scheduled_emails():
    """
    Cron endpoint to process scheduled emails.

    Runs every 5 minutes. Each email is attempted exactly once.
    Protected by CRON_SECRET token. Call with ?token=YOUR_SECRET

    Set up an external cron service (cron-job.org, etc.) to hit this every 5 minutes:
    https://your-app.railway.app/cron/process-scheduled-emails?token=YOUR_CRON_SECRET
    """
    import os
    from app.services.email_blast_service import process_pending_emails

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    # Process pending emails
    try:
        results = process_pending_emails()

        return jsonify({
            'status': 'ok',
            'processed': len(results),
            'results': results
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@main_bp.route('/cron/generate-weekly-digests')
def cron_generate_weekly_digests():
    """
    Cron endpoint to generate weekly umpire partner digest emails.

    Runs Sunday 6pm ET (23:00 UTC). Generates digest drafts for all partners
    with games in the upcoming week. Partners with auto_send_digest=True
    will have their digests sent immediately.

    Protected by CRON_SECRET token. Call with ?token=YOUR_SECRET

    Set up an external cron service to hit this on Sundays at 6pm ET:
    https://your-app.railway.app/cron/generate-weekly-digests?token=YOUR_CRON_SECRET
    """
    import os
    from app.services.weekly_digest_service import WeeklyDigestService

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    try:
        service = WeeklyDigestService()
        digests = service.generate_all_digests()

        results = {
            'total': len(digests),
            'drafts': sum(1 for d in digests if d.status == 'draft'),
            'sent': sum(1 for d in digests if d.status == 'sent'),
            'skipped': sum(1 for d in digests if d.status == 'skipped'),
            'partners': [d.partner_code for d in digests]
        }

        return jsonify({
            'status': 'ok',
            'results': results
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@main_bp.route('/cron/digest-reminders')
def cron_digest_reminders():
    """
    Cron endpoint to send reminders about pending umpire digest emails.

    Runs Monday 8am ET (13:00 UTC). Sends reminder to admins if any
    digests are still in draft status and haven't been sent.

    Protected by CRON_SECRET token. Call with ?token=YOUR_SECRET

    Set up an external cron service to hit this on Mondays at 8am ET:
    https://your-app.railway.app/cron/digest-reminders?token=YOUR_CRON_SECRET
    """
    import os
    from app.models.weekly_digest import WeeklyDigest
    from app.services.weekly_digest_service import WeeklyDigestService

    # Verify secret token
    expected_token = os.environ.get('CRON_SECRET')
    provided_token = request.args.get('token')

    if not expected_token:
        return jsonify({'error': 'CRON_SECRET not configured'}), 500

    if provided_token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403

    try:
        # Get pending digests that haven't had reminders sent
        pending = WeeklyDigest.get_pending_reminders()

        if not pending:
            return jsonify({
                'status': 'ok',
                'message': 'No pending digests requiring reminders',
                'count': 0
            }), 200

        # Send reminder
        service = WeeklyDigestService()
        success = service.send_reminder_to_admins(pending)

        return jsonify({
            'status': 'ok',
            'reminder_sent': success,
            'pending_count': len(pending),
            'partners': [d.partner_code for d in pending]
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
