"""Game management routes"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.game import Game
from app.models.field import Field
from app.extensions import db
from app.utils.logging import SDLLLogger

games_bp = Blueprint('games', __name__)
logger = SDLLLogger('games')


@games_bp.route('/')
@login_required
def index():
    """List games with filtering"""
    # Get filter parameters
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)
    league = request.args.get('league')
    status = request.args.get('status')
    game_mode = request.args.get('game_mode', 'games')  # 'all', 'games', 'practices'

    # Build query
    query = Game.query.filter(Game.active == 1)

    if year:
        query = query.filter(Game.year == year)
    if is_spring is not None:
        query = query.filter(Game.is_spring == is_spring)
    if league:
        query = query.filter(Game.league == league)
    if status:
        query = query.filter(Game.status == status)

    # Filter by game mode (games/scrimmages vs practices)
    if game_mode == 'games':
        # Games and scrimmages have two teams (away_ID is not null)
        query = query.filter(Game.away_ID.isnot(None))
    elif game_mode == 'practices':
        # Practices have only one team (away_ID is null)
        query = query.filter(Game.away_ID.is_(None))
    # 'all' shows everything

    games = query.order_by(Game.game_date.desc()).limit(100).all()

    # Get filter options
    leagues = db.session.query(Game.league).distinct().filter(
        Game.league.isnot(None)
    ).all()
    leagues = [l[0] for l in leagues if l[0]]

    years = db.session.query(Game.year).distinct().filter(
        Game.year.isnot(None)
    ).order_by(Game.year.desc()).all()
    years = [y[0] for y in years]

    return render_template(
        'games/index.html',
        games=games,
        leagues=leagues,
        years=years,
        current_filters={
            'year': year,
            'is_spring': is_spring,
            'league': league,
            'status': status,
            'game_mode': game_mode
        }
    )


@games_bp.route('/<int:game_id>')
@login_required
def view(game_id):
    """View a single game"""
    game = Game.query.get_or_404(game_id)
    return render_template('games/view.html', game=game)


@games_bp.route('/upcoming')
@login_required
def upcoming():
    """View upcoming games"""
    games = Game.get_upcoming(limit=50)
    return render_template('games/upcoming.html', games=games)
