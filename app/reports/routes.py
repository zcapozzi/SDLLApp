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
from app.utils.tracking import log_authenticated_view
from app.utils.auth import get_effective_user


@reports_bp.route('/')
@login_required
def index():
    """Reports index page - filtered by user role access.

    Supports view_as parameter for admins to test as other users.
    """
    log_authenticated_view('reports_index')

    # Use effective user for view_as support
    effective_user = get_effective_user()

    # Get current season for pitching reports
    current_season = LeagueSeason.query.filter_by(active=1).order_by(
        LeagueSeason.year.desc(),
        LeagueSeason.is_spring.desc()
    ).first()

    current_year = current_season.year if current_season else None
    current_is_spring = current_season.is_spring if current_season else 0

    # Get leagues that track pitching stats - filtered by access
    pitching_leagues = []
    has_admin_access = effective_user.has_role('admin', 'BB_VP', 'SB_VP', 'coaching_coordinator')

    all_pitching_leagues = League.query.filter(
        League.active == 1,
        League.track_pitching_stats == 1
    ).order_by(League.sort_order, League.display_name).all()

    if has_admin_access:
        # Admins/VPs see all pitching leagues
        pitching_leagues = all_pitching_leagues
    elif current_year:
        # Coaches only see leagues where they have a team
        coach_user = CoachUser.get_by_user(effective_user.ID)
        if coach_user:
            # Get league IDs where this coach has a team in the current season
            team_assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()
            team_ids = [a.team_id for a in team_assignments]

            if team_ids:
                coach_league_ids = db.session.query(TeamSeason.league_id).filter(
                    TeamSeason.team_ID.in_(team_ids),
                    TeamSeason.year == current_year,
                    TeamSeason.is_spring == current_is_spring,
                    TeamSeason.active == 1
                ).distinct().all()
                coach_league_ids = {lid[0] for lid in coach_league_ids}

                # Filter pitching leagues to only those the coach has access to
                pitching_leagues = [lg for lg in all_pitching_leagues if lg.ID in coach_league_ids]

    return render_template(
        'reports/index.html',
        pitching_leagues=pitching_leagues,
        current_year=current_year,
        current_is_spring=current_is_spring,
        effective_user=effective_user
    )


@reports_bp.route('/recent-changes')
@login_required
def recent_changes():
    """View recent game changes with filters.

    Access: Admin, scheduler, VP roles only.
    """
    if not current_user.can_edit_schedule():
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('main.dashboard'))

    log_authenticated_view('reports_recent_changes')

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
    log_authenticated_view('reports_schedule_downloads')

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
        # Query league_id and join with League to get display_name
        saved_league_rows = db.session.query(League.display_name).join(
            Game, Game.league_id == League.ID
        ).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.active == 1,
            Game.game_type.in_(['regular', 'playoff']),
            Game.game_date.isnot(None)
        ).distinct().all()
        saved_leagues = set(l[0] for l in saved_league_rows if l[0])

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
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f'pitching_report accessed: year={year}, is_spring={is_spring}, league={league}, user={current_user.ID}')

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
    logger.info(f'pitching_report access check: user={current_user.ID}, has_admin_access={has_admin_access}')

    if not has_admin_access:
        # Check if user coaches a team in this league
        has_team = _user_has_team_in_league(current_user.ID, league_id, year, is_spring)
        logger.info(f'pitching_report coach check: user={current_user.ID}, league_id={league_id}, has_team={has_team}')
        if not has_team:
            flash('You do not have permission to view this report.', 'error')
            return redirect(url_for('reports.index'))

    log_authenticated_view('reports_pitching', f'{year}/{is_spring}/{league}')

    # Get pitching data
    pitching_data = PitchingReportService.get_league_pitching_summary(year, is_spring, league_id)

    # Get league display name for the season
    season_name = 'Spring' if is_spring else 'Fall'
    league_display = league_obj.get_seasonal_name(is_spring)

    from app.models.pitching_stats import PitchingStats

    return render_template(
        'reports/pitching_report.html',
        pitching_data=pitching_data,
        league=league_obj,
        league_display=league_display,
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        format_innings_from_outs=PitchingStats.format_innings_from_outs,
        format_strike_pct=PitchingReportService.format_strike_pct
    )


@reports_bp.route('/standings')
@login_required
def standings():
    """League standings page with proposed playoff brackets.

    Shows standings for all leagues, defaulting to the user's league if they're a coach.
    Includes projected playoff bracket based on league's tournament format.
    """
    from app.services.standings_service import StandingsService
    from app.models.org_season import OrgSeason

    log_authenticated_view('reports_standings')

    effective_user = get_effective_user()

    # Get current season
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'error')
        return redirect(url_for('reports.index'))

    year = request.args.get('year', current_season.year, type=int)
    is_spring = request.args.get('is_spring', current_season.is_spring, type=int)

    # Get all active leagues for this season
    league_seasons = LeagueSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).all()

    # Build league info with standings
    leagues_data = []
    user_league_id = None

    # Find user's league if they're a coach
    coach_user = CoachUser.get_by_user(effective_user.ID)
    if coach_user:
        team_assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()
        team_ids = [a.team_id for a in team_assignments]
        if team_ids:
            user_team = TeamSeason.query.filter(
                TeamSeason.team_ID.in_(team_ids),
                TeamSeason.year == year,
                TeamSeason.is_spring == is_spring,
                TeamSeason.active == 1
            ).first()
            if user_team:
                user_league_id = user_team.league_id

    # Check if user has admin access (can see all leagues)
    has_admin_access = effective_user.has_role('admin', 'scheduler', 'BB_VP', 'SB_VP', 'coaching_coordinator')

    for ls in league_seasons:
        if not ls.league_rel:
            continue

        league = ls.league_rel

        # Get standings for this league
        standings_list = StandingsService.get_league_standings(year, is_spring, league.ID)

        # Generate bracket data based on playoff format
        bracket_data = _generate_bracket(standings_list, ls)

        leagues_data.append({
            'league': league,
            'league_season': ls,
            'standings': standings_list,
            'has_ties': StandingsService.has_ties(standings_list),
            'bracket': bracket_data,
            'is_user_league': league.ID == user_league_id
        })

    # Sort leagues by age_rank (youngest first)
    leagues_data.sort(key=lambda x: (x['league'].age_rank or 99, x['league'].display_name))

    # Get selected league from URL param, or default to user's league
    selected_league_id = request.args.get('league', type=int)
    if not selected_league_id and user_league_id:
        selected_league_id = user_league_id

    season_name = 'Spring' if is_spring else 'Fall'

    return render_template(
        'reports/standings.html',
        leagues_data=leagues_data,
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        selected_league_id=selected_league_id,
        has_admin_access=has_admin_access,
        user_league_id=user_league_id
    )


def _generate_bracket(standings: list, league_season: LeagueSeason) -> dict:
    """Generate playoff bracket data based on standings and playoff format.

    Args:
        standings: List of TeamStanding objects
        league_season: LeagueSeason with playoff configuration

    Returns:
        Dict with bracket structure for template rendering
    """
    if not standings or league_season.playoff_format == 'none':
        return None

    # Determine number of playoff teams
    num_teams = league_season.playoff_teams or len(standings)
    if num_teams > len(standings):
        num_teams = len(standings)

    # Get qualifying teams
    qualifying_teams = standings[:num_teams]

    bracket = {
        'format': league_season.playoff_format,
        'format_display': dict(LeagueSeason.PLAYOFF_FORMATS).get(league_season.playoff_format, 'Unknown'),
        'num_teams': num_teams,
        'teams': [{'seed': i + 1, 'team': t.team, 'record': f'{t.wins}-{t.losses}'} for i, t in enumerate(qualifying_teams)],
        'rounds': []
    }

    if league_season.playoff_format == 'single_elimination':
        bracket['rounds'] = _generate_single_elimination_rounds(num_teams, qualifying_teams)
    elif league_season.playoff_format == 'double_elimination':
        bracket['rounds'] = _generate_double_elimination_rounds(num_teams, qualifying_teams)
    elif league_season.playoff_format == 'round_robin_knockout':
        bracket['rounds'] = _generate_round_robin_knockout_rounds(num_teams, qualifying_teams)

    return bracket


def _generate_single_elimination_rounds(num_teams: int, teams: list) -> list:
    """Generate single elimination bracket rounds.

    Standard seeding: 1v8, 4v5, 3v6, 2v7 (for 8 teams)
    """
    rounds = []

    # Generate first round matchups with proper seeding
    first_round = []

    if num_teams == 2:
        first_round.append({'high_seed': 1, 'low_seed': 2, 'round_name': 'Championship'})
    elif num_teams <= 4:
        # 1v4, 2v3 → winners play in championship
        first_round.append({'high_seed': 1, 'low_seed': 4, 'round_name': 'Semifinals'})
        first_round.append({'high_seed': 2, 'low_seed': 3, 'round_name': 'Semifinals'})
        rounds.append({'name': 'Semifinals', 'matchups': first_round})
        rounds.append({'name': 'Championship', 'matchups': [{'high_seed': 'W1', 'low_seed': 'W2'}]})
        return rounds
    elif num_teams <= 8:
        # Standard 8-team bracket: 1v8, 4v5, 3v6, 2v7
        matchups = [(1, 8), (4, 5), (3, 6), (2, 7)]
        for high, low in matchups:
            if low <= num_teams:
                first_round.append({'high_seed': high, 'low_seed': low})
            else:
                # Bye for high seed
                first_round.append({'high_seed': high, 'low_seed': 'BYE'})
        rounds.append({'name': 'Quarterfinals', 'matchups': first_round})
        rounds.append({'name': 'Semifinals', 'matchups': [
            {'high_seed': 'W1', 'low_seed': 'W4'},
            {'high_seed': 'W2', 'low_seed': 'W3'}
        ]})
        rounds.append({'name': 'Championship', 'matchups': [{'high_seed': 'SF1', 'low_seed': 'SF2'}]})
        return rounds

    # Default case
    rounds.append({'name': 'First Round', 'matchups': first_round})
    return rounds


def _generate_double_elimination_rounds(num_teams: int, teams: list) -> list:
    """Generate double elimination bracket structure."""
    rounds = []

    # Winners bracket first round
    first_round = []
    if num_teams <= 4:
        first_round = [
            {'high_seed': 1, 'low_seed': 4, 'bracket': 'winners'},
            {'high_seed': 2, 'low_seed': 3, 'bracket': 'winners'}
        ]
    elif num_teams <= 8:
        matchups = [(1, 8), (4, 5), (3, 6), (2, 7)]
        for high, low in matchups:
            if low <= num_teams:
                first_round.append({'high_seed': high, 'low_seed': low, 'bracket': 'winners'})
            else:
                first_round.append({'high_seed': high, 'low_seed': 'BYE', 'bracket': 'winners'})

    rounds.append({'name': 'Winners Round 1', 'matchups': first_round, 'bracket': 'winners'})
    rounds.append({'name': 'Losers Round 1', 'matchups': [], 'bracket': 'losers', 'note': 'Losers from Winners R1'})
    rounds.append({'name': 'Winners Finals', 'matchups': [], 'bracket': 'winners'})
    rounds.append({'name': 'Losers Finals', 'matchups': [], 'bracket': 'losers'})
    rounds.append({'name': 'Championship', 'matchups': [], 'note': 'Winners Finals winner vs Losers Finals winner'})

    return rounds


def _generate_round_robin_knockout_rounds(num_teams: int, teams: list) -> list:
    """Generate round robin + knockout bracket structure."""
    rounds = []

    # Round robin phase
    rounds.append({
        'name': 'Round Robin',
        'type': 'round_robin',
        'note': f'All {num_teams} teams play each other once. Top 4 advance to knockout.'
    })

    # Knockout phase (top 4)
    rounds.append({
        'name': 'Semifinals',
        'matchups': [
            {'high_seed': '#1 Seed', 'low_seed': '#4 Seed'},
            {'high_seed': '#2 Seed', 'low_seed': '#3 Seed'}
        ]
    })
    rounds.append({
        'name': 'Championship',
        'matchups': [{'high_seed': 'SF1 Winner', 'low_seed': 'SF2 Winner'}]
    })

    return rounds
