"""Game management routes"""

from datetime import datetime
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
