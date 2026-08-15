"""Game management routes"""

from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.field import Field
from app.models.organization import Organization
from app.extensions import db
from app.utils.logging import SDLLLogger

games_bp = Blueprint('games', __name__)
logger = SDLLLogger('games')


@games_bp.route('/')
@login_required
def index():
    """List games with filtering"""
    # Get filter parameters
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)
    league = request.args.get('league')
    status = request.args.get('status')
    game_mode = request.args.get('game_mode', 'games')  # 'all', 'games', 'practices'

    # Build query
    query = Game.query.filter(Game.active == 1)

    if year:
        query = query.filter(Game.year == year)
    if is_spring is not None:
        query = query.filter(Game.is_spring == is_spring)
    if league:
        query = query.filter(Game.league == league)
    if status:
        query = query.filter(Game.status == status)

    # Filter by game mode (games/scrimmages vs practices)
    if game_mode == 'games':
        # Games and scrimmages have two teams (away_ID is not null)
        query = query.filter(Game.away_ID.isnot(None))
    elif game_mode == 'practices':
        # Practices have only one team (away_ID is null)
        query = query.filter(Game.away_ID.is_(None))
    # 'all' shows everything

    games = query.order_by(Game.game_date.desc()).limit(100).all()

    # Get filter options
    leagues = db.session.query(Game.league).distinct().filter(
        Game.league.isnot(None)
    ).all()
    leagues = [l[0] for l in leagues if l[0]]

    years = db.session.query(Game.year).distinct().filter(
        Game.year.isnot(None)
    ).order_by(Game.year.desc()).all()
    years = [y[0] for y in years]

    return render_template(
        'games/index.html',
        games=games,
        leagues=leagues,
        years=years,
        current_filters={
            'year': year,
            'is_spring': is_spring,
            'league': league,
            'status': status,
            'game_mode': game_mode
        }
    )


@games_bp.route('/<int:game_id>')
@login_required
def view(game_id):
    """View a single game"""
    game = Game.query.get_or_404(game_id)
    return render_template('games/view.html', game=game)


@games_bp.route('/upcoming')
@login_required
def upcoming():
    """View upcoming games"""
    games = Game.get_upcoming(limit=50)
    return render_template('games/upcoming.html', games=games)


@games_bp.route('/<int:year>/<int:is_spring>/manage', methods=['GET', 'POST'])
@login_required
def manage(year, is_spring):
    """Manage games for a season - allows editing individual games"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to edit games.', 'error')
        return redirect(url_for('games.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'
    anchor = None

    if request.method == 'POST':
        action = request.form.get('action')
        game_id = request.form.get('game_id')

        if game_id:
            game = Game.query.get(int(game_id))
            if game:
                anchor = f'game-{game_id}'

                if action == 'update_game':
                    # Parse date and time
                    game_date_str = request.form.get('game_date')
                    game_time_str = request.form.get('game_time')
                    if game_date_str and game_time_str:
                        game.game_date = datetime.strptime(
                            f'{game_date_str} {game_time_str}', '%Y-%m-%d %H:%M'
                        )
                    elif game_date_str:
                        game.game_date = datetime.strptime(game_date_str, '%Y-%m-%d')

                    # Update location
                    game.location = request.form.get('location')

                    # Update teams
                    home_id = request.form.get('home_id')
                    away_id = request.form.get('away_id')
                    game.home_ID = int(home_id) if home_id else None
                    game.away_ID = int(away_id) if away_id else None

                    # Update game type and status
                    game.game_type = request.form.get('game_type', 'regular')
                    game.status = request.form.get('status', 'scheduled')
                    game.is_scrimmage = 1 if request.form.get('is_scrimmage') else 0
                    game.no_time_limit = 1 if request.form.get('no_time_limit') else 0

                    # If converting to practice, clear away team
                    if game.game_type == 'practice':
                        game.away_ID = None

                    db.session.commit()
                    logger.info(f'Updated game {game_id}: {game.home_team.computed_display_name if game.home_team else "TBD"} vs {game.away_team.computed_display_name if game.away_team else "N/A"}')
                    flash('Game updated successfully.', 'success')

                elif action == 'delete_game':
                    game.active = 0
                    db.session.commit()
                    logger.info(f'Deleted game {game_id}')
                    flash('Game deleted.', 'success')
                    anchor = None  # Don't scroll to deleted game

        redirect_url = url_for('games.manage', year=year, is_spring=is_spring)
        if anchor:
            redirect_url += f'#{anchor}'
        return redirect(redirect_url)

    # GET - show management page
    # Get filter parameters
    league = request.args.get('league')
    game_mode = request.args.get('game_mode', 'all')

    # Build query
    query = Game.query.filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring
    )

    if league:
        query = query.filter(Game.league == league)

    if game_mode == 'games':
        query = query.filter(Game.away_ID.isnot(None))
    elif game_mode == 'practices':
        query = query.filter(Game.away_ID.is_(None))

    games = query.order_by(Game.game_date, Game.location).all()

    # Get leagues for filter dropdown
    leagues = db.session.query(Game.league).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league.isnot(None)
    ).distinct().all()
    leagues = [l[0] for l in leagues if l[0]]

    # Get all teams for the dropdowns (including external teams)
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    # Get all fields for location dropdown
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    return render_template(
        'games/manage.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        games=games,
        teams=teams,
        fields=fields,
        leagues=leagues,
        current_filters={
            'league': league,
            'game_mode': game_mode
        }
    )


@games_bp.route('/external-teams', methods=['GET', 'POST'])
@login_required
def external_teams():
    """Manage external organizations and their teams"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage external teams.', 'error')
        return redirect(url_for('games.index'))

    anchor = None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_organization':
            name = request.form.get('name', '').strip()
            short_name = request.form.get('short_name', '').strip()
            location = request.form.get('location', '').strip()

            if name:
                org = Organization(
                    name=name,
                    short_name=short_name or None,
                    location=location or None,
                    is_home_org=0
                )
                db.session.add(org)
                db.session.commit()
                logger.info(f'Created organization: {name}')
                flash(f'Added organization: {name}', 'success')
                anchor = f'org-{org.ID}'

        elif action == 'add_team':
            org_id = int(request.form.get('org_id'))
            year = int(request.form.get('year'))
            is_spring = int(request.form.get('is_spring'))
            team_name = request.form.get('team_name', '').strip()
            league = request.form.get('league', '').strip()

            if org_id and team_name:
                team = TeamSeason(
                    active=1,
                    year=year,
                    is_spring=is_spring,
                    league=league or 'External',
                    display_name=team_name,
                    team_name=team_name,
                    organization_id=org_id,
                    is_placeholder=0
                )
                db.session.add(team)
                db.session.commit()
                logger.info(f'Created external team: {team_name}')
                flash(f'Added team: {team_name}', 'success')
                anchor = f'org-{org_id}'

        elif action == 'delete_organization':
            org_id = int(request.form.get('org_id'))
            org = Organization.query.get(org_id)
            if org and not org.is_home_org:
                org.active = 0
                db.session.commit()
                logger.info(f'Deleted organization: {org.name}')
                flash(f'Deleted organization: {org.name}', 'success')

        redirect_url = url_for('games.external_teams')
        if anchor:
            redirect_url += f'#{anchor}'
        return redirect(redirect_url)

    # GET - show external teams management
    organizations = Organization.get_all_active()

    # Get current season info for team creation
    from app.models.league_season import LeagueSeason
    current_season = db.session.query(
        LeagueSeason.year,
        LeagueSeason.is_spring
    ).filter_by(active=1).order_by(
        LeagueSeason.year.desc(),
        LeagueSeason.is_spring.desc()
    ).first()

    return render_template(
        'games/external_teams.html',
        organizations=organizations,
        current_year=current_season.year if current_season else 2026,
        current_is_spring=current_season.is_spring if current_season else 0
    )


@games_bp.route('/<int:year>/<int:is_spring>/calendar')
@login_required
def calendar(year, is_spring):
    """Calendar view of games for a season"""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get week parameter (ISO week number) or default to current/opening week
    week_param = request.args.get('week')

    # Get league filter
    league = request.args.get('league')

    # Check if there's a proposal for this season
    from app.models.schedule_proposal import ScheduleProposal
    proposal = ScheduleProposal.get_for_season(year, is_spring)
    has_proposal = proposal is not None

    # Determine the date range for this season
    from app.models.league_season import LeagueSeason
    configs = LeagueSeason.get_by_season(year, is_spring)

    # Find earliest opening day across all leagues
    opening_dates = [c.opening_day_date for c in configs if c.opening_day_date]
    if opening_dates:
        season_start = min(opening_dates)
    else:
        # Default to a reasonable start date
        season_start = date(year, 3 if is_spring else 9, 1)

    # Calculate current week
    today = date.today()
    if week_param:
        # Parse week parameter (format: YYYY-WW)
        try:
            week_year, week_num = week_param.split('-')
            # Get Monday of that week
            week_start = datetime.strptime(f'{week_year}-W{week_num}-1', '%G-W%V-%u').date()
        except (ValueError, AttributeError):
            week_start = today - timedelta(days=today.weekday())
    else:
        # Default to current week if in season, otherwise opening week
        if season_start <= today:
            week_start = today - timedelta(days=today.weekday())
        else:
            week_start = season_start - timedelta(days=season_start.weekday())

    week_end = week_start + timedelta(days=6)

    # Build week days with games
    week_days = []

    # If there's a proposal, create a lookup of proposed games by date
    proposed_games_by_date = {}
    if has_proposal:
        for pg in proposal.games:
            if pg.get('game_date'):
                try:
                    pg_date = datetime.fromisoformat(pg['game_date']).date()
                    if pg_date not in proposed_games_by_date:
                        proposed_games_by_date[pg_date] = []
                    proposed_games_by_date[pg_date].append(pg)
                except (ValueError, TypeError):
                    pass

    for i in range(7):
        day_date = week_start + timedelta(days=i)

        if has_proposal:
            # Use proposed games
            day_games_raw = proposed_games_by_date.get(day_date, [])
            if league:
                day_games_raw = [g for g in day_games_raw if g.get('league') == league]

            # Convert to objects with needed properties for template
            day_games = []
            for g in sorted(day_games_raw, key=lambda x: x.get('game_date', '')):
                game_obj = type('ProposedGame', (), {
                    'ID': g.get('id'),
                    'game_date': datetime.fromisoformat(g['game_date']) if g.get('game_date') else None,
                    'location': g.get('field_name'),  # Proposed games use field_name
                    'league': g.get('league'),
                    'status': 'scheduled',
                    'game_type': g.get('game_type', 'regular'),
                    'is_scrimmage': g.get('is_scrimmage', False),
                    'display_type': g.get('game_type', 'regular') if not g.get('is_scrimmage') else 'scrimmage',
                    'home_ID': g.get('home_team_id'),
                    'away_ID': g.get('away_team_id'),
                    'home_team': type('Team', (), {'computed_display_name': g.get('home_team_name', 'TBD')})() if g.get('home_team_id') else None,
                    'away_team': type('Team', (), {'computed_display_name': g.get('away_team_name', 'TBD')})() if g.get('away_team_id') else None,
                    'no_time_limit': g.get('no_time_limit', False),
                    'is_proposed': True
                })()
                day_games.append(game_obj)
        else:
            # Get games from database
            query = Game.query.filter(
                Game.active == 1,
                Game.year == year,
                Game.is_spring == is_spring,
                db.func.date(Game.game_date) == day_date
            )
            if league:
                query = query.filter(Game.league == league)

            day_games = query.order_by(Game.game_date, Game.location).all()

        week_days.append({
            'date': day_date,
            'is_today': day_date == today,
            'games': day_games
        })

    # Calculate prev/next week
    prev_week = (week_start - timedelta(days=7)).strftime('%G-%V')
    next_week = (week_start + timedelta(days=7)).strftime('%G-%V')

    # Get leagues for filter
    if has_proposal:
        # Get leagues from proposal
        leagues = list(set(g.get('league') for g in proposal.games if g.get('league')))
    else:
        # Get leagues from database
        leagues = db.session.query(Game.league).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.league.isnot(None)
        ).distinct().all()
        leagues = [l[0] for l in leagues if l[0]]
    leagues.sort()

    # Get teams and fields for edit modal
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    return render_template(
        'games/calendar.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        week_start=week_start,
        week_end=week_end,
        week_days=week_days,
        prev_week=prev_week,
        next_week=next_week,
        leagues=leagues,
        teams=teams,
        fields=fields,
        current_league=league,
        today=today,
        has_proposal=has_proposal
    )


@games_bp.route('/<int:year>/<int:is_spring>/day/<target_date>')
@login_required
def day_view(year, is_spring, target_date):
    """Single day view with field columns and time slot rows.

    Shows all games/practices for a specific date in a grid format:
    - Columns: Fields
    - Rows: Time slots (5:30, 6:00, 6:30, 7:00, 7:30, 8:00)
    - Cells: Games/practices at that field/time
    """
    from datetime import datetime as dt
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Parse the target date
    try:
        view_date = dt.strptime(target_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('games.calendar', year=year, is_spring=is_spring))

    # Check if there's a proposal for this season
    from app.models.schedule_proposal import ScheduleProposal
    proposal = ScheduleProposal.get_for_season(year, is_spring)
    has_proposal = proposal is not None

    if has_proposal:
        # Get games from proposal for this day
        games = []
        for g in proposal.games:
            if g.get('game_date'):
                try:
                    pg_date = dt.fromisoformat(g['game_date']).date()
                    if pg_date == view_date:
                        # Convert to object with needed properties
                        game_obj = type('ProposedGame', (), {
                            'ID': g.get('id'),
                            'game_date': dt.fromisoformat(g['game_date']) if g.get('game_date') else None,
                            'location': g.get('field_name'),  # Proposed games use field_name
                            'league': g.get('league'),
                            'status': 'scheduled',
                            'game_type': g.get('game_type', 'regular'),
                            'is_scrimmage': g.get('is_scrimmage', False),
                            'display_type': g.get('game_type', 'regular') if not g.get('is_scrimmage') else 'scrimmage',
                            'home_ID': g.get('home_team_id'),
                            'away_ID': g.get('away_team_id'),
                            'home_team': type('Team', (), {'computed_display_name': g.get('home_team_name', 'TBD')})() if g.get('home_team_id') else None,
                            'away_team': type('Team', (), {'computed_display_name': g.get('away_team_name', 'TBD')})() if g.get('away_team_id') else None,
                            'no_time_limit': g.get('no_time_limit', False),
                            'is_proposed': True
                        })()
                        games.append(game_obj)
                except (ValueError, TypeError):
                    pass
        # Sort by game_date
        games.sort(key=lambda x: x.game_date if x.game_date else dt.min)
    else:
        # Get games from database for this day
        games = Game.query.filter(
            Game.active == 1,
            Game.year == year,
            Game.is_spring == is_spring,
            db.func.date(Game.game_date) == view_date
        ).order_by(Game.game_date, Game.location).all()

    # Get all fields that have games on this day
    fields_with_games = set()
    game_hours = set()
    for game in games:
        if game.location:
            fields_with_games.add(game.location)
        if game.game_date:
            game_hours.add(game.game_date.hour)

    # Get all fields for display (prioritize those with games)
    all_fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()
    field_lookup = {f.location_title: f for f in all_fields}

    # Build display_fields from fields used on this day
    if fields_with_games:
        display_fields = []
        for field_name in sorted(fields_with_games):
            if field_name:
                # Try to find matching field in DB
                if field_name in field_lookup:
                    display_fields.append(field_lookup[field_name])
                else:
                    # Create a placeholder field object for fields not in DB
                    placeholder = type('Field', (), {'ID': None, 'location_title': field_name})()
                    display_fields.append(placeholder)
    else:
        display_fields = all_fields[:8]  # Limit to 8 fields to fit on screen

    # Define time slots based on actual game times (dynamic range)
    time_slots = []
    if game_hours:
        min_hour = min(game_hours)
        max_hour = max(game_hours) + 1  # Include the last hour
        for hour in range(min_hour, max_hour + 1):
            for minute in [0, 30]:
                time_slots.append(f'{hour:02d}:{minute:02d}')
    else:
        # Default to evening if no games
        for hour in [17, 18, 19, 20]:
            for minute in [0, 30]:
                time_slots.append(f'{hour:02d}:{minute:02d}')

    # Build grid: time_slot -> field -> list of games
    grid = {}
    for slot in time_slots:
        grid[slot] = {}
        for field in display_fields:
            grid[slot][field.location_title] = []

    # Place games in grid
    for game in games:
        if game.game_date and game.location:
            time_key = game.game_date.strftime('%H:%M')
            # Round to nearest 30-minute slot
            hour = game.game_date.hour
            minute = 0 if game.game_date.minute < 30 else 30
            time_key = f'{hour:02d}:{minute:02d}'

            if time_key in grid and game.location in grid[time_key]:
                grid[time_key][game.location].append(game)

    # Calculate prev/next day links
    prev_date = view_date - timedelta(days=1)
    next_date = view_date + timedelta(days=1)

    # Get teams for edit modal
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    return render_template(
        'games/day_view.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        view_date=view_date,
        prev_date=prev_date.strftime('%Y-%m-%d'),
        next_date=next_date.strftime('%Y-%m-%d'),
        games=games,
        display_fields=display_fields,
        all_fields=all_fields,
        time_slots=time_slots,
        grid=grid,
        teams=teams
    )


@games_bp.route('/<int:year>/<int:is_spring>/rainout', methods=['GET', 'POST'])
@login_required
def rainout(year, is_spring):
    """Handle rainouts - bulk postpone/reschedule games"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage rainouts.', 'error')
        return redirect(url_for('games.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'postpone_all':
            rainout_date_str = request.form.get('rainout_date')
            if rainout_date_str:
                rainout_date = datetime.strptime(rainout_date_str, '%Y-%m-%d').date()

                # Get all games on this date
                games = Game.query.filter(
                    Game.active == 1,
                    Game.year == year,
                    Game.is_spring == is_spring,
                    db.func.date(Game.game_date) == rainout_date,
                    Game.away_ID.isnot(None)  # Only actual games, not practices
                ).all()

                count = 0
                for game in games:
                    game.status = 'postponed'
                    count += 1

                db.session.commit()
                logger.info(f'Postponed {count} games for rainout on {rainout_date}')
                flash(f'Postponed {count} games for {rainout_date.strftime("%B %d, %Y")}', 'success')

        elif action == 'reschedule_game':
            game_id = int(request.form.get('game_id'))
            new_date_str = request.form.get('new_date')
            new_time_str = request.form.get('new_time')
            new_field = request.form.get('new_field')

            game = Game.query.get(game_id)
            if game and new_date_str:
                if new_time_str:
                    game.game_date = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
                else:
                    # Keep original time
                    original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                    new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    game.game_date = datetime.combine(new_date, original_time)

                # Update field if specified
                if new_field:
                    game.location = new_field

                game.status = 'scheduled'
                db.session.commit()
                logger.info(f'Rescheduled game {game_id} to {game.game_date} at {game.location}')
                flash(f'Rescheduled game to {game.game_date.strftime("%B %d at %I:%M %p")}', 'success')

        elif action == 'swap_with_practice':
            game_id = int(request.form.get('game_id'))
            practice_date_str = request.form.get('practice_date')

            game = Game.query.get(game_id)
            if game and practice_date_str:
                practice_date = datetime.strptime(practice_date_str, '%Y-%m-%d').date()
                original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                game.game_date = datetime.combine(practice_date, original_time)
                game.status = 'scheduled'
                db.session.commit()
                logger.info(f'Swapped game {game_id} to practice date {practice_date}')
                flash(f'Moved game to {practice_date.strftime("%B %d")}', 'success')

        elif action == 'bulk_reschedule':
            # Bulk reschedule selected games
            game_ids = request.form.getlist('game_ids')
            new_date_str = request.form.get('bulk_new_date')
            new_time_str = request.form.get('bulk_new_time')
            new_field = request.form.get('bulk_new_field')

            if game_ids and new_date_str:
                count = 0
                for game_id in game_ids:
                    game = Game.query.get(int(game_id))
                    if game:
                        # Update date/time
                        if new_time_str:
                            game.game_date = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
                        else:
                            original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                            game.game_date = datetime.combine(new_date, original_time)

                        # Update field if specified
                        if new_field:
                            game.location = new_field

                        game.status = 'scheduled'
                        count += 1

                db.session.commit()
                logger.info(f'Bulk rescheduled {count} games to {new_date_str}')
                flash(f'Rescheduled {count} games to {new_date_str}', 'success')

        return redirect(url_for('games.rainout', year=year, is_spring=is_spring))

    # GET - show rainout wizard
    selected_date_str = request.args.get('date')
    selected_date = None
    affected_games = []

    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            affected_games = Game.query.filter(
                Game.active == 1,
                Game.year == year,
                Game.is_spring == is_spring,
                db.func.date(Game.game_date) == selected_date,
                Game.away_ID.isnot(None)  # Only actual games
            ).order_by(Game.game_date).all()
        except ValueError:
            pass

    # Get dates that have games (for quick selection)
    game_dates = db.session.query(
        db.func.date(Game.game_date).label('game_date'),
        db.func.count(Game.ID).label('game_count')
    ).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        Game.away_ID.isnot(None),
        Game.status == 'scheduled'
    ).group_by(
        db.func.date(Game.game_date)
    ).order_by(
        db.func.date(Game.game_date)
    ).all()

    # Get practice dates (potential reschedule targets)
    from app.models.league_season import LeagueSeason
    configs = LeagueSeason.get_by_season(year, is_spring)
    practice_dates = []

    for config in configs:
        if config.practice_days and config.opening_day_date:
            # Get practice days for next 4 weeks from opening day
            current = config.opening_day_date
            end_date = current + timedelta(weeks=12)
            while current <= end_date:
                if current.weekday() in config.practice_days:
                    if current not in practice_dates:
                        practice_dates.append(current)
                current += timedelta(days=1)

    practice_dates.sort()

    # Get fields for reschedule dropdown
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    return render_template(
        'games/rainout.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        selected_date=selected_date,
        affected_games=affected_games,
        game_dates=game_dates,
        practice_dates=practice_dates[:20],  # Limit to next 20 practice dates
        fields=fields
    )


@games_bp.route('/<int:year>/<int:is_spring>/league-practice', methods=['GET', 'POST'])
@login_required
def league_practice(year, is_spring):
    """Create a league-based group practice where all teams practice together."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to create league practices.', 'error')
        return redirect(url_for('games.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get leagues for this season
    from app.models.league_season import LeagueSeason
    league_configs = LeagueSeason.get_by_season(year, is_spring)
    leagues = [lc.league for lc in league_configs]

    # Get fields
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    if request.method == 'POST':
        league = request.form.get('league')
        practice_date_str = request.form.get('practice_date')
        practice_time_str = request.form.get('practice_time')
        field_id = request.form.get('field_id')

        if not all([league, practice_date_str, practice_time_str, field_id]):
            flash('All fields are required.', 'error')
            return redirect(url_for('games.league_practice', year=year, is_spring=is_spring))

        try:
            practice_date = datetime.strptime(practice_date_str, '%Y-%m-%d').date()
            practice_time = datetime.strptime(practice_time_str, '%H:%M').time()
            practice_datetime = datetime.combine(practice_date, practice_time)
        except ValueError:
            flash('Invalid date or time format.', 'error')
            return redirect(url_for('games.league_practice', year=year, is_spring=is_spring))

        field = Field.query.get(int(field_id))
        if not field:
            flash('Invalid field selected.', 'error')
            return redirect(url_for('games.league_practice', year=year, is_spring=is_spring))

        # Get all active teams in this league for this season
        teams = TeamSeason.query.filter_by(
            year=year,
            is_spring=is_spring,
            league=league,
            is_placeholder=0,
            active=1
        ).all()

        if not teams:
            flash(f'No teams found for {league}.', 'error')
            return redirect(url_for('games.league_practice', year=year, is_spring=is_spring))

        # Create a practice for each team, all marked as league practice
        created_count = 0
        for team in teams:
            practice = Game(
                active=1,
                game_date=practice_datetime,
                home_ID=team.team_ID,
                away_ID=None,  # Practice = no away team
                league=league,
                location=field.location_title,
                status='scheduled',
                year=year,
                is_spring=is_spring,
                game_type='practice',
                is_league_practice=True
            )
            db.session.add(practice)
            created_count += 1

        db.session.commit()
        logger.info(f'Created league practice for {league} on {practice_date} with {created_count} teams')
        flash(f'Created league practice for {league} with {created_count} teams on {practice_date.strftime("%B %d, %Y")} at {practice_time.strftime("%I:%M %p")}', 'success')
        return redirect(url_for('games.league_practice', year=year, is_spring=is_spring))

    # Get existing league practices for display
    existing_practices = Game.query.filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        Game.is_league_practice == True
    ).order_by(Game.game_date).all()

    # Group by date/time/league
    practice_groups = {}
    for p in existing_practices:
        key = (p.game_date.date() if p.game_date else None, p.league, p.location)
        if key not in practice_groups:
            practice_groups[key] = {
                'date': p.game_date,
                'league': p.league,
                'location': p.location,
                'teams': []
            }
        practice_groups[key]['teams'].append(p)

    return render_template(
        'games/league_practice.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        leagues=leagues,
        fields=fields,
        practice_groups=list(practice_groups.values())
    )
