"""Umpire availability routes - self-service blockout management.

Umpires log in and mark dates they are NOT available to work.
This helps the umpire coordinator know who might pick up open games.
"""

from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta

from app.extensions import db
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_blockout import UmpireBlockout
from app.models.org_season import OrgSeason
from app.models.game import Game

from . import umpires_bp


@umpires_bp.route('/availability')
@login_required
def availability():
    """Umpire availability management page.

    Shows a calendar where umpires can mark dates they're unavailable.
    Also shows their upcoming scheduled games.
    """
    # Get the umpire's profile(s)
    # User might have their own profile OR be a guardian of managed profiles
    accessible_profiles = UmpireProfile.get_accessible_profiles(current_user.ID)

    if not accessible_profiles:
        flash('No umpire profile found. Please contact the umpire coordinator.', 'warning')
        return redirect(url_for('main.dashboard'))

    # If multiple profiles, let user select (or default to first)
    profile_id = request.args.get('profile_id', type=int)
    if profile_id:
        profile = next((p for p in accessible_profiles if p.id == profile_id), None)
        if not profile:
            flash('Profile not found or not accessible.', 'error')
            return redirect(url_for('umpires.availability'))
    else:
        profile = accessible_profiles[0]

    # Determine calendar date range
    # Start: today
    # End: end of current season OR last game date, whichever is later
    today = date.today()
    start_date = today

    # Get current season end date
    current_season = OrgSeason.get_current_season()
    season_end = None
    if current_season and current_season.season_end_date:
        season_end = current_season.season_end_date

    # Get last game date
    last_game = Game.query.filter(
        Game.active == 1,
        Game.game_date >= datetime.combine(today, datetime.min.time())
    ).order_by(Game.game_date.desc()).first()

    last_game_date = last_game.game_date.date() if last_game else None

    # Use whichever is later, with a minimum of 60 days out
    min_end = today + timedelta(days=60)
    end_date = max(filter(None, [season_end, last_game_date, min_end]))

    # Get existing blockouts for this profile
    blockouts = UmpireBlockout.get_blocked_dates(profile.id, start_date, end_date)

    # Get upcoming games for this umpire from Assignr
    upcoming_games = []
    if profile.assignr_id:
        upcoming_games = get_umpire_upcoming_games(profile.assignr_id, start_date, end_date)

    # Build calendar data
    # Group by month for display
    calendar_months = build_calendar_months(start_date, end_date, blockouts, upcoming_games)

    return render_template(
        'umpires/availability.html',
        profile=profile,
        accessible_profiles=accessible_profiles,
        calendar_months=calendar_months,
        blockouts=blockouts,
        upcoming_games=upcoming_games,
        start_date=start_date,
        end_date=end_date,
        today=today
    )


@umpires_bp.route('/availability/api/toggle', methods=['POST'])
@login_required
def availability_toggle():
    """Toggle a blockout date on/off (AJAX)."""
    data = request.get_json()
    profile_id = data.get('profile_id')
    date_str = data.get('date')  # YYYY-MM-DD format
    reason = data.get('reason', '')

    if not profile_id or not date_str:
        return jsonify({'error': 'Missing profile_id or date'}), 400

    # Verify access
    accessible_profiles = UmpireProfile.get_accessible_profiles(current_user.ID)
    profile = next((p for p in accessible_profiles if p.id == profile_id), None)

    if not profile:
        return jsonify({'error': 'Profile not accessible'}), 403

    # Parse date
    try:
        block_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Don't allow blocking past dates
    if block_date < date.today():
        return jsonify({'error': 'Cannot block past dates'}), 400

    # Toggle
    if UmpireBlockout.is_blocked(profile_id, block_date):
        UmpireBlockout.clear_blocked(profile_id, block_date)
        is_blocked = False
    else:
        UmpireBlockout.set_blocked(profile_id, block_date, reason if reason else None)
        is_blocked = True

    return jsonify({
        'success': True,
        'date': date_str,
        'is_blocked': is_blocked
    })


@umpires_bp.route('/availability/api/set-range', methods=['POST'])
@login_required
def availability_set_range():
    """Block a range of dates (AJAX)."""
    data = request.get_json()
    profile_id = data.get('profile_id')
    start_str = data.get('start_date')
    end_str = data.get('end_date')
    reason = data.get('reason', '')

    if not profile_id or not start_str or not end_str:
        return jsonify({'error': 'Missing required fields'}), 400

    # Verify access
    accessible_profiles = UmpireProfile.get_accessible_profiles(current_user.ID)
    profile = next((p for p in accessible_profiles if p.id == profile_id), None)

    if not profile:
        return jsonify({'error': 'Profile not accessible'}), 403

    # Parse dates
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    if start_date > end_date:
        return jsonify({'error': 'Start date must be before end date'}), 400

    if start_date < date.today():
        start_date = date.today()

    # Block the range
    count = UmpireBlockout.set_blocked_range(profile_id, start_date, end_date, reason if reason else None)

    return jsonify({
        'success': True,
        'dates_blocked': count
    })


@umpires_bp.route('/availability/api/clear-range', methods=['POST'])
@login_required
def availability_clear_range():
    """Clear blockouts for a range of dates (AJAX)."""
    data = request.get_json()
    profile_id = data.get('profile_id')
    start_str = data.get('start_date')
    end_str = data.get('end_date')

    if not profile_id or not start_str or not end_str:
        return jsonify({'error': 'Missing required fields'}), 400

    # Verify access
    accessible_profiles = UmpireProfile.get_accessible_profiles(current_user.ID)
    profile = next((p for p in accessible_profiles if p.id == profile_id), None)

    if not profile:
        return jsonify({'error': 'Profile not accessible'}), 403

    # Parse dates
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Clear the range
    count = UmpireBlockout.clear_blocked_range(profile_id, start_date, end_date)

    return jsonify({
        'success': True,
        'dates_cleared': count
    })


def get_umpire_upcoming_games(assignr_id, start_date, end_date):
    """Get upcoming games for an umpire from Assignr.

    Returns list of dicts with game info.
    """
    from app.services.assignr_service import get_assignr_service

    games = []

    try:
        assignr = get_assignr_service()
        if not assignr.is_configured():
            return games

        # Get games from Assignr
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        assignr_games = assignr.get_all_games(start_dt, end_dt)

        # Filter to games where this official is assigned
        for game in assignr_games:
            if game.get('is_cancelled'):
                continue

            assignments = game.get('_embedded', {}).get('assignments', []) or []
            for assignment in assignments:
                if assignment.get('accepted') not in [True, 'True']:
                    continue

                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}

                if str(official.get('id')) == str(assignr_id):
                    game_date = game.get('_game_date')
                    if game_date:
                        games.append({
                            'date': game_date.date(),
                            'time': game_date.strftime('%I:%M %p').lstrip('0'),
                            'title': game.get('localized_title', ''),
                            'venue': game.get('venue_name', ''),
                            'position': assignment.get('position', 'Umpire'),
                            'assignr_id': game.get('id')
                        })
                    break  # Found this official, move to next game

    except Exception as e:
        # Log but don't fail
        print(f"Error fetching Assignr games: {e}")

    # Sort by date
    games.sort(key=lambda g: (g['date'], g['time']))
    return games


def build_calendar_months(start_date, end_date, blockouts, upcoming_games):
    """Build calendar data structure for template.

    Returns list of month dicts, each containing weeks of days.
    """
    import calendar

    # Build set of game dates for quick lookup
    game_dates = {g['date'] for g in upcoming_games}

    months = []
    current = start_date.replace(day=1)  # Start at beginning of month

    while current <= end_date:
        year = current.year
        month = current.month
        month_name = current.strftime('%B %Y')

        # Get calendar for this month
        cal = calendar.Calendar(firstweekday=6)  # Sunday first
        weeks = []

        for week in cal.monthdayscalendar(year, month):
            week_days = []
            for day in week:
                if day == 0:
                    week_days.append(None)  # Empty cell
                else:
                    day_date = date(year, month, day)
                    week_days.append({
                        'date': day_date,
                        'day': day,
                        'is_past': day_date < start_date,
                        'is_blocked': day_date in blockouts,
                        'has_game': day_date in game_dates,
                        'is_today': day_date == date.today()
                    })
            weeks.append(week_days)

        months.append({
            'name': month_name,
            'year': year,
            'month': month,
            'weeks': weeks
        })

        # Move to next month
        if month == 12:
            current = date(year + 1, 1, 1)
        else:
            current = date(year, month + 1, 1)

    return months
