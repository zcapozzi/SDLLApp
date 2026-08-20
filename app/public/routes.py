"""Public routes for team schedules (no authentication required)."""

from flask import render_template, abort, request, make_response, jsonify
from flask_login import current_user
from datetime import datetime, date
from app.public import public_bp
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league_season import LeagueSeason
from app.models.schedule_proposal import ScheduleProposal
from app.models.field import Field
from app.models.analytics import PageView, Ad, AdImpression, AdClick, generate_session_id
from app.extensions import db

# Cookie name for anonymous session tracking
SESSION_COOKIE_NAME = 'sdll_session'
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _get_or_create_session_id():
    """Get existing session ID from cookie or create a new one."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        session_id = generate_session_id()
    return session_id


def _set_session_cookie(response, session_id):
    """Set the session cookie on the response."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=request.is_secure
    )


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

    # Get home/away teams - proposal uses home_team_id/away_team_id
    home_team_id = game_data.get('home_team_id')
    away_team_id = game_data.get('away_team_id')
    home_team = all_teams_by_id.get(home_team_id)
    away_team = all_teams_by_id.get(away_team_id)

    # Build game-like object
    return {
        'ID': game_data.get('id'),
        'game_date': game_date,
        'location': game_data.get('field_name'),
        'game_type': game_data.get('game_type', 'regular'),
        'status': 'scheduled',
        'home_ID': home_team_id,
        'away_ID': away_team_id,
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
            # Non-admin viewing unreleased schedule - still track the visit
            session_id = _get_or_create_session_id()
            try:
                PageView.log_view('team_schedule', token, request, session_id)
            except Exception:
                pass

            response = make_response(render_template(
                'public/team_schedule.html',
                team=team,
                season_name=season_name,
                schedule_not_released=True,
                next_game=None,
                upcoming_games=[],
                past_games=[],
                today=today
            ))
            _set_session_cookie(response, session_id)
            return response

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
                home_id = game_data.get('home_team_id')
                away_id = game_data.get('away_team_id')
                if home_id == team.team_ID or away_id == team.team_ID:
                    game_obj = _build_game_object_from_proposal(
                        game_data, team, all_teams_by_id, fields_by_name
                    )
                    proposal_games.append(ProposalGameWrapper(game_obj))

            # Also include division practices from the database
            league_practices = Game.query.filter(
                Game.active == 1,
                Game.year == team.year,
                Game.is_spring == team.is_spring,
                Game.is_league_practice == True,
                Game.home_ID == team.team_ID
            ).all()

            for lp in league_practices:
                lp_obj = {
                    'ID': f'lp_{lp.ID}',
                    'game_date': lp.game_date,
                    'location': lp.location,
                    'game_type': 'practice',
                    'status': 'scheduled',
                    'home_ID': lp.home_ID,
                    'away_ID': None,
                    'home_team': lp.home_team,
                    'away_team': None,
                    'is_scrimmage': False,
                    'is_league_practice': True,
                    'is_proposal': False
                }
                proposal_games.append(ProposalGameWrapper(lp_obj))

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

            # Track page view and get ad (for admin viewing proposal)
            session_id = _get_or_create_session_id()
            page_view = None
            ad = None
            impression = None

            try:
                page_view = PageView.log_view('team_schedule', token, request, session_id)
                ad = Ad.get_active_ad(team.league)
                if ad and page_view:
                    impression = AdImpression.log_impression(
                        ad, page_view, session_id, token,
                        PageView._detect_device_type(request.headers.get('User-Agent', ''))
                    )
            except Exception:
                pass

            response = make_response(render_template(
                'public/team_schedule.html',
                team=team,
                season_name=season_name,
                next_game=next_game,
                upcoming_games=upcoming_games,
                past_games=past_games,
                today=today,
                is_proposal=True,  # Flag for template to show "Proposed" badge
                page_view_id=page_view.ID if page_view else None,
                ad=ad,
                impression_token=impression.impression_token if impression else None
            ))
            _set_session_cookie(response, session_id)
            return response

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

    # Track page view and get ad
    session_id = _get_or_create_session_id()
    page_view = None
    ad = None
    impression = None

    try:
        page_view = PageView.log_view('team_schedule', token, request, session_id)
        ad = Ad.get_active_ad(team.league)
        if ad and page_view:
            impression = AdImpression.log_impression(
                ad, page_view, session_id, token,
                PageView._detect_device_type(request.headers.get('User-Agent', ''))
            )
    except Exception:
        pass  # Don't fail the page if tracking fails

    response = make_response(render_template(
        'public/team_schedule.html',
        team=team,
        season_name=season_name,
        next_game=next_game,
        upcoming_games=upcoming_games,
        past_games=past_games,
        today=today,
        page_view_id=page_view.ID if page_view else None,
        ad=ad,
        impression_token=impression.impression_token if impression else None
    ))
    _set_session_cookie(response, session_id)
    return response


@public_bp.route('/privacy')
def privacy():
    """Privacy policy page."""
    session_id = _get_or_create_session_id()

    try:
        PageView.log_view('privacy', None, request, session_id)
    except Exception:
        pass

    response = make_response(render_template('public/privacy.html'))
    _set_session_cookie(response, session_id)
    return response


@public_bp.route('/beacon', methods=['POST'])
def tracking_beacon():
    """Receive tracking beacon data from JavaScript.

    Updates page view with viewport size and time on page.
    """
    try:
        data = request.get_json() or {}
        page_view_id = data.get('page_view_id')
        viewport_width = data.get('viewport_width')
        viewport_height = data.get('viewport_height')
        time_on_page = data.get('time_on_page')

        if page_view_id:
            PageView.update_from_beacon(
                page_view_id,
                viewport_width,
                viewport_height,
                time_on_page
            )
        return jsonify({'status': 'ok'})
    except Exception:
        return jsonify({'status': 'error'}), 500


@public_bp.route('/ad/viewability', methods=['POST'])
def ad_viewability_beacon():
    """Receive ad viewability beacon data from JavaScript."""
    try:
        data = request.get_json() or {}
        impression_token = data.get('impression_token')
        was_viewable = data.get('was_viewable', False)
        viewable_seconds = data.get('viewable_seconds', 0)
        viewport_width = data.get('viewport_width')

        if impression_token:
            AdImpression.update_viewability(
                impression_token,
                was_viewable,
                viewable_seconds,
                viewport_width
            )
        return jsonify({'status': 'ok'})
    except Exception:
        return jsonify({'status': 'error'}), 500


@public_bp.route('/ad/click/<token>')
def ad_click(token):
    """Handle ad click with validation."""
    session_id = _get_or_create_session_id()

    # Get click data from query params
    ad_id = request.args.get('ad_id', type=int)
    time_to_click = request.args.get('ttc', type=int)
    click_x = request.args.get('x', type=int)
    click_y = request.args.get('y', type=int)

    if not ad_id:
        abort(400)

    # Get the ad
    ad = Ad.query.get(ad_id)
    if not ad:
        abort(404)

    # Log and validate the click
    try:
        AdClick.log_click(
            ad_id=ad_id,
            impression_id=None,  # Will be looked up by token
            click_token=token,
            session_id=session_id,
            time_to_click_ms=time_to_click,
            click_x=click_x,
            click_y=click_y
        )
    except Exception:
        pass  # Don't fail redirect if tracking fails

    # Redirect to ad destination
    if ad.click_url:
        from flask import redirect
        return redirect(ad.click_url)
    else:
        return redirect('/')
