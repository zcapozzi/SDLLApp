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
    for i in range(7):
        day_date = week_start + timedelta(days=i)

        # Get games for this day
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
    leagues = db.session.query(Game.league).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league.isnot(None)
    ).distinct().all()
    leagues = [l[0] for l in leagues if l[0]]

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
        current_league=league
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

            game = Game.query.get(game_id)
            if game and new_date_str:
                if new_time_str:
                    game.game_date = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
                else:
                    # Keep original time
                    original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                    new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    game.game_date = datetime.combine(new_date, original_time)

                game.status = 'scheduled'
                db.session.commit()
                logger.info(f'Rescheduled game {game_id} to {game.game_date}')
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

    return render_template(
        'games/rainout.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        selected_date=selected_date,
        affected_games=affected_games,
        game_dates=game_dates,
        practice_dates=practice_dates[:20]  # Limit to next 20 practice dates
    )
