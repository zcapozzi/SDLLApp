"""Public routes for team schedules (no authentication required).

CRITICAL: All tracking code must fail gracefully. Analytics should NEVER
prevent users from seeing their content.

ARCHITECTURE:
1. Prepare ALL core content first (team data, games, etc.)
2. Safely attempt to get ad data (optional, fail silently)
3. Build the complete response
4. Safely attempt to log tracking (optional, fail silently)
5. Return the response regardless of any tracking success/failure
"""

from flask import render_template, abort, request, make_response, jsonify, redirect
from flask_login import current_user
from datetime import datetime, date
from app.public import public_bp
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league_season import LeagueSeason
from app.models.schedule_proposal import ScheduleProposal
from app.models.field import Field
from app.extensions import db
import sys

# Cookie name for anonymous session tracking
SESSION_COOKIE_NAME = 'sdll_session'
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _log_tracking_error(context, error):
    """Log a tracking error to stderr. Never crashes."""
    try:
        print(f"[TRACKING ERROR] {context}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
    except Exception:
        pass


def _safe_rollback():
    """Attempt to rollback the database session. Never crashes."""
    try:
        db.session.rollback()
    except Exception:
        pass


def _get_or_create_session_id():
    """Get existing session ID from cookie or create a new one."""
    try:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            import secrets
            session_id = secrets.token_urlsafe(32)
        return session_id
    except Exception:
        return None


def _set_session_cookie(response, session_id):
    """Set the session cookie on the response. Never crashes."""
    if not session_id:
        return
    try:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=request.is_secure
        )
    except Exception as e:
        _log_tracking_error("set_session_cookie", e)


def _safe_get_ad():
    """
    Safely attempt to get an active ad. Returns None on any failure.
    This is called BEFORE rendering so ads can be included in the response.
    """
    try:
        from app.models.analytics import Ad
        return Ad.get_active_ad()
    except Exception as e:
        _log_tracking_error("get_active_ad", e)
        _safe_rollback()
        return None


def _safe_log_page_view(page_type, page_context, session_id):
    """
    Safely log a page view. Returns page_view or None on failure.
    Called AFTER response is built - failure doesn't affect the page.
    """
    if not session_id:
        return None
    try:
        from app.models.analytics import PageView
        return PageView.log_view(page_type, page_context, request, session_id)
    except Exception as e:
        _log_tracking_error("log_page_view", e)
        _safe_rollback()
        return None


def _safe_log_impression(ad, page_view, session_id, page_context):
    """
    Safely log an ad impression. Returns impression or None on failure.
    Called AFTER response is built - failure doesn't affect the page.
    """
    if not ad or not page_view or not session_id:
        return None
    try:
        from app.models.analytics import AdImpression, PageView as PV
        device_type = PV._detect_device_type(request.headers.get('User-Agent', ''))
        return AdImpression.log_impression(ad, page_view, session_id, page_context, device_type)
    except Exception as e:
        _log_tracking_error("log_impression", e)
        _safe_rollback()
        return None


def _build_game_object_from_proposal(game_data, team, all_teams_by_id, fields_by_name):
    """Convert proposal game data dict into an object-like dict for template."""
    game_date = None
    if game_data.get('game_date'):
        try:
            game_date = datetime.fromisoformat(game_data['game_date'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    home_team_id = game_data.get('home_team_id')
    away_team_id = game_data.get('away_team_id')
    home_team = all_teams_by_id.get(home_team_id)
    away_team = all_teams_by_id.get(away_team_id)

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
        'is_proposal': True
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

    CRITICAL: This page MUST load even if tracking/analytics fails.
    """
    # =========================================================================
    # PHASE 1: PREPARE ALL CORE CONTENT (required data, must succeed)
    # =========================================================================

    # Look up team by token - this is required, 404 if not found
    team = TeamSeason.get_by_schedule_token(token)
    if not team:
        abort(404)

    today = date.today()
    season_name = f'{"Spring" if team.is_spring else "Fall"} {team.year}'
    is_locked = LeagueSeason.is_season_locked(team.year, team.is_spring)

    # Check if user can see proposed schedule
    can_see_proposal = False
    try:
        can_see_proposal = (
            current_user.is_authenticated and
            current_user.can_edit_schedule()
        )
    except Exception:
        pass

    # Prepare session ID for tracking (but don't track yet)
    session_id = _get_or_create_session_id()

    # Initialize template variables
    template_vars = {
        'team': team,
        'season_name': season_name,
        'next_game': None,
        'upcoming_games': [],
        'past_games': [],
        'today': today,
        'page_view_id': None,
        'ad': None,
        'impression_token': None,
    }

    # Determine what games/practices to show
    if not is_locked:
        proposal = ScheduleProposal.get_for_season(team.year, team.is_spring)

        if proposal and not can_see_proposal:
            # Non-admin viewing unreleased schedule
            template_vars['schedule_not_released'] = True

        elif proposal and can_see_proposal:
            # Admin viewing proposed schedule
            template_vars['is_proposal'] = True

            all_teams = TeamSeason.query.filter_by(
                year=team.year,
                is_spring=team.is_spring,
                active=1
            ).all()
            all_teams_by_id = {t.team_ID: t for t in all_teams}

            fields = Field.query.filter_by(active=1).all()
            fields_by_name = {f.location_title: f for f in fields}

            proposal_games = []
            for game_data in proposal.games:
                home_id = game_data.get('home_team_id')
                away_id = game_data.get('away_team_id')
                if home_id == team.team_ID or away_id == team.team_ID:
                    game_obj = _build_game_object_from_proposal(
                        game_data, team, all_teams_by_id, fields_by_name
                    )
                    proposal_games.append(ProposalGameWrapper(game_obj))

            # Include division practices from the database
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

            proposal_games.sort(key=lambda g: g.game_date or datetime.max)

            upcoming_games = []
            past_games = []
            next_game = None

            for game in proposal_games:
                if game.game_date:
                    game_date_only = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
                    if game_date_only >= today:
                        upcoming_games.append(game)
                        if next_game is None:
                            next_game = game
                    else:
                        past_games.append(game)

            template_vars['upcoming_games'] = upcoming_games
            template_vars['past_games'] = past_games
            template_vars['next_game'] = next_game

        elif not proposal:
            pass  # Will show saved games below

    # If locked or no proposal, show saved games
    if is_locked or ('schedule_not_released' not in template_vars and 'is_proposal' not in template_vars):
        games = Game.query.filter(
            Game.active == 1,
            Game.year == team.year,
            Game.is_spring == team.is_spring,
            db.or_(Game.home_ID == team.team_ID, Game.away_ID == team.team_ID)
        ).order_by(Game.game_date).all()

        upcoming_games = []
        past_games = []
        next_game = None

        for game in games:
            if game.game_date:
                game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
                if game_date >= today:
                    upcoming_games.append(game)
                    if next_game is None and game.status == 'scheduled':
                        next_game = game
                else:
                    past_games.append(game)

        template_vars['upcoming_games'] = upcoming_games
        template_vars['past_games'] = past_games
        template_vars['next_game'] = next_game

    # =========================================================================
    # PHASE 2: SAFELY GET AD (optional, fail silently)
    # =========================================================================

    ad = _safe_get_ad()
    template_vars['ad'] = ad

    # =========================================================================
    # PHASE 3: BUILD RESPONSE (core content is ready)
    # =========================================================================

    response = make_response(render_template('public/team_schedule.html', **template_vars))

    # =========================================================================
    # PHASE 4: SAFELY LOG TRACKING (optional, fail silently, AFTER response built)
    # =========================================================================

    try:
        # Log page view
        page_view = _safe_log_page_view('team_schedule', token, session_id)

        # Log ad impression if we have an ad
        impression = None
        if ad and page_view:
            impression = _safe_log_impression(ad, page_view, session_id, token)

        # Set session cookie
        _set_session_cookie(response, session_id)

        # Note: page_view_id and impression_token are already None in the rendered template.
        # The JavaScript tracking will still work for time-on-page via the beacon,
        # it just won't have a page_view_id to send. That's fine - graceful degradation.

    except Exception as e:
        _log_tracking_error("tracking_phase", e)
        _safe_rollback()

    # =========================================================================
    # PHASE 5: RETURN RESPONSE (always succeeds)
    # =========================================================================

    return response


@public_bp.route('/beacon', methods=['POST'])
def tracking_beacon():
    """Receive tracking beacon data from JavaScript.
    Always returns 200 OK - never fail on tracking.
    """
    try:
        from app.models.analytics import PageView
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
    except Exception as e:
        _log_tracking_error("tracking_beacon", e)
        _safe_rollback()

    return jsonify({'status': 'ok'})


@public_bp.route('/ad/viewability', methods=['POST'])
def ad_viewability_beacon():
    """Receive ad viewability beacon data from JavaScript.
    Always returns 200 OK - never fail on tracking.
    """
    try:
        from app.models.analytics import AdImpression
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
    except Exception as e:
        _log_tracking_error("ad_viewability_beacon", e)
        _safe_rollback()

    return jsonify({'status': 'ok'})


@public_bp.route('/ad/click/<token>')
def ad_click(token):
    """Handle ad click with validation.
    Even if tracking fails, still redirect user to destination.
    """
    redirect_url = '/'

    try:
        session_id = _get_or_create_session_id()
        ad_id = request.args.get('ad_id', type=int)
        time_to_click = request.args.get('ttc', type=int)
        click_x = request.args.get('x', type=int)
        click_y = request.args.get('y', type=int)

        from app.models.analytics import Ad, AdClick
        if ad_id:
            ad = Ad.query.get(ad_id)
            if ad:
                redirect_url = ad.click_url or '/'

                try:
                    AdClick.log_click(
                        ad_id=ad_id,
                        impression_id=None,
                        click_token=token,
                        session_id=session_id,
                        time_to_click_ms=time_to_click,
                        click_x=click_x,
                        click_y=click_y
                    )
                except Exception as e:
                    _log_tracking_error("log_ad_click", e)
                    _safe_rollback()
    except Exception as e:
        _log_tracking_error("ad_click", e)
        _safe_rollback()

    return redirect(redirect_url)
