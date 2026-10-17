"""Report routes for viewing game changes and audit history"""

import csv
import io
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from app.reports import reports_bp
from app.models.game_change import GameChange
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.user import User
from app.models.umpire_assignment import UmpireAssignment
from app.models.schedule_proposal import ScheduleProposal
from app.models.league_season import LeagueSeason
from app.models.league import League
from app.models.field import Field
from app.models.coach import CoachUser, CoachSeason
from app.extensions import db
from app.utils.league_helpers import get_league_id_from_request, get_league_id_from_param


@reports_bp.route('/')
@login_required
def index():
    """Reports index page"""
    # Get current season for pitching reports
    current_season = LeagueSeason.query.filter_by(active=1).order_by(
        LeagueSeason.year.desc(),
        LeagueSeason.is_spring.desc()
    ).first()

    current_year = current_season.year if current_season else None
    current_is_spring = current_season.is_spring if current_season else 0

    # Get leagues that track pitching stats
    pitching_leagues = League.query.filter(
        League.active == 1,
        League.track_pitching_stats == 1
    ).order_by(League.sort_order, League.display_name).all()

    return render_template(
        'reports/index.html',
        pitching_leagues=pitching_leagues,
        current_year=current_year,
        current_is_spring=current_is_spring
    )


@reports_bp.route('/recent-changes')
@login_required
def recent_changes():
    """View recent game changes with filters"""
    from app.models.league import League
    from sqlalchemy.orm import joinedload

    # Get filter parameters
    days = request.args.get('days', 7, type=int)
    league_id = request.args.get('league_id', type=int)
    change_type = request.args.get('change_type')
    changed_by = request.args.get('changed_by', type=int)

    # Build query with eager loading for league
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = GameChange.query.options(
        joinedload(GameChange.league_rel)
    ).filter(GameChange.changed_at >= cutoff)

    if league_id:
        query = query.filter(GameChange.league_id == league_id)
    if change_type:
        query = query.filter(GameChange.change_type == change_type)
    if changed_by:
        query = query.filter(GameChange.changed_by == changed_by)

    changes = query.order_by(GameChange.changed_at.desc()).limit(200).all()

    # Get filter options - all leagues that have changes
    league_ids_with_changes = db.session.query(GameChange.league_id).distinct().filter(
        GameChange.league_id.isnot(None)
    ).all()
    league_ids = [l[0] for l in league_ids_with_changes if l[0]]
    leagues = League.query.filter(League.ID.in_(league_ids)).order_by(League.display_name).all() if league_ids else []

    users = User.query.filter(User.role.in_(['admin', 'scheduler'])).all()

    return render_template(
        'reports/recent_changes.html',
        changes=changes,
        leagues=leagues,
        users=users,
        current_filters={
            'days': days,
            'league_id': league_id,
            'change_type': change_type,
            'changed_by': changed_by
        }
    )


@reports_bp.route('/game/<int:game_id>/history')
@login_required
def game_history(game_id):
    """View change history for a specific game"""
    game = Game.query.get_or_404(game_id)
    changes = GameChange.get_for_game(game_id)

    # Get team names for display
    home_team_name = 'TBD'
    away_team_name = 'TBD'
    if game.home_ID:
        from app.models.team import TeamSeason
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.scheduler_display_name
    if game.away_ID:
        from app.models.team import TeamSeason
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.scheduler_display_name

    return render_template(
        'reports/game_history.html',
        game=game,
        changes=changes,
        home_team_name=home_team_name,
        away_team_name=away_team_name
    )


@reports_bp.route('/umpire-changes')
@login_required
def umpire_changes():
    """View changes affecting games with umpire assignments"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get filter parameters
    umpire_id = request.args.get('umpire_id', type=int)
    days = request.args.get('days', 7, type=int)

    # Get umpires for filter dropdown (handles pipe-delimited roles)
    umpires = User.query.filter(
        db.or_(
            User.role == 'umpire',
            User.role.like('umpire|%'),
            User.role.like('%|umpire'),
            User.role.like('%|umpire|%')
        )
    ).all()

    if not umpire_id and umpires:
        # Default to first umpire
        umpire_id = umpires[0].user_id

    # Get game IDs assigned to this umpire
    if umpire_id:
        assignments = UmpireAssignment.query.filter_by(umpire_id=umpire_id).all()
        game_ids = [a.game_id for a in assignments]

        # Get changes for those games
        cutoff = datetime.utcnow() - timedelta(days=days)
        changes = GameChange.query.filter(
            GameChange.game_id.in_(game_ids),
            GameChange.changed_at >= cutoff
        ).order_by(GameChange.changed_at.desc()).all()
    else:
        changes = []

    return render_template(
        'reports/umpire_changes.html',
        changes=changes,
        umpires=umpires,
        current_umpire_id=umpire_id,
        days=days
    )


@reports_bp.route('/my-changes')
@login_required
def my_changes():
    """View changes made by the current user"""
    changes = GameChange.get_by_user(current_user.user_id, limit=100)

    return render_template(
        'reports/my_changes.html',
        changes=changes
    )


@reports_bp.route('/schedule-downloads')
@login_required
def schedule_downloads():
    """Page for downloading league schedules as CSV files."""
    # Get available seasons
    from sqlalchemy import func

    # Check for seasons with either proposal data or saved games
    seasons_with_games = db.session.query(
        Game.year, Game.is_spring
    ).filter(Game.active == 1).distinct().all()

    seasons_with_proposals = db.session.query(
        ScheduleProposal.year, ScheduleProposal.is_spring
    ).filter(ScheduleProposal.status.in_(['draft', 'review', 'accepted'])).distinct().all()

    # Combine unique seasons
    all_seasons = set(seasons_with_games) | set(seasons_with_proposals)
    seasons = sorted(all_seasons, key=lambda x: (x[0], x[1]), reverse=True)

    # Get current season (most recent active LeagueSeason)
    current_season = db.session.query(
        LeagueSeason.year,
        LeagueSeason.is_spring
    ).filter_by(active=1).order_by(
        LeagueSeason.year.desc(),
        LeagueSeason.is_spring.desc()
    ).first()

    # Use URL params if provided, otherwise default to current season
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)

    if year is None:
        if current_season:
            year, is_spring = current_season.year, current_season.is_spring
        elif seasons:
            # Fallback to most recent season with data
            year, is_spring = seasons[0]

    # Get leagues for this season
    leagues_data = []
    if year is not None and is_spring is not None:
        # Check for proposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)

        # Get leagues from saved games (games and scrimmages, with dates)
        saved_leagues = db.session.query(Game.league).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.active == 1,
            Game.game_type.in_(['regular', 'playoff']),
            Game.game_date.isnot(None)
        ).distinct().all()
        saved_leagues = set(l[0] for l in saved_leagues if l[0])

        # Get leagues from proposal (games and scrimmages, with dates)
        proposal_leagues = set()
        if proposal:
            for game in proposal.games:
                game_type = game.get('game_type', 'regular')
                if game_type in ('practice', 'division_practice'):
                    continue
                if game.get('is_league_practice'):
                    continue
                if not game.get('game_date'):
                    continue
                if game.get('league'):
                    proposal_leagues.add(game['league'])

        # Combine and add info
        all_leagues = sorted(saved_leagues | proposal_leagues)
        for league_name in all_leagues:
            # Look up league_id for filtering
            league_id = get_league_id_from_param(league_name)

            # Count games from saved (games and scrimmages, with dates)
            query = Game.query.filter(
                Game.year == year,
                Game.is_spring == is_spring,
                Game.active == 1,
                Game.game_type.in_(['regular', 'playoff']),
                Game.game_date.isnot(None)
            )
            if league_id:
                query = query.filter(Game.league_id == league_id)
            saved_count = query.count()

            # Count games from proposal (games and scrimmages, with dates)
            proposal_count = 0
            if proposal:
                for g in proposal.games:
                    if g.get('league') != league_name:
                        continue
                    game_type = g.get('game_type', 'regular')
                    if game_type in ('practice', 'division_practice'):
                        continue
                    if g.get('is_league_practice'):
                        continue
                    if not g.get('game_date'):
                        continue
                    proposal_count += 1

            # Use saved if available, otherwise proposal
            game_count = saved_count if saved_count > 0 else proposal_count

            # Get seasonal display name
            league_obj = League.get_by_name(league_name)
            if league_obj:
                display_name = league_obj.get_seasonal_name(is_spring)
            else:
                display_name = league_name

            leagues_data.append({
                'name': league_name,  # Internal name for URL
                'display_name': display_name,  # Seasonal display name
                'game_count': game_count
            })

    # Pass active season info for highlighting
    active_year = current_season.year if current_season else None
    active_is_spring = current_season.is_spring if current_season else None

    return render_template(
        'reports/schedule_downloads.html',
        seasons=seasons,
        leagues=leagues_data,
        current_year=year,
        current_is_spring=is_spring,
        active_year=active_year,
        active_is_spring=active_is_spring
    )


@reports_bp.route('/schedule-download/<int:year>/<int:is_spring>/<league>')
@login_required
def download_league_schedule(year, is_spring, league):
    """Download game schedule for a specific league as CSV.

    Games and scrimmages (no practices). Uses saved games if available, otherwise proposal.
    Only includes games with dates set.
    """
    # Convert league name/ID to league_id for filtering
    league_id = get_league_id_from_param(league)

    events = []

    # Check for saved games first (only those with dates)
    query = Game.query.filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff']),
        Game.game_date.isnot(None)
    )
    if league_id:
        query = query.filter(Game.league_id == league_id)
    saved_games = query.order_by(Game.game_date).all()

    if saved_games:
        # Use saved games
        for game in saved_games:
            date_str = game.game_date.strftime('%Y-%m-%d')
            time_str = game.game_date.strftime('%I:%M %p')
            day_str = game.game_date.strftime('%A')

            field_name = game.field_name

            # Determine game type for display
            if game.is_scrimmage:
                game_type_display = 'Scrimmage'
            elif game.game_type == 'playoff':
                game_type_display = 'Playoff'
            else:
                game_type_display = 'Regular'

            # Get team names
            home_team = ''
            away_team = ''
            if game.home_ID:
                home_team_obj = TeamSeason.query.get(game.home_ID)
                if home_team_obj:
                    home_team = home_team_obj.scheduler_display_name
            if game.away_ID:
                away_team_obj = TeamSeason.query.get(game.away_ID)
                if away_team_obj:
                    away_team = away_team_obj.scheduler_display_name

            events.append({
                'date': date_str,
                'day': day_str,
                'time': time_str,
                'type': game_type_display,
                'field': field_name,
                'home_team': home_team,
                'away_team': away_team
            })
    else:
        # Fall back to proposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)
        if proposal:
            for game in proposal.games:
                if game.get('league') != league:
                    continue

                game_type = game.get('game_type', 'regular')

                # Skip practices only (include scrimmages)
                if game_type in ('practice', 'division_practice'):
                    continue
                if game.get('is_league_practice'):
                    continue

                # Skip games without dates
                game_date_str = game.get('game_date', '')
                if not game_date_str:
                    continue

                # Parse date/time
                try:
                    dt = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d')
                    time_str = dt.strftime('%I:%M %p')
                    day_str = dt.strftime('%A')
                except (ValueError, AttributeError):
                    continue  # Skip if we can't parse the date

                # Determine game type for display
                if game_type == 'scrimmage':
                    game_type_display = 'Scrimmage'
                elif game_type == 'playoff':
                    game_type_display = 'Playoff'
                else:
                    game_type_display = 'Regular'

                field_name = game.get('field_name') or game.get('location') or ''
                home_team = game.get('home_team_name', '')
                away_team = game.get('away_team_name', '')

                events.append({
                    'date': date_str,
                    'day': day_str,
                    'time': time_str,
                    'type': game_type_display,
                    'field': field_name,
                    'home_team': home_team,
                    'away_team': away_team
                })

    # Sort events by date and time
    events.sort(key=lambda e: (e['date'], e['time']))

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['Date', 'Day', 'Time', 'Type', 'Field', 'Home Team', 'Away Team'])

    # Data rows
    for event in events:
        writer.writerow([
            event['date'],
            event['day'],
            event['time'],
            event['type'],
            event['field'],
            event['home_team'],
            event['away_team']
        ])

    # Create response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    season_name = 'Spring' if is_spring else 'Fall'
    filename = f"{league}_{season_name}_{year}_schedule_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )


def _user_has_team_in_league(user_id: int, league_id: int, year: int, is_spring: int) -> bool:
    """Check if user coaches any team in the specified league/season.

    Args:
        user_id: User ID to check
        league_id: League ID
        year: Season year
        is_spring: 1 for spring, 0 for fall

    Returns:
        True if user coaches a team in the league
    """
    # Get coach record for this user
    coach_user = CoachUser.get_by_user(user_id)
    if not coach_user:
        return False

    # Get all team assignments for this coach
    team_assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()
    if not team_assignments:
        return False

    team_ids = [a.team_id for a in team_assignments]

    # Check if any of those teams are in this league/season
    matching_team = TeamSeason.query.filter(
        TeamSeason.team_ID.in_(team_ids),
        TeamSeason.league_id == league_id,
        TeamSeason.year == year,
        TeamSeason.is_spring == is_spring,
        TeamSeason.active == 1
    ).first()

    return matching_team is not None


@reports_bp.route('/pitching/<int:year>/<int:is_spring>/<league>')
@login_required
def pitching_report(year, is_spring, league):
    """Pitching report for a league.

    Shows aggregated pitching stats for all teams/pitchers in the league.

    Access control:
    - Admins can view any league
    - BB_VP, SB_VP, coaching_coordinator can view any league
    - Coaches can only view leagues where they have a team
    """
    from app.services.pitching_report_service import PitchingReportService

    # Get league info
    league_id = get_league_id_from_param(league)
    if not league_id:
        flash('League not found.', 'error')
        return redirect(url_for('reports.index'))

    league_obj = League.query.get(league_id)
    if not league_obj:
        flash('League not found.', 'error')
        return redirect(url_for('reports.index'))

    # Check if league tracks pitching stats
    if not league_obj.captures_pitching_data:
        flash(f'{league_obj.display_name} does not track pitching statistics.', 'warning')
        return redirect(url_for('reports.index'))

    # Access control
    has_admin_access = current_user.has_role('admin', 'BB_VP', 'SB_VP', 'coaching_coordinator')

    if not has_admin_access:
        # Check if user coaches a team in this league
        if not _user_has_team_in_league(current_user.ID, league_id, year, is_spring):
            flash('You do not have permission to view this report.', 'error')
            return redirect(url_for('reports.index'))

    # Get pitching data
    pitching_data = PitchingReportService.get_league_pitching_summary(year, is_spring, league_id)

    # Get league display name for the season
    season_name = 'Spring' if is_spring else 'Fall'
    league_display = league_obj.get_seasonal_name(is_spring)

    return render_template(
        'reports/pitching_report.html',
        pitching_data=pitching_data,
        league=league_obj,
        league_display=league_display,
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        format_innings=PitchingReportService.format_innings,
        format_sb_ratio=PitchingReportService.format_strike_ball_ratio
    )
