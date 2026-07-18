"""Main routes - dashboard and home"""

from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models.game import Game
from app.models.team import TeamSeason
from app.extensions import db

main_bp = Blueprint('main', __name__)


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
