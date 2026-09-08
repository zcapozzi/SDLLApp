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

    # Get date range from query params
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    show_unpublished = request.args.get('show_unpublished', '0') == '1'

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    # End date is optional - if not specified, fetch through end of year
    end_date = None
    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
        except ValueError:
            pass

    # Use end of year as API fallback when no end date specified
    api_end_date = end_date if end_date else datetime(start_date.year, 12, 31)

    # Fetch games from Assignr
    assignr_games = service.get_all_games(start_date, api_end_date)

    # Enrich with local data
    assignr_games = service.enrich_games_with_local_data(assignr_games)

    # Get league lookup for needs_umpire calculation
    league_lookup = {l.display_name: l for l in League.query.all()}

    # Add _needs_umpire flag to each game
    assignr_games = add_needs_umpire_flags(assignr_games, league_lookup)

    # Separate urgent games (within 2 weeks from now, needs umpire, unassigned, SDL-managed)
    now = datetime.now()
    two_weeks_from_now = now + timedelta(days=14)
    urgent_games = []

    for game in assignr_games:
        # Only consider SDL-managed games for urgent list
        local = game.get('_local')
        if not local or local.get('umpire_override') != 'SDL':
            continue

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

    # Filter to only SDL-managed games for summary stats
    # (games where umpire_override='SDL' - these are games WE need to assign)
    sdl_games = [
        g for g in assignr_games
        if g.get('_local') and g['_local'].get('umpire_override') == 'SDL'
    ]

    # Build summary based only on SDL-managed games
    summary = service.get_umpire_summary(sdl_games)

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

    # Build delegated games summary (games NOT managed by SDL)
    # These are unpublished in Assignr and assigned to partners
    delegated_summary = {}
    for game in assignr_games:
        local = game.get('_local')
        if local:
            override = local.get('umpire_override')
            # Count games by their umpire_override (excluding SDL and None)
            if override and override.upper() != 'SDL':
                if override not in delegated_summary:
                    delegated_summary[override] = {'count': 0, 'unpublished': 0}
                delegated_summary[override]['count'] += 1
                # Check if game is unpublished in Assignr
                if not game.get('published', True):
                    delegated_summary[override]['unpublished'] += 1

    return render_template(
        'assignr/index.html',
        games=assignr_games,
        urgent_games=urgent_games,
        summary=summary,
        umpires=umpires_sorted,
        leagues=leagues_sorted,
        partners=partners,
        delegated_summary=delegated_summary,
        start_date=start_date,
        end_date=end_date,
        show_unpublished=show_unpublished
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
    show_unpublished = request.args.get('show_unpublished', '0') == '1'

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    # End date is optional - if not specified, fetch through end of year
    end_date = None
    end_date_specified = False
    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
            end_date_specified = True
        except ValueError:
            pass

    # Use end of year as API fallback when no end date specified
    api_end_date = end_date if end_date else datetime(start_date.year, 12, 31)

    # Fetch games from Assignr
    assignr_games = service.get_all_games(start_date, api_end_date)

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
        end_date=end_date,
        show_unpublished=show_unpublished
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


@assignr_bp.route('/officials')
@login_required
@umpire_coordinator_required
def officials_list():
    """List officials and their group memberships from Assignr."""
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_group_assignment import UmpireGroupAssignment
    from dateutil.relativedelta import relativedelta

    service = get_assignr_service()

    if not service.is_configured():
        return redirect(url_for('assignr.index'))

    # Fetch groups first
    groups = service.get_site_groups()
    group_lookup = {g.get('id'): g for g in groups}

    # Fetch all officials
    officials = service.get_all_site_officials()

    # Get local umpire profiles for linking
    local_profiles = UmpireProfile.query.filter(
        UmpireProfile.assignr_id.isnot(None)
    ).all()
    local_by_assignr_id = {p.assignr_id: p for p in local_profiles}

    # Get all local group assignments
    all_assignments = UmpireGroupAssignment.query.all()
    local_groups_by_profile = {}
    for assignment in all_assignments:
        if assignment.umpire_profile_id not in local_groups_by_profile:
            local_groups_by_profile[assignment.umpire_profile_id] = set()
        local_groups_by_profile[assignment.umpire_profile_id].add(assignment.assignr_group_id)

    # Get last game date for each official from Assignr API
    last_game_by_official = service.get_official_last_game_dates(months_back=24)

    # Calculate inactive threshold (12 months ago)
    inactive_threshold = datetime.now() - relativedelta(months=12)

    # Enrich officials with local data and group info
    for official in officials:
        official_id = official.get('id')
        official_id_str = str(official_id) if official_id else ''
        local_profile = local_by_assignr_id.get(official_id_str)
        official['_local_profile'] = local_profile

        # Get local SDLL group assignments for this profile
        if local_profile:
            official['_local_group_ids'] = local_groups_by_profile.get(local_profile.id, set())
        else:
            official['_local_group_ids'] = set()

        # Get last active date from Assignr data
        last_game = last_game_by_official.get(official_id)
        official['_last_active_date'] = last_game
        official['_is_inactive'] = last_game is None or last_game < inactive_threshold

        # Get this official's groups from Assignr
        official_groups = service.get_official_groups(int(official_id)) if official_id else []
        official['_groups'] = official_groups
        official['_group_names'] = [g.get('name', '') for g in official_groups]

        # Build Assignr profile URL
        official['_assignr_url'] = f"https://sdll.assignr.com/users/{official_id}"

    # Sort by last name, first name
    officials.sort(key=lambda o: (o.get('last_name', '').lower(), o.get('first_name', '').lower()))

    return render_template(
        'assignr/officials.html',
        officials=officials,
        groups=groups
    )


@assignr_bp.route('/officials/<int:official_id>/groups', methods=['POST'])
@login_required
@umpire_coordinator_required
def update_official_groups(official_id):
    """Update an official's group memberships."""
    service = get_assignr_service()

    if not service.is_configured():
        return jsonify({'error': 'Assignr not configured'}), 500

    data = request.get_json()
    action = data.get('action')  # 'add' or 'remove'
    group_id = data.get('group_id')

    if not action or not group_id:
        return jsonify({'error': 'Missing action or group_id'}), 400

    if action == 'add':
        success, error = service.add_official_to_group(official_id, group_id)
    elif action == 'remove':
        success, error = service.remove_official_from_group(official_id, group_id)
    else:
        return jsonify({'error': 'Invalid action'}), 400

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': error}), 500


@assignr_bp.route('/officials/<int:official_id>/sdll-groups', methods=['POST'])
@login_required
@umpire_coordinator_required
def update_sdll_groups(official_id):
    """Update SDLL group assignment and sync with Assignr."""
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_group_assignment import UmpireGroupAssignment

    service = get_assignr_service()

    if not service.is_configured():
        return jsonify({'error': 'Assignr not configured'}), 500

    data = request.get_json()
    profile_id = data.get('profile_id')
    group_id = data.get('group_id')
    group_name = data.get('group_name')
    checked = data.get('checked', False)

    if not profile_id or not group_id:
        return jsonify({'error': 'Missing profile_id or group_id'}), 400

    # Find the SDLL profile
    profile = UmpireProfile.query.get(profile_id)
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404

    # Update local assignment
    if checked:
        UmpireGroupAssignment.add_group(profile_id, group_id, group_name)
    else:
        UmpireGroupAssignment.remove_group(profile_id, group_id)

    # Sync with Assignr
    if checked:
        success, error = service.add_official_to_group(official_id, group_id)
    else:
        success, error = service.remove_official_from_group(official_id, group_id)

    if not success:
        logger.warning(f"Failed to sync group {group_id} to Assignr: {error}")
        # Still return success - local update worked

    return jsonify({'success': True})


@assignr_bp.route('/officials/import', methods=['POST'])
@login_required
@umpire_coordinator_required
def import_from_assignr():
    """Import group memberships from Assignr and update SDLL database."""
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_group_assignment import UmpireGroupAssignment

    service = get_assignr_service()

    if not service.is_configured():
        flash('Assignr not configured.', 'error')
        return redirect(url_for('assignr.officials_list'))

    # Get all groups for name lookup
    groups = service.get_site_groups()
    group_lookup = {g.get('id'): g.get('name') for g in groups}

    # Get all linked profiles
    profiles = UmpireProfile.query.filter(
        UmpireProfile.assignr_id.isnot(None)
    ).all()

    total_added = 0
    total_removed = 0

    for profile in profiles:
        official_id = int(profile.assignr_id)
        official_groups = service.get_official_groups(official_id)
        group_ids = [g.get('id') for g in official_groups]

        # Sync local assignments to match Assignr
        added, removed = UmpireGroupAssignment.sync_from_list(
            profile.id, group_ids, group_lookup
        )
        total_added += added
        total_removed += removed

    flash(f'Imported from Assignr: {total_added} added, {total_removed} removed.', 'success')
    return redirect(url_for('assignr.officials_list'))


@assignr_bp.route('/officials/sync', methods=['POST'])
@login_required
@umpire_coordinator_required
def sync_officials_with_assignr():
    """Push SDLL group assignments to Assignr."""
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_group_assignment import UmpireGroupAssignment

    service = get_assignr_service()

    if not service.is_configured():
        flash('Assignr not configured.', 'error')
        return redirect(url_for('assignr.officials_list'))

    # Get all linked profiles with their group assignments
    profiles = UmpireProfile.query.filter(
        UmpireProfile.assignr_id.isnot(None)
    ).all()

    # Get all groups for reference
    all_groups = service.get_site_groups()
    all_group_ids = {g.get('id') for g in all_groups}

    synced = 0
    errors = 0

    for profile in profiles:
        official_id = int(profile.assignr_id)

        # Get current Assignr groups
        current_assignr_groups = service.get_official_groups(official_id)
        current_group_ids = {g.get('id') for g in current_assignr_groups}

        # Get desired SDLL groups
        desired_group_ids = set(UmpireGroupAssignment.get_group_ids_for_profile(profile.id))

        # Add missing groups
        for gid in desired_group_ids - current_group_ids:
            if gid in all_group_ids:  # Only sync known groups
                success, error = service.add_official_to_group(official_id, gid)
                if success:
                    synced += 1
                else:
                    errors += 1

        # Remove extra groups
        for gid in current_group_ids - desired_group_ids:
            if gid in all_group_ids:  # Only sync known groups
                success, error = service.remove_official_from_group(official_id, gid)
                if success:
                    synced += 1
                else:
                    errors += 1

    flash(f'Synced to Assignr: {synced} changes ({errors} errors).', 'success' if errors == 0 else 'warning')
    return redirect(url_for('assignr.officials_list'))


@assignr_bp.route('/groups')
@login_required
@umpire_coordinator_required
def groups_list():
    """List all groups defined for this site."""
    service = get_assignr_service()

    if not service.is_configured():
        return redirect(url_for('assignr.index'))

    groups = service.get_site_groups()

    return render_template(
        'assignr/groups.html',
        groups=groups
    )
