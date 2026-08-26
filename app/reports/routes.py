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
from app.extensions import db


@reports_bp.route('/')
@login_required
def index():
    """Reports index page"""
    return render_template('reports/index.html')


@reports_bp.route('/recent-changes')
@login_required
def recent_changes():
    """View recent game changes with filters"""
    # Get filter parameters
    days = request.args.get('days', 7, type=int)
    league = request.args.get('league')
    change_type = request.args.get('change_type')
    changed_by = request.args.get('changed_by', type=int)

    # Build query
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = GameChange.query.filter(GameChange.changed_at >= cutoff)

    if league:
        query = query.filter(GameChange.league == league)
    if change_type:
        query = query.filter(GameChange.change_type == change_type)
    if changed_by:
        query = query.filter(GameChange.changed_by == changed_by)

    changes = query.order_by(GameChange.changed_at.desc()).limit(200).all()

    # Get filter options
    leagues = db.session.query(GameChange.league).distinct().filter(
        GameChange.league.isnot(None)
    ).all()
    leagues = sorted([l[0] for l in leagues if l[0]])

    users = User.query.filter(User.role.in_(['admin', 'scheduler'])).all()

    return render_template(
        'reports/recent_changes.html',
        changes=changes,
        leagues=leagues,
        users=users,
        current_filters={
            'days': days,
            'league': league,
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
            # Count games from saved (games and scrimmages, with dates)
            saved_count = Game.query.filter(
                Game.year == year,
                Game.is_spring == is_spring,
                Game.league == league_name,
                Game.active == 1,
                Game.game_type.in_(['regular', 'playoff']),
                Game.game_date.isnot(None)
            ).count()

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
    events = []

    # Check for saved games first (only those with dates)
    saved_games = Game.query.filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league == league,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff']),
        Game.game_date.isnot(None)
    ).order_by(Game.game_date).all()

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
