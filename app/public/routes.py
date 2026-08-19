"""Public routes for team schedules (no authentication required)."""

from flask import render_template, abort
from flask_login import current_user
from datetime import datetime, date
from app.public import public_bp
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league_season import LeagueSeason
from app.models.schedule_proposal import ScheduleProposal
from app.models.field import Field
from app.extensions import db


def _build_game_object_from_proposal(game_data, team, all_teams_by_id, fields_by_name):
    """Convert proposal game data dict into an object-like dict for template.

    Returns a dict that matches the Game model's attributes for template rendering.
    """
    from datetime import datetime

    # Parse game_date
    game_date = None
    if game_data.get('game_date'):
        try:
            game_date = datetime.fromisoformat(game_data['game_date'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    # Get home/away teams
    home_team = all_teams_by_id.get(game_data.get('home_id'))
    away_team = all_teams_by_id.get(game_data.get('away_id'))

    # Build game-like object
    return {
        'ID': game_data.get('id'),
        'game_date': game_date,
        'location': game_data.get('field_name'),
        'game_type': game_data.get('game_type', 'regular'),
        'status': 'scheduled',
        'home_ID': game_data.get('home_id'),
        'away_ID': game_data.get('away_id'),
        'home_team': home_team,
        'away_team': away_team,
        'is_scrimmage': game_data.get('is_scrimmage', False),
        'is_league_practice': game_data.get('is_league_practice', False),
        'is_proposal': True  # Mark as from proposal, not saved
    }


class ProposalGameWrapper:
    """Wrapper to make proposal game dicts behave like Game objects in templates."""

    def __init__(self, game_dict):
        self._data = game_dict

    def __getattr__(self, name):
        return self._data.get(name)


@public_bp.route('/<token>')
def team_schedule(token):
    """Public team schedule view.

    URL format: /s/<token>
    Example: /s/abc123xyz

    Shows:
    - Team name and league
    - Next upcoming game (highlighted)
    - Full schedule of games and practices

    If schedule is not locked:
    - Admins see proposed schedule (if available)
    - Non-admins see "schedule not released" message
    """
    # Look up team by token
    team = TeamSeason.get_by_schedule_token(token)
    if not team:
        abort(404)

    # Get today's date for determining "next game"
    today = date.today()
    now = datetime.now()

    # Season info
    season_name = f'{"Spring" if team.is_spring else "Fall"} {team.year}'

    # Check if schedule is locked
    is_locked = LeagueSeason.is_season_locked(team.year, team.is_spring)

    # Check if user can see proposed schedule
    can_see_proposal = (
        current_user.is_authenticated and
        current_user.can_edit_schedule()
    )

    # If schedule is not locked, check for proposal
    if not is_locked:
        proposal = ScheduleProposal.get_for_season(team.year, team.is_spring)

        if proposal and not can_see_proposal:
            # Non-admin viewing unreleased schedule
            return render_template(
                'public/team_schedule.html',
                team=team,
                season_name=season_name,
                schedule_not_released=True,
                next_game=None,
                upcoming_games=[],
                past_games=[],
                today=today
            )

        if proposal and can_see_proposal:
            # Admin viewing proposed schedule
            # Build lookup tables for teams and fields
            all_teams = TeamSeason.query.filter_by(
                year=team.year,
                is_spring=team.is_spring,
                active=1
            ).all()
            all_teams_by_id = {t.team_ID: t for t in all_teams}

            fields = Field.query.filter_by(active=1).all()
            fields_by_name = {f.location_title: f for f in fields}

            # Filter proposal games for this team
            proposal_games = []
            for game_data in proposal.games:
                home_id = game_data.get('home_id')
                away_id = game_data.get('away_id')
                if home_id == team.team_ID or away_id == team.team_ID:
                    game_obj = _build_game_object_from_proposal(
                        game_data, team, all_teams_by_id, fields_by_name
                    )
                    proposal_games.append(ProposalGameWrapper(game_obj))

            # Sort by date
            proposal_games.sort(key=lambda g: g.game_date or datetime.max)

            # Separate into upcoming and past
            upcoming_games = []
            past_games = []
            next_game = None

            for game in proposal_games:
                if game.game_date:
                    game_date_only = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
                    if game_date_only >= today:
                        upcoming_games.append(game)
                        # First upcoming game is the "next game"
                        if next_game is None:
                            next_game = game
                    else:
                        past_games.append(game)

            return render_template(
                'public/team_schedule.html',
                team=team,
                season_name=season_name,
                next_game=next_game,
                upcoming_games=upcoming_games,
                past_games=past_games,
                today=today,
                is_proposal=True  # Flag for template to show "Proposed" badge
            )

    # Default: Show saved games (locked schedule or no proposal)
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

    return render_template(
        'public/team_schedule.html',
        team=team,
        season_name=season_name,
        next_game=next_game,
        upcoming_games=upcoming_games,
        past_games=past_games,
        today=today
    )
