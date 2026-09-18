"""Umpire Capacity Dashboard - heatmap view of umpire activity and availability.

Shows a GitHub-style contribution chart with:
- Past activity (games worked)
- Future availability (blockouts)
- Scheduled games
- Swap suggestions for BTP-qualified umpires
"""

from flask import render_template, request, jsonify
from flask_login import login_required
from datetime import datetime, date, timedelta
from collections import defaultdict

from app.extensions import db
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_blockout import UmpireBlockout
from app.models.game import Game
from app.models.org_season import OrgSeason
from app.models.league import League

from . import umpires_bp, umpire_coordinator_required


@umpires_bp.route('/capacity')
@login_required
@umpire_coordinator_required
def capacity_dashboard():
    """Umpire capacity dashboard with activity heatmap."""
    today = date.today()

    # Get current season
    current_season = OrgSeason.get_current_season()

    # Determine date range
    # Past: 30 days
    # Future: to end of season or 60 days, whichever is later
    start_date = today - timedelta(days=30)

    season_end = None
    if current_season and current_season.season_end_date:
        season_end = current_season.season_end_date

    # Get last game date
    last_game = Game.query.filter(
        Game.active == 1,
        Game.game_date >= datetime.combine(today, datetime.min.time())
    ).order_by(Game.game_date.desc()).first()

    last_game_date = last_game.game_date.date() if last_game else None

    # Use whichever is later
    min_end = today + timedelta(days=60)
    end_date = max(filter(None, [season_end, last_game_date, min_end]))

    # Get active umpires (active in last 60 days OR has upcoming games)
    active_umpires = get_active_umpires(today)

    # Get all blockouts for active umpires
    all_blockouts = get_blockouts_map(active_umpires, start_date, end_date)

    # Get all games with umpire assignments
    games_by_date = get_games_by_date(start_date, end_date)

    # Get umpire assignments from Assignr
    umpire_game_counts = get_umpire_game_counts(start_date, end_date)

    # Build heatmap data
    heatmap_data = build_heatmap_data(
        active_umpires,
        start_date,
        end_date,
        all_blockouts,
        umpire_game_counts,
        today
    )

    # Get leagues for filtering
    leagues = League.query.filter_by(active=1).order_by(League.sort_order).all()

    # Get open games (SDL games without assignments)
    open_games = get_open_sdl_games(today, end_date)

    # Get swap suggestions for BTP games
    swap_suggestions = get_swap_suggestions(today, end_date, active_umpires, all_blockouts)

    return render_template(
        'umpires/capacity_dashboard.html',
        start_date=start_date,
        end_date=end_date,
        today=today,
        active_umpires=active_umpires,
        heatmap_data=heatmap_data,
        leagues=leagues,
        open_games=open_games,
        swap_suggestions=swap_suggestions,
        current_season=current_season
    )


def get_active_umpires(reference_date):
    """Get umpires who are active (worked recently or have upcoming games).

    Returns list of UmpireProfile objects with safe name access.
    """
    # Get profiles that are active status
    profiles = UmpireProfile.query.filter(
        UmpireProfile.status == UmpireProfile.STATUS_ACTIVE
    ).all()

    # Add safe name access for profiles with encryption key mismatch
    valid_profiles = []
    for p in profiles:
        try:
            # Test if we can decrypt the name
            _ = p.name
            valid_profiles.append(p)
        except Exception:
            # Skip profiles we can't decrypt
            # Could also add: p._safe_name = f"Profile #{p.id}"
            pass

    return valid_profiles


def get_blockouts_map(umpires, start_date, end_date):
    """Get blockouts for all umpires as a map.

    Returns dict: {profile_id: set of blocked dates}
    """
    profile_ids = [u.id for u in umpires]

    blockouts = UmpireBlockout.query.filter(
        UmpireBlockout.umpire_profile_id.in_(profile_ids),
        UmpireBlockout.blocked_date >= start_date,
        UmpireBlockout.blocked_date <= end_date
    ).all()

    result = defaultdict(set)
    for b in blockouts:
        result[b.umpire_profile_id].add(b.blocked_date)

    return result


def get_games_by_date(start_date, end_date):
    """Get games grouped by date.

    Returns dict: {date: list of Game objects}
    """
    games = Game.query.filter(
        Game.active == 1,
        Game.game_date >= datetime.combine(start_date, datetime.min.time()),
        Game.game_date <= datetime.combine(end_date, datetime.max.time())
    ).all()

    result = defaultdict(list)
    for g in games:
        result[g.game_date.date()].append(g)

    return result


def get_umpire_game_counts(start_date, end_date):
    """Get game counts per umpire from Assignr.

    Returns dict: {profile_id: {date: count}}
    """
    from app.services.assignr_service import get_assignr_service

    result = defaultdict(lambda: defaultdict(int))

    try:
        assignr = get_assignr_service()
        if not assignr.is_configured():
            return result

        # Get all games from Assignr
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        games = assignr.get_all_games(start_dt, end_dt)

        # Build assignr_id -> profile_id map
        profiles = UmpireProfile.query.filter(
            UmpireProfile.assignr_id.isnot(None)
        ).all()
        assignr_to_profile = {str(p.assignr_id): p.id for p in profiles}

        # Count games per umpire per date
        for game in games:
            if game.get('is_cancelled'):
                continue

            game_date = game.get('_game_date')
            if not game_date:
                continue

            assignments = game.get('_embedded', {}).get('assignments', []) or []
            for assignment in assignments:
                if assignment.get('accepted') not in [True, 'True']:
                    continue

                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}
                assignr_id = str(official.get('id', ''))

                if assignr_id in assignr_to_profile:
                    profile_id = assignr_to_profile[assignr_id]
                    result[profile_id][game_date.date()] += 1

    except Exception as e:
        print(f"Error fetching Assignr game counts: {e}")

    return result


def build_heatmap_data(umpires, start_date, end_date, blockouts, game_counts, today):
    """Build heatmap data structure for template.

    Returns list of dicts, one per umpire:
    {
        'profile': UmpireProfile,
        'days': [
            {
                'date': date,
                'count': int,  # games worked
                'blocked': bool,
                'is_past': bool,
                'is_today': bool
            },
            ...
        ],
        'total_games': int,
        'blocked_count': int
    }
    """
    result = []

    # Generate list of all dates
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    for umpire in umpires:
        umpire_blockouts = blockouts.get(umpire.id, set())
        umpire_games = game_counts.get(umpire.id, {})

        days = []
        total_games = 0
        blocked_count = 0

        for d in dates:
            count = umpire_games.get(d, 0)
            blocked = d in umpire_blockouts

            total_games += count
            if blocked and d >= today:
                blocked_count += 1

            days.append({
                'date': d,
                'count': count,
                'blocked': blocked,
                'is_past': d < today,
                'is_today': d == today
            })

        result.append({
            'profile': umpire,
            'days': days,
            'total_games': total_games,
            'blocked_count': blocked_count
        })

    # Sort by total games (most active first)
    result.sort(key=lambda x: x['total_games'], reverse=True)

    return result


def get_open_sdl_games(start_date, end_date):
    """Get SDL games that don't have umpire assignments.

    Returns list of Game objects with SDL (needs internal umpires)
    that don't have Assignr assignments.
    """
    from app.services.assignr_service import get_assignr_service

    # Get SDL games (umpire_override = 'SDL')
    games = Game.query.filter(
        Game.active == 1,
        Game.umpire_override == 'SDL',
        Game.game_date >= datetime.combine(start_date, datetime.min.time()),
        Game.game_date <= datetime.combine(end_date, datetime.max.time())
    ).order_by(Game.game_date).all()

    if not games:
        return []

    # Check which have Assignr assignments
    open_games = []

    try:
        assignr = get_assignr_service()
        if not assignr.is_configured():
            return games  # All SDL games are "open" if no Assignr

        # Get Assignr game IDs for this range
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        assignr_games = assignr.get_all_games(start_dt, end_dt)

        # Build set of Assignr IDs with accepted assignments
        assigned_ids = set()
        for ag in assignr_games:
            assignments = ag.get('_embedded', {}).get('assignments', []) or []
            has_accepted = any(a.get('accepted') in [True, 'True'] for a in assignments)
            if has_accepted:
                assigned_ids.add(str(ag.get('id')))

        # Filter to games without assignments
        for game in games:
            if game.assignr_id and str(game.assignr_id) in assigned_ids:
                continue
            open_games.append(game)

    except Exception as e:
        print(f"Error checking Assignr assignments: {e}")
        open_games = games

    return open_games


def get_swap_suggestions(start_date, end_date, umpires, blockouts):
    """Get swap suggestions for BTP games.

    Find games where:
    - Current plate umpire is not BTP-qualified
    - A BTP-qualified umpire is available

    Returns list of suggestion dicts.
    """
    from app.services.assignr_service import get_assignr_service

    suggestions = []

    try:
        assignr = get_assignr_service()
        if not assignr.is_configured():
            return suggestions

        # Get BTP-qualified umpires (max_baseball_age_rank >= 4 means AA or higher)
        btp_umpires = [u for u in umpires if u.max_baseball_age_rank and u.max_baseball_age_rank >= 4]
        btp_assignr_ids = {str(u.assignr_id) for u in btp_umpires if u.assignr_id}

        if not btp_umpires:
            return suggestions

        # Build profile lookups
        assignr_to_profile = {str(u.assignr_id): u for u in umpires if u.assignr_id}

        # Get games from Assignr
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        games = assignr.get_all_games(start_dt, end_dt)

        for game in games:
            if game.get('is_cancelled'):
                continue

            game_date = game.get('_game_date')
            if not game_date:
                continue

            # Only look at future games
            if game_date.date() < date.today():
                continue

            # Check if this is a kid-pitch game (AA, AAA)
            title = game.get('localized_title', '').lower()
            is_kid_pitch = 'aa' in title or 'aaa' in title or 'majors' in title

            if not is_kid_pitch:
                continue

            # Find plate assignment
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            plate_assignment = None
            plate_official = None

            for assignment in assignments:
                if assignment.get('accepted') not in [True, 'True']:
                    continue
                position = assignment.get('position', '').lower()
                if 'plate' in position or 'hp' in position:
                    embedded = assignment.get('_embedded', {}) or {}
                    official = embedded.get('official', {}) or {}
                    plate_official = official
                    plate_assignment = assignment
                    break

            if not plate_official:
                continue

            plate_assignr_id = str(plate_official.get('id', ''))

            # Check if plate umpire is BTP-qualified
            if plate_assignr_id in btp_assignr_ids:
                continue  # Already BTP-qualified

            # Find available BTP umpires for this date
            game_day = game_date.date()
            available_btp = []

            for u in btp_umpires:
                # Check not blocked
                umpire_blocks = blockouts.get(u.id, set())
                if game_day in umpire_blocks:
                    continue

                # Check not already assigned to this game
                is_assigned = False
                for assignment in assignments:
                    if assignment.get('accepted') not in [True, 'True']:
                        continue
                    embedded = assignment.get('_embedded', {}) or {}
                    off = embedded.get('official', {}) or {}
                    if str(off.get('id')) == str(u.assignr_id):
                        is_assigned = True
                        break

                if not is_assigned:
                    available_btp.append(u)

            if available_btp:
                # Get current plate umpire profile
                current_profile = assignr_to_profile.get(plate_assignr_id)
                current_name = plate_official.get('first_name', '') + ' ' + plate_official.get('last_name', '')

                suggestions.append({
                    'game': game,
                    'game_date': game_date,
                    'current_plate': current_name.strip() or 'Unknown',
                    'current_profile': current_profile,
                    'available_btp': available_btp[:3]  # Top 3 suggestions
                })

    except Exception as e:
        print(f"Error getting swap suggestions: {e}")

    return suggestions[:10]  # Limit to 10 suggestions
