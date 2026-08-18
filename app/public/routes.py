"""Public routes for team schedules (no authentication required)."""

from flask import render_template, abort
from datetime import datetime, date
from app.public import public_bp
from app.models.team import TeamSeason
from app.models.game import Game
from app.extensions import db


@public_bp.route('/<token>')
def team_schedule(token):
    """Public team schedule view.

    URL format: /s/<token>
    Example: /s/abc123xyz

    Shows:
    - Team name and league
    - Next upcoming game (highlighted)
    - Full schedule of games and practices
    """
    # Look up team by token
    team = TeamSeason.get_by_schedule_token(token)
    if not team:
        abort(404)

    # Get today's date for determining "next game"
    today = date.today()
    now = datetime.now()

    # Get all games for this team (home or away)
    games = Game.query.filter(
        Game.active == 1,
        Game.year == team.year,
        Game.is_spring == team.is_spring,
        db.or_(Game.home_ID == team.team_ID, Game.away_ID == team.team_ID)
    ).order_by(Game.game_date).all()

    # Separate into upcoming and past
    upcoming_games = []
    past_games = []
    next_game = None

    for game in games:
        if game.game_date:
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            if game_date >= today:
                upcoming_games.append(game)
                # First upcoming game is the "next game"
                if next_game is None and game.status == 'scheduled':
                    next_game = game
            else:
                past_games.append(game)

    # Season info
    season_name = f'{"Spring" if team.is_spring else "Fall"} {team.year}'

    return render_template(
        'public/team_schedule.html',
        team=team,
        season_name=season_name,
        next_game=next_game,
        upcoming_games=upcoming_games,
        past_games=past_games,
        today=today
    )
