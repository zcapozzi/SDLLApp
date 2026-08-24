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
