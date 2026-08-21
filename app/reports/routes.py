"""Report routes for viewing game changes and audit history"""

from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.reports import reports_bp
from app.models.game_change import GameChange
from app.models.game import Game
from app.models.user import User
from app.models.umpire_assignment import UmpireAssignment
from app.extensions import db


@reports_bp.route('/')
@login_required
def index():
    """Reports index page"""
    return render_template('reports/index.html')


@reports_bp.route('/recent-changes')
@login_required
def recent_changes():
    """View recent game changes with filters"""
    # Get filter parameters
    days = request.args.get('days', 7, type=int)
    league = request.args.get('league')
    change_type = request.args.get('change_type')
    changed_by = request.args.get('changed_by', type=int)

    # Build query
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = GameChange.query.filter(GameChange.changed_at >= cutoff)

    if league:
        query = query.filter(GameChange.league == league)
    if change_type:
        query = query.filter(GameChange.change_type == change_type)
    if changed_by:
        query = query.filter(GameChange.changed_by == changed_by)

    changes = query.order_by(GameChange.changed_at.desc()).limit(200).all()

    # Get filter options
    leagues = db.session.query(GameChange.league).distinct().filter(
        GameChange.league.isnot(None)
    ).all()
    leagues = sorted([l[0] for l in leagues if l[0]])

    users = User.query.filter(User.role.in_(['admin', 'scheduler'])).all()

    return render_template(
        'reports/recent_changes.html',
        changes=changes,
        leagues=leagues,
        users=users,
        current_filters={
            'days': days,
            'league': league,
            'change_type': change_type,
            'changed_by': changed_by
        }
    )


@reports_bp.route('/game/<int:game_id>/history')
@login_required
def game_history(game_id):
    """View change history for a specific game"""
    game = Game.query.get_or_404(game_id)
    changes = GameChange.get_for_game(game_id)

    # Get team names for display
    home_team_name = 'TBD'
    away_team_name = 'TBD'
    if game.home_ID:
        from app.models.team import TeamSeason
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.scheduler_display_name
    if game.away_ID:
        from app.models.team import TeamSeason
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.scheduler_display_name

    return render_template(
        'reports/game_history.html',
        game=game,
        changes=changes,
        home_team_name=home_team_name,
        away_team_name=away_team_name
    )


@reports_bp.route('/umpire-changes')
@login_required
def umpire_changes():
    """View changes affecting games with umpire assignments"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get filter parameters
    umpire_id = request.args.get('umpire_id', type=int)
    days = request.args.get('days', 7, type=int)

    # Get umpires for filter dropdown
    umpires = User.query.filter(User.role == 'umpire').all()

    if not umpire_id and umpires:
        # Default to first umpire
        umpire_id = umpires[0].user_id

    # Get game IDs assigned to this umpire
    if umpire_id:
        assignments = UmpireAssignment.query.filter_by(umpire_id=umpire_id).all()
        game_ids = [a.game_id for a in assignments]

        # Get changes for those games
        cutoff = datetime.utcnow() - timedelta(days=days)
        changes = GameChange.query.filter(
            GameChange.game_id.in_(game_ids),
            GameChange.changed_at >= cutoff
        ).order_by(GameChange.changed_at.desc()).all()
    else:
        changes = []

    return render_template(
        'reports/umpire_changes.html',
        changes=changes,
        umpires=umpires,
        current_umpire_id=umpire_id,
        days=days
    )


@reports_bp.route('/my-changes')
@login_required
def my_changes():
    """View changes made by the current user"""
    changes = GameChange.get_by_user(current_user.user_id, limit=100)

    return render_template(
        'reports/my_changes.html',
        changes=changes
    )
