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
