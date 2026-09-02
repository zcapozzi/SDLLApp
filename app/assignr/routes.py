"""Assignr integration routes.

Provides views for:
- Assignr games dashboard
- Umpire assignment status
- Sync status between Assignr and local games
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date, timedelta

from app.extensions import db
from app.models.league import League
from app.models.umpire_partner import UmpirePartner
from app.services.assignr_service import get_assignr_service
from app.utils.logging import SDLLLogger
from . import assignr_bp

logger = SDLLLogger('assignr')


def add_needs_umpire_flags(games, league_lookup):
    """Add _needs_umpire flag to each game based on local data.

    A game needs umpire if:
    - League requires umpires (league.needs_umpires)
    - AND umpire_count_override is not 0
    - AND game is unassigned (no accepted umpires)
    """
    for game in games:
        needs_umpire = False
        local = game.get('_local')

        if local:
            # Use local game's league
            league_obj = league_lookup.get(local.get('league'))
            if league_obj and league_obj.needs_umpires:
                # Check if umpire_count_override is explicitly 0
                if local.get('umpire_count_override') == 0:
                    needs_umpire = False
                else:
                    needs_umpire = True

        game['_needs_umpire'] = needs_umpire

    return games


def umpire_coordinator_required(f):
    """Decorator to require umpire coordinator or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.can_manage_umpires():
            flash('You do not have permission to access Assignr data.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@assignr_bp.route('/')
@login_required
@umpire_coordinator_required
def index():
    """Assignr dashboard - games and umpire summary."""
    service = get_assignr_service()

    # Check if Assignr is configured
    if not service.is_configured():
        return render_template(
            'assignr/not_configured.html'
        )

    # Get date range from query params (default to next 2 weeks)
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            end_date = start_date + timedelta(days=14)
    else:
        end_date = start_date + timedelta(days=14)

    # Fetch games from Assignr
    assignr_games = service.get_all_games(start_date, end_date)

    # Enrich with local data
    assignr_games = service.enrich_games_with_local_data(assignr_games)

    # Get league lookup for needs_umpire calculation
    league_lookup = {l.display_name: l for l in League.query.all()}

    # Add _needs_umpire flag to each game
    assignr_games = add_needs_umpire_flags(assignr_games, league_lookup)

    # Separate urgent games (within 2 weeks from now, needs umpire, unassigned)
    now = datetime.now()
    two_weeks_from_now = now + timedelta(days=14)
    urgent_games = []

    for game in assignr_games:
        # Parse game date
        game_date_str = game.get('localized_date', '')[:10] if game.get('localized_date') else ''
        game_datetime = None
        if game_date_str:
            try:
                game_datetime = datetime.strptime(game_date_str, '%Y-%m-%d')
            except ValueError:
                pass

        # Check if urgent: needs umpire, unassigned, and within 2 weeks
        has_assignment = len(game.get('_accepted_umpires', []) or []) > 0
        is_urgent = (
            game.get('_needs_umpire') and
            not has_assignment and
            game_datetime and
            game_datetime <= two_weeks_from_now
        )

        if is_urgent:
            urgent_games.append(game)

    # Build summary
    summary = service.get_umpire_summary(assignr_games)

    # Sort umpires by game count (descending)
    umpires_sorted = sorted(
        summary['umpires'].items(),
        key=lambda x: x[1]['games'],
        reverse=True
    )

    # Sort leagues by game count
    leagues_sorted = sorted(
        summary['by_league'].items(),
        key=lambda x: x[1]['games'],
        reverse=True
    )

    # Get umpire partners for source dropdown
    partners = UmpirePartner.get_active()

    return render_template(
        'assignr/index.html',
        games=assignr_games,
        urgent_games=urgent_games,
        summary=summary,
        umpires=umpires_sorted,
        leagues=leagues_sorted,
        partners=partners,
        start_date=start_date,
        end_date=end_date
    )


@assignr_bp.route('/games')
@login_required
@umpire_coordinator_required
def games_list():
    """List view of Assignr games with filtering."""
    service = get_assignr_service()

    if not service.is_configured():
        return redirect(url_for('assignr.index'))

    # Get date range from query params
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    league_filter = request.args.get('league', '')

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            end_date = start_date + timedelta(days=14)
    else:
        end_date = start_date + timedelta(days=14)

    # Fetch games from Assignr
    assignr_games = service.get_all_games(start_date, end_date)

    # Enrich with local data
    assignr_games = service.enrich_games_with_local_data(assignr_games)

    # Get league lookup for needs_umpire calculation
    league_lookup = {l.display_name: l for l in League.query.all()}

    # Add _needs_umpire flag to each game
    assignr_games = add_needs_umpire_flags(assignr_games, league_lookup)

    # Separate urgent games (within 2 weeks from now, needs umpire, unassigned)
    now = datetime.now()
    two_weeks_from_now = now + timedelta(days=14)
    urgent_games = []
    regular_games = []

    for game in assignr_games:
        # Parse game date
        game_date_str = game.get('localized_date', '')[:10] if game.get('localized_date') else ''
        game_datetime = None
        if game_date_str:
            try:
                game_datetime = datetime.strptime(game_date_str, '%Y-%m-%d')
            except ValueError:
                pass

        # Check if urgent: needs umpire, unassigned, and within 2 weeks
        has_assignment = len(game.get('_accepted_umpires', []) or []) > 0
        is_urgent = (
            game.get('_needs_umpire') and
            not has_assignment and
            game_datetime and
            game_datetime <= two_weeks_from_now
        )

        if is_urgent:
            urgent_games.append(game)

        regular_games.append(game)

    # Get unique leagues for filter dropdown
    leagues = set()
    for game in assignr_games:
        local = game.get('_local')
        league = local['league'] if local else game.get('league_name', '')
        if league:
            leagues.add(league)
    leagues = sorted(leagues)

    # Get umpire partners for source dropdown
    partners = UmpirePartner.get_active()

    return render_template(
        'assignr/games.html',
        games=regular_games,
        urgent_games=urgent_games,
        leagues=leagues,
        partners=partners,
        league_filter=league_filter,
        start_date=start_date,
        end_date=end_date
    )


@assignr_bp.route('/umpires')
@login_required
@umpire_coordinator_required
def umpires_list():
    """Summary of umpire assignments from Assignr."""
    service = get_assignr_service()

    if not service.is_configured():
        return redirect(url_for('assignr.index'))

    # Get date range from query params (default to current season span)
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now() - timedelta(days=30)
    else:
        start_date = datetime.now() - timedelta(days=30)

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            end_date = datetime.now() + timedelta(days=30)
    else:
        end_date = datetime.now() + timedelta(days=30)

    # Fetch games from Assignr
    assignr_games = service.get_all_games(start_date, end_date)

    # Enrich with local data
    assignr_games = service.enrich_games_with_local_data(assignr_games)

    # Build summary
    summary = service.get_umpire_summary(assignr_games)

    # Sort umpires by game count (descending)
    umpires_sorted = sorted(
        summary['umpires'].items(),
        key=lambda x: x[1]['games'],
        reverse=True
    )

    return render_template(
        'assignr/umpires.html',
        umpires=umpires_sorted,
        summary=summary,
        start_date=start_date,
        end_date=end_date
    )


@assignr_bp.route('/api/games')
@login_required
@umpire_coordinator_required
def api_games():
    """API endpoint for fetching Assignr games as JSON."""
    service = get_assignr_service()

    if not service.is_configured():
        return jsonify({'error': 'Assignr not configured'}), 500

    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid start date'}), 400
    else:
        start_date = datetime.now()

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid end date'}), 400
    else:
        end_date = start_date + timedelta(days=14)

    # Fetch games
    assignr_games = service.get_all_games(start_date, end_date)
    assignr_games = service.enrich_games_with_local_data(assignr_games)
    summary = service.get_umpire_summary(assignr_games)

    return jsonify({
        'games': assignr_games,
        'summary': summary,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat()
    })


@assignr_bp.route('/sync-status')
@login_required
@umpire_coordinator_required
def sync_status():
    """Show sync status between Assignr and local games."""
    from app.models.game import Game
    from sqlalchemy.orm import joinedload

    service = get_assignr_service()

    if not service.is_configured():
        return redirect(url_for('assignr.index'))

    # Get date range
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            end_date = start_date + timedelta(days=30)
    else:
        end_date = start_date + timedelta(days=30)

    # Fetch from Assignr
    assignr_games = service.get_all_games(start_date, end_date)
    assignr_ids = {str(g.get('id')) for g in assignr_games if g.get('id')}

    # Fetch local games with assignr_id in date range
    local_games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.active == 1,
        Game.game_date >= start_date,
        Game.game_date <= end_date,
        Game.game_type.in_(['regular', 'playoff'])
    ).all()

    # Categorize games
    synced = []  # In both Assignr and local
    assignr_only = []  # In Assignr but not linked locally
    local_only = []  # Local with assignr_id not in Assignr results
    unlinked = []  # Local games without assignr_id

    local_assignr_ids = set()
    for game in local_games:
        if game.assignr_id:
            local_assignr_ids.add(game.assignr_id)
            if game.assignr_id in assignr_ids:
                synced.append(game)
            else:
                local_only.append(game)
        else:
            unlinked.append(game)

    # Find Assignr games not linked to local
    for ag in assignr_games:
        if str(ag.get('id')) not in local_assignr_ids:
            assignr_only.append(ag)

    return render_template(
        'assignr/sync_status.html',
        synced=synced,
        assignr_only=assignr_only,
        local_only=local_only,
        unlinked=unlinked,
        start_date=start_date,
        end_date=end_date
    )
