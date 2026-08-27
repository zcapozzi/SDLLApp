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

from flask import render_template, abort, request, make_response, jsonify, redirect, Response, url_for, flash
from flask_login import current_user
from datetime import datetime, date, timedelta
from sqlalchemy.orm import joinedload
from app.public import public_bp
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league_season import LeagueSeason
from app.models.schedule_proposal import ScheduleProposal
from app.models.field import Field
from app.models.umpire_partner import UmpirePartner
from app.models.game_change import GameChange
from app.models.game_start_record import GameStartRecord
from app.extensions import db
import sys
import csv
from io import StringIO

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

    field_name = game_data.get('field_name') or game_data.get('location') or ''

    return {
        'ID': game_data.get('id'),
        'game_date': game_date,
        'location': field_name,
        'field_name': field_name,  # Add field_name for template compatibility
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

    @property
    def directions_url(self):
        """Get Google Maps directions URL for this game's location."""
        location = self._data.get('location')
        if not location:
            return None
        field = Field.get_by_name(location)
        if field:
            return field.google_maps_url
        return None


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

    # Check for testing flag to allow start time recording on non-game days
    allow_start_time_record = request.args.get('allowStartTimeRecord', '0') == '1'

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
        'game_originals': {},  # "Originally scheduled for..." text per game
        'shared_practices': {},  # game_id -> partner team name for shared practices
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
                field_name = lp.field_name or ''  # Use Game.field_name property
                lp_obj = {
                    'ID': f'lp_{lp.ID}',
                    'game_date': lp.game_date,
                    'location': field_name,
                    'field_name': field_name,  # Add field_name for template compatibility
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

        # Get "originally" display text for games that have been changed (batch query)
        from app.models.game_change import GameChange
        all_games = upcoming_games + past_games
        try:
            game_originals = GameChange.get_original_display_batch(all_games)
        except Exception:
            game_originals = {}  # Don't fail if change lookup fails
        template_vars['game_originals'] = game_originals

        # Find shared practices - other teams practicing at same field/time
        shared_practices = {}  # game_id -> partner team display name
        try:
            # Get all practice games for this team
            practice_games = [g for g in all_games if g.game_type == 'practice' and g.field_id and g.game_date]
            if practice_games:
                # For each practice, find other practices at same field/time
                for practice in practice_games:
                    overlapping = Game.query.filter(
                        Game.active == 1,
                        Game.ID != practice.ID,
                        Game.game_type == 'practice',
                        Game.field_id == practice.field_id,
                        Game.game_date == practice.game_date,
                        Game.home_ID != team.team_ID  # Different team
                    ).first()
                    if overlapping and overlapping.home_team:
                        shared_practices[practice.ID] = overlapping.home_team.computed_display_name
        except Exception:
            pass  # Don't fail page load if lookup fails
        template_vars['shared_practices'] = shared_practices

    # =========================================================================
    # PHASE 1.5: GET GAME START RECORDS FOR TODAY'S GAMES
    # =========================================================================

    # Find games eligible for start time recording
    # Normally only today's games, but allowStartTimeRecord=1 enables all upcoming games
    recordable_game_ids = set()
    for game in template_vars.get('upcoming_games', []):
        if game.game_date and game.game_type != 'practice':
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            # Include if it's today, OR if testing flag is set
            if game_date == today or allow_start_time_record:
                # Get the actual game ID (handle both Game objects and wrapper objects)
                game_id = getattr(game, 'ID', None)
                if game_id and isinstance(game_id, int):
                    recordable_game_ids.add(game_id)

    # Get existing start records for user's session/user
    game_start_records = {}
    if recordable_game_ids:
        try:
            user_id = None
            try:
                if current_user.is_authenticated:
                    user_id = current_user.ID
            except Exception:
                pass

            # Batch query for all records by this session or user
            records_query = GameStartRecord.query.filter(
                GameStartRecord.game_id.in_(recordable_game_ids)
            )

            if user_id:
                records_query = records_query.filter(
                    db.or_(
                        GameStartRecord.user_id == user_id,
                        GameStartRecord.session_id == session_id
                    )
                )
            elif session_id:
                records_query = records_query.filter(
                    GameStartRecord.session_id == session_id
                )

            for record in records_query.all():
                game_start_records[record.game_id] = {
                    'start_time': record.start_time.isoformat(),
                    'formatted_time': record.start_time.strftime('%I:%M %p'),
                    'is_own': True
                }
        except Exception as e:
            _log_tracking_error("get_game_start_records", e)

    template_vars['recordable_game_ids'] = list(recordable_game_ids)
    template_vars['game_start_records'] = game_start_records
    template_vars['allow_start_time_record'] = allow_start_time_record

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


@public_bp.route('/partner/<token>')
def partner_schedule(token):
    """Public partner schedule view.

    Shows games assigned to a partner (Diamond, Dynamic, etc.) in a table format.
    """
    from sqlalchemy.orm import joinedload
    from app.models.league import League

    partner = UmpirePartner.get_by_schedule_token(token)
    if not partner:
        abort(404)

    # Get query parameters
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)
    field_filter = request.args.get('field', '')
    league_filter = request.args.get('league', '')
    date_filter = request.args.get('date', '')

    # Default to current/upcoming season
    if year is None:
        current = LeagueSeason.query.filter_by(active=1).order_by(
            LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
        ).first()
        if current:
            year = current.year
            is_spring = 1 if current.is_spring else 0
        else:
            year = date.today().year
            is_spring = 1 if date.today().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Pre-load leagues and fields to avoid N+1 queries
    all_leagues = {l.display_name: l for l in League.get_all_active()}
    all_fields = {f.location_title: f for f in Field.query.filter_by(active=1).all()}

    # Get games with eager loading of relationships (exclude practices)
    partner_code = partner.short_code
    games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == (is_spring == 1),
        Game.umpire_override == partner_code,
        Game.game_type != 'practice'
    ).order_by(Game.game_date).all()

    # Pre-compute values that would otherwise trigger N+1 queries
    # and collect filter options from the SAME query (no duplicate query)
    fields_set = set()
    leagues_set = set()
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    new_game_ids = set()
    has_ntl_games = False

    for g in games:
        # Cache computed values on the game object to avoid repeated lookups
        g._cached_field_name = g.field_name

        # Cache umpire count
        if g.umpire_count_override is not None:
            g._cached_umpire_count = g.umpire_count_override
        else:
            league_obj = all_leagues.get(g.league)
            if league_obj:
                is_playoff = g.game_type == 'playoff'
                g._cached_umpire_count = league_obj.get_umpire_count(is_playoff=is_playoff)
            else:
                g._cached_umpire_count = 1

        # Cache rules URL
        league_obj = all_leagues.get(g.league)
        g._cached_rules_url = league_obj.rules_doc_url if league_obj else None

        # Cache directions URL
        field_obj = all_fields.get(g._cached_field_name) or (g.field_rel if g.field_id else None)
        g._cached_directions_url = field_obj.google_maps_url if field_obj else None

        # Collect filter options
        if g._cached_field_name:
            fields_set.add(g._cached_field_name)
        if g.league:
            leagues_set.add(g.league)

        # Check for new games (use date_added column)
        if g.date_added and g.date_added > one_week_ago:
            new_game_ids.add(g.ID)

        # Check for NTL games
        if g.no_time_limit:
            has_ntl_games = True

    # Build game_originals for rescheduled games (batch query to avoid N+1)
    game_originals = GameChange.get_original_display_batch(games)

    # Apply filters (using cached field_name)
    if field_filter:
        games = [g for g in games if g._cached_field_name and field_filter.lower() in g._cached_field_name.lower()]
    if league_filter:
        games = [g for g in games if g.league and league_filter.lower() in g.league.lower()]
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            games = [g for g in games if g.game_date and g.game_date.date() == filter_date]
        except ValueError:
            pass

    fields = sorted(fields_set)
    leagues = sorted(leagues_set)

    # Get available seasons for the season picker
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    return render_template(
        'public/partner_schedule.html',
        partner=partner,
        games=games,
        season_name=season_name,
        year=year,
        is_spring=is_spring,
        seasons=seasons,
        fields=fields,
        leagues=leagues,
        field_filter=field_filter,
        league_filter=league_filter,
        date_filter=date_filter,
        token=token,
        new_game_ids=new_game_ids,
        has_ntl_games=has_ntl_games,
        game_originals=game_originals,
        today=date.today()
    )


@public_bp.route('/partner/<token>/csv')
def partner_schedule_csv(token):
    """Download partner schedule as CSV."""
    from sqlalchemy.orm import joinedload
    from app.models.game_umpire import GameUmpire
    from app.models.league import League

    partner = UmpirePartner.get_by_schedule_token(token)
    if not partner:
        abort(404)

    # Get query parameters
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)

    # Default to current/upcoming season
    if year is None:
        current = LeagueSeason.query.filter_by(active=1).order_by(
            LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
        ).first()
        if current:
            year = current.year
            is_spring = 1 if current.is_spring else 0
        else:
            year = date.today().year
            is_spring = 1 if date.today().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"}{year}'
    partner_code = partner.short_code

    # Pre-load leagues for umpire count lookup
    all_leagues = {l.display_name: l for l in League.get_all_active()}

    # Get games with eager loading (exclude practices)
    games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == (is_spring == 1),
        Game.umpire_override == partner_code,
        Game.game_type != 'practice'
    ).order_by(Game.game_date).all()

    # Pre-load all umpire assignments for these games in ONE query
    game_ids = [g.ID for g in games]
    all_assignments = {}
    if game_ids:
        assignments = GameUmpire.query.filter(
            GameUmpire.game_id.in_(game_ids),
            GameUmpire.partner_id == partner.id,
            GameUmpire.status != 'cancelled'
        ).all()
        for a in assignments:
            if a.game_id not in all_assignments:
                all_assignments[a.game_id] = []
            if a.notes:
                all_assignments[a.game_id].append(a.notes)

    # Build CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        'Date', 'Day', 'Time', 'League', 'Home Team', 'Away Team',
        'Field', 'Game Type', 'Umpires Needed', 'Assigned Umpire'
    ])

    for game in games:
        game_date = game.game_date
        if game_date:
            date_str = game_date.strftime('%m/%d/%Y')
            day_str = game_date.strftime('%a')
            time_str = game_date.strftime('%I:%M %p')
        else:
            date_str = 'TBD'
            day_str = ''
            time_str = 'TBD'

        home_name = game.home_team.computed_display_name if game.home_team else 'TBD'
        away_name = game.away_team.computed_display_name if game.away_team else 'TBD'

        # Get field name efficiently
        field_name = game.field_name

        # Get umpire count efficiently
        if game.umpire_count_override is not None:
            umpire_count = game.umpire_count_override
        else:
            league_obj = all_leagues.get(game.league)
            if league_obj:
                umpire_count = league_obj.get_umpire_count(is_playoff=game.game_type == 'playoff')
            else:
                umpire_count = 1

        # Get pre-loaded assignments
        umpire_names = all_assignments.get(game.ID, [])

        writer.writerow([
            date_str,
            day_str,
            time_str,
            game.league or '',
            home_name,
            away_name,
            field_name,
            game.game_type or 'regular',
            umpire_count,
            ', '.join(umpire_names)
        ])

    output.seek(0)
    filename = f'SDLL_{season_name}_{partner.name.replace(" ", "_")}.csv'

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@public_bp.route('/api/game-start', methods=['POST'])
def record_game_start():
    """Record or update a game start time (first pitch).

    This is a public API for recording when games actually start.
    Only available for non-practice games on the day of the game.
    Pass allowStartTimeRecord=1 in request body to bypass date check for testing.
    """
    try:
        data = request.get_json() or {}
        game_id = data.get('game_id')
        start_time_str = data.get('start_time')
        # Check for testing flag - accept boolean true, string 'true', or 1
        allow_flag = data.get('allowStartTimeRecord')
        allow_any_date = allow_flag in (True, 'true', '1', 1)

        if not game_id or not start_time_str:
            return jsonify({'error': 'Missing game_id or start_time'}), 400

        # Parse the start time
        try:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid start_time format'}), 400

        # Verify the game exists and is not a practice
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        if game.game_type == 'practice':
            return jsonify({'error': 'Cannot record start time for practices'}), 400

        # Verify it's the day of the game (unless testing flag is set)
        if not allow_any_date and game.game_date:
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            if game_date != date.today():
                return jsonify({'error': 'Can only record start time on day of game'}), 400

        # Get user/session info
        session_id = _get_or_create_session_id()
        user_id = None
        try:
            if current_user.is_authenticated:
                user_id = current_user.ID
        except Exception:
            pass

        # Record the start time
        record = GameStartRecord.record_start(
            game_id=game_id,
            start_time=start_time,
            user_id=user_id,
            session_id=session_id
        )

        # Build response
        response = make_response(jsonify({
            'status': 'ok',
            'record_id': record.id,
            'start_time': record.start_time.isoformat(),
            'was_update': record.created_at != record.updated_at
        }))

        # Set session cookie
        _set_session_cookie(response, session_id)

        return response

    except Exception as e:
        _log_tracking_error("record_game_start", e)
        _safe_rollback()
        return jsonify({'error': 'Failed to record start time'}), 500


@public_bp.route('/api/game-start/<int:game_id>', methods=['GET'])
def get_game_start(game_id):
    """Get game start time record for current user/session.

    Returns the user's own record if they've submitted one,
    or the latest record if they haven't.
    """
    try:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        user_id = None
        try:
            if current_user.is_authenticated:
                user_id = current_user.ID
        except Exception:
            pass

        # First check for user's own record
        record = None
        if user_id:
            record = GameStartRecord.get_for_game_by_user(game_id, user_id)
        if not record and session_id:
            record = GameStartRecord.get_for_game_by_session(game_id, session_id)

        if record:
            return jsonify({
                'has_record': True,
                'is_own': True,
                'start_time': record.start_time.isoformat(),
                'created_at': record.created_at.isoformat(),
                'updated_at': record.updated_at.isoformat()
            })

        # Check if there's any record for this game
        latest = GameStartRecord.get_latest_for_game(game_id)
        if latest:
            return jsonify({
                'has_record': True,
                'is_own': False,
                'start_time': latest.start_time.isoformat(),
                'created_at': latest.created_at.isoformat(),
                'updated_at': latest.updated_at.isoformat()
            })

        return jsonify({'has_record': False})

    except Exception as e:
        _log_tracking_error("get_game_start", e)
        return jsonify({'has_record': False})


def user_has_coach_access(user_id, year, is_spring, league):
    """Check if user is an active coach in this specific league-season."""
    from app.models.coach import CoachUser, CoachSeason

    coach = CoachUser.get_by_user(user_id)
    if not coach or coach.status != 'active':
        return False

    return CoachSeason.query.join(TeamSeason).filter(
        CoachSeason.coach_id == coach.id,
        TeamSeason.year == year,
        TeamSeason.is_spring == is_spring,
        TeamSeason.league == league,
        TeamSeason.active == 1
    ).count() > 0


@public_bp.route('/division/<token>')
def division_schedule(token):
    """Public division schedule view with tiered access control."""
    league_season = LeagueSeason.get_by_schedule_token(token)
    if not league_season:
        abort(404)

    # Not logged in -> landing page
    if not current_user.is_authenticated:
        return render_template(
            'public/division_landing.html',
            league_season=league_season,
            login_url=url_for('auth.login', next=request.url)
        )

    # Check access
    has_full_access = current_user.has_role('admin', 'scheduler', 'umpire_coordinator')
    has_coach_access = user_has_coach_access(
        current_user.ID,
        league_season.year,
        league_season.is_spring,
        league_season.league
    )

    if not has_full_access and not has_coach_access:
        return render_template(
            'public/division_request_access.html',
            league_season=league_season,
            token=token
        )

    # Load games (including practices) with eager loading
    games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.active == 1,
        Game.year == league_season.year,
        Game.is_spring == league_season.is_spring,
        Game.league == league_season.league
    ).order_by(Game.game_date).all()

    today = date.today()

    # Separate upcoming and past games
    upcoming_games = []
    past_games = []
    for game in games:
        if game.game_date:
            game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date
            if game_date >= today:
                upcoming_games.append(game)
            else:
                past_games.append(game)
        else:
            upcoming_games.append(game)  # TBD dates go to upcoming

    # Get "originally" display text for games that have been changed (batch query)
    all_games = upcoming_games + past_games
    try:
        game_originals = GameChange.get_original_display_batch(all_games)
    except Exception:
        game_originals = {}

    # Get teams for filter dropdown
    teams = TeamSeason.query.filter_by(
        year=league_season.year,
        is_spring=league_season.is_spring,
        league=league_season.league,
        active=1,
        is_placeholder=0
    ).order_by(TeamSeason.display_name).all()

    # Get fields for filter dropdown
    fields_set = set()
    for g in games:
        if g.field_name:
            fields_set.add(g.field_name)
    fields = sorted(fields_set)

    return render_template(
        'public/division_schedule.html',
        league_season=league_season,
        games=games,
        upcoming_games=upcoming_games,
        past_games=past_games,
        game_originals=game_originals,
        teams=teams,
        fields=fields,
        show_minimal_menu=not has_full_access,
        today=today,
        token=token
    )


@public_bp.route('/division/<token>/request-access', methods=['POST'])
def division_request_access(token):
    """Handle access request form submission."""
    league_season = LeagueSeason.get_by_schedule_token(token)
    if not league_season:
        abort(404)

    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))

    message = request.form.get('message', '').strip()

    # Send email to scheduling coordinator
    try:
        from app.services.notification_service import GmailService
        email_service = GmailService()

        season_name = f'{"Spring" if league_season.is_spring else "Fall"} {league_season.year}'
        subject = f'SDLL Division Schedule Access Request - {league_season.league} {season_name}'

        body_text = f"""Access Request for Division Schedule

User: {current_user.name}
Email: {current_user.email}
League: {league_season.league}
Season: {season_name}

Message from user:
{message if message else '(No message provided)'}

---
This request was submitted from the division schedule page.
"""

        body_html = f"""
<h2>Access Request for Division Schedule</h2>
<p><strong>User:</strong> {current_user.name}<br>
<strong>Email:</strong> {current_user.email}<br>
<strong>League:</strong> {league_season.league}<br>
<strong>Season:</strong> {season_name}</p>

<h3>Message from user:</h3>
<p>{message if message else '<em>(No message provided)</em>'}</p>

<hr>
<p><small>This request was submitted from the division schedule page.</small></p>
"""

        # Send to scheduling coordinator
        coordinator_email = 'scheduling@sdll.org'  # Default, could be configurable
        email_service.send_email(
            to=coordinator_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            reply_to=current_user.email
        )

        flash('Your access request has been sent. You will be contacted by email.', 'success')
    except Exception as e:
        _log_tracking_error("division_request_access", e)
        flash('There was an error sending your request. Please try again or contact scheduling@sdll.org directly.', 'error')

    return redirect(url_for('public.division_schedule', token=token))
