"""Season management routes"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.extensions import db
from app.utils.logging import SDLLLogger

seasons_bp = Blueprint('seasons', __name__)
logger = SDLLLogger('seasons')


@seasons_bp.route('/')
@login_required
def index():
    """List all seasons"""
    seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring,
        db.func.count(TeamSeason.team_ID).label('team_count')
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).order_by(
        TeamSeason.year.desc(),
        TeamSeason.is_spring.desc()
    ).all()

    season_list = []
    for year, is_spring, team_count in seasons:
        # Count games for this season
        game_count = Game.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).count()

        season_list.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{"Spring" if is_spring else "Fall"} {year}',
            'team_count': team_count,
            'game_count': game_count
        })

    return render_template('seasons/index.html', seasons=season_list)


@seasons_bp.route('/<int:year>/<int:is_spring>')
@login_required
def view(year, is_spring):
    """View a specific season"""
    teams = TeamSeason.get_by_season(year, is_spring)
    games = Game.get_by_season(year, is_spring)

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Group teams by league
    teams_by_league = {}
    for team in teams:
        league = team.league or 'Unknown'
        if league not in teams_by_league:
            teams_by_league[league] = []
        teams_by_league[league].append(team)

    return render_template(
        'seasons/view.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        teams_by_league=teams_by_league,
        games=games,
        team_count=len(teams),
        game_count=len(games)
    )


@seasons_bp.route('/setup', methods=['GET', 'POST'])
@login_required
def setup():
    """Season setup - create new season or manage existing"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to set up seasons.', 'error')
        return redirect(url_for('seasons.index'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_season':
            year = int(request.form.get('year'))
            is_spring = int(request.form.get('is_spring'))

            # Check if season exists
            existing = TeamSeason.query.filter_by(
                year=year,
                is_spring=is_spring,
                active=1
            ).first()

            if existing:
                flash(f'Season {"Spring" if is_spring else "Fall"} {year} already exists.', 'error')
            else:
                # Create empty season (will add teams separately)
                flash(f'Season {"Spring" if is_spring else "Fall"} {year} created. Now add teams.', 'success')
                return redirect(url_for('seasons.manage_teams', year=year, is_spring=is_spring))

    # Get existing seasons for display
    seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring,
        db.func.count(TeamSeason.team_ID).label('team_count')
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).order_by(
        TeamSeason.year.desc(),
        TeamSeason.is_spring.desc()
    ).all()

    season_list = []
    for year, is_spring, team_count in seasons:
        game_count = Game.query.filter_by(year=year, is_spring=is_spring, active=1).count()
        season_list.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{"Spring" if is_spring else "Fall"} {year}',
            'team_count': team_count,
            'game_count': game_count
        })

    # Get available leagues
    leagues = League.get_all_active()

    return render_template('seasons/setup.html', seasons=season_list, leagues=leagues)


@seasons_bp.route('/<int:year>/<int:is_spring>/teams', methods=['GET', 'POST'])
@login_required
def manage_teams(year, is_spring):
    """Manage teams for a specific season"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage teams.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_team':
            league = request.form.get('league')
            display_name = request.form.get('display_name')
            is_placeholder = 1 if request.form.get('is_placeholder') else 0

            team = TeamSeason(
                active=1,
                year=year,
                league=league,
                display_name=display_name,
                is_placeholder=is_placeholder,
                is_spring=is_spring
            )
            db.session.add(team)
            db.session.commit()
            logger.info(f'Added team {display_name} to {season_name}')
            flash(f'Added team: {display_name}', 'success')

        elif action == 'add_multiple':
            league = request.form.get('league')
            count = int(request.form.get('team_count', 1))

            # Get current team count for this league in this season
            existing_count = TeamSeason.query.filter_by(
                year=year,
                is_spring=is_spring,
                league=league,
                active=1
            ).count()

            for i in range(count):
                team_num = existing_count + i + 1
                display_name = f'{league} Team {team_num}'
                team = TeamSeason(
                    active=1,
                    year=year,
                    league=league,
                    display_name=display_name,
                    is_placeholder=0,
                    is_spring=is_spring
                )
                db.session.add(team)

            db.session.commit()
            logger.info(f'Added {count} teams to {league} in {season_name}')
            flash(f'Added {count} teams to {league}', 'success')

        elif action == 'delete_team':
            team_id = int(request.form.get('team_id'))
            team = TeamSeason.query.get(team_id)
            if team and team.year == year and team.is_spring == is_spring:
                team.active = 0  # Soft delete
                db.session.commit()
                logger.info(f'Deleted team {team.display_name} from {season_name}')
                flash(f'Removed team: {team.display_name}', 'success')

        elif action == 'rename_team':
            team_id = int(request.form.get('team_id'))
            new_name = request.form.get('new_name')
            team = TeamSeason.query.get(team_id)
            if team and team.year == year and team.is_spring == is_spring:
                old_name = team.display_name
                team.display_name = new_name
                db.session.commit()
                logger.info(f'Renamed team {old_name} to {new_name}')
                flash(f'Renamed team to: {new_name}', 'success')

        elif action == 'set_team_name':
            team_id = int(request.form.get('team_id'))
            team_name = request.form.get('team_name', '').strip() or None
            team = TeamSeason.query.get(team_id)
            if team and team.year == year and team.is_spring == is_spring:
                team.team_name = team_name
                db.session.commit()
                if team_name:
                    logger.info(f'Set team name for {team.display_name} to {team_name}')
                    flash(f'Team name set to: {team_name}', 'success')
                else:
                    logger.info(f'Cleared team name for {team.display_name}')
                    flash(f'Team name cleared (will show placeholder)', 'success')

        return redirect(url_for('seasons.manage_teams', year=year, is_spring=is_spring))

    # GET - show teams
    teams = TeamSeason.get_by_season(year, is_spring)

    # Group by league
    teams_by_league = {}
    for team in teams:
        league = team.league or 'Unknown'
        if league not in teams_by_league:
            teams_by_league[league] = []
        teams_by_league[league].append(team)

    # Get available leagues
    leagues = League.get_all_active()

    return render_template(
        'seasons/manage_teams.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        teams_by_league=teams_by_league,
        team_count=len(teams),
        leagues=leagues
    )


@seasons_bp.route('/copy', methods=['GET', 'POST'])
@login_required
def copy_wizard():
    """Season copy wizard"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to copy seasons.', 'error')
        return redirect(url_for('seasons.index'))

    if request.method == 'POST':
        source_year = int(request.form.get('source_year'))
        source_is_spring = int(request.form.get('source_is_spring'))
        target_year = int(request.form.get('target_year'))
        target_is_spring = int(request.form.get('target_is_spring'))
        copy_games = request.form.get('copy_games') == 'yes'

        logger.info(f'Starting season copy: {source_year}/{source_is_spring} -> {target_year}/{target_is_spring}')

        # Check if target season already exists
        existing = TeamSeason.query.filter_by(
            year=target_year,
            is_spring=target_is_spring,
            active=1
        ).first()

        if existing:
            flash(f'Season {"Spring" if target_is_spring else "Fall"} {target_year} already has teams. Delete them first or choose a different target.', 'error')
            return redirect(url_for('seasons.copy_wizard'))

        try:
            # Copy teams
            source_teams = TeamSeason.get_by_season(source_year, source_is_spring)
            team_id_mapping = {}

            new_teams = TeamSeason.copy_to_new_season(
                source_year, source_is_spring,
                target_year, target_is_spring
            )

            # Build mapping of old team IDs to new team IDs
            for i, source_team in enumerate(source_teams):
                if i < len(new_teams):
                    team_id_mapping[source_team.team_ID] = new_teams[i].team_ID

            logger.info(f'Copied {len(new_teams)} teams')

            # Optionally copy games
            games_copied = 0
            if copy_games:
                new_games = Game.copy_to_new_season(
                    source_year, source_is_spring,
                    target_year, target_is_spring,
                    team_id_mapping=team_id_mapping
                )
                games_copied = len(new_games)
                logger.info(f'Copied {games_copied} games')

            # Copy league configurations (playoff formats, etc.)
            new_league_configs = LeagueSeason.copy_to_new_season(
                source_year, source_is_spring,
                target_year, target_is_spring
            )
            logger.info(f'Copied {len(new_league_configs)} league configs')

            # Auto-generate seed placeholders for each league
            total_seeds = 0
            for config in new_league_configs:
                seeds = TeamSeason.generate_seed_placeholders(
                    target_year, target_is_spring,
                    config.league, config.actual_playoff_teams
                )
                total_seeds += len(seeds)
            logger.info(f'Generated {total_seeds} seed placeholders')

            flash(f'Successfully created {"Spring" if target_is_spring else "Fall"} {target_year}: {len(new_teams)} teams, {games_copied} games, {len(new_league_configs)} league settings, {total_seeds} seed placeholders.', 'success')
            return redirect(url_for('seasons.manage_teams', year=target_year, is_spring=target_is_spring))

        except Exception as e:
            db.session.rollback()
            logger.info(f'Season copy failed: {str(e)}')
            flash(f'Error copying season: {str(e)}', 'error')
            return redirect(url_for('seasons.copy_wizard'))

    # GET - show the wizard form
    seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring,
        db.func.count(TeamSeason.team_ID).label('team_count')
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).order_by(
        TeamSeason.year.desc(),
        TeamSeason.is_spring.desc()
    ).all()

    source_options = []
    for year, is_spring, team_count in seasons:
        game_count = Game.query.filter_by(year=year, is_spring=is_spring, active=1).count()
        source_options.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{"Spring" if is_spring else "Fall"} {year}',
            'team_count': team_count,
            'game_count': game_count
        })

    return render_template('seasons/copy.html', source_options=source_options)


@seasons_bp.route('/api/teams/<int:year>/<int:is_spring>')
@login_required
def api_teams(year, is_spring):
    """API endpoint to get teams for a season"""
    teams = TeamSeason.get_by_season(year, is_spring)
    return jsonify([{
        'team_ID': t.team_ID,
        'display_name': t.display_name,
        'team_name': t.team_name,
        'computed_display_name': t.computed_display_name,
        'league': t.league,
        'is_placeholder': t.is_placeholder
    } for t in teams])


@seasons_bp.route('/api/season/<int:year>/<int:is_spring>/summary')
@login_required
def api_season_summary(year, is_spring):
    """API endpoint to get season summary"""
    teams = TeamSeason.get_by_season(year, is_spring)
    games = Game.get_by_season(year, is_spring)

    # Group teams by league
    leagues = {}
    for team in teams:
        league = team.league or 'Unknown'
        if league not in leagues:
            leagues[league] = 0
        leagues[league] += 1

    return jsonify({
        'year': year,
        'is_spring': is_spring,
        'name': f'{"Spring" if is_spring else "Fall"} {year}',
        'team_count': len(teams),
        'game_count': len(games),
        'teams_by_league': leagues
    })


@seasons_bp.route('/<int:year>/<int:is_spring>/reset', methods=['GET', 'POST'])
@login_required
def reset_season(year, is_spring):
    """Reset/clear season data with cascading delete options"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to reset season data.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get current counts
    from app.models.field_slot import FieldSlot
    teams = TeamSeason.query.filter_by(year=year, is_spring=is_spring, active=1).all()
    games = Game.query.filter_by(year=year, is_spring=is_spring, active=1).all()
    slots = FieldSlot.query.filter_by(year=year, is_spring=is_spring, active=1).all()
    league_configs = LeagueSeason.query.filter_by(year=year, is_spring=is_spring, active=1).all()

    # Separate regular teams from placeholders
    regular_teams = [t for t in teams if not t.is_placeholder]
    placeholder_teams = [t for t in teams if t.is_placeholder]

    counts = {
        'teams': len(regular_teams),
        'placeholders': len(placeholder_teams),
        'games': len(games),
        'slots': len(slots),
        'league_configs': len(league_configs)
    }

    if request.method == 'POST':
        action = request.form.get('action')
        hard_delete = request.form.get('hard_delete') == 'yes'

        deleted = {'teams': 0, 'games': 0, 'slots': 0, 'configs': 0, 'placeholders': 0}

        if action == 'delete_games':
            # Delete games only
            for game in games:
                if hard_delete:
                    db.session.delete(game)
                else:
                    game.active = 0
                deleted['games'] += 1
            db.session.commit()
            logger.info(f'Deleted {deleted["games"]} games from {season_name}')
            flash(f'Deleted {deleted["games"]} games', 'success')

        elif action == 'delete_slots':
            # Delete field slots only
            for slot in slots:
                if hard_delete:
                    db.session.delete(slot)
                else:
                    slot.active = 0
                deleted['slots'] += 1
            db.session.commit()
            logger.info(f'Deleted {deleted["slots"]} field slots from {season_name}')
            flash(f'Deleted {deleted["slots"]} field slots', 'success')

        elif action == 'delete_placeholders':
            # Delete playoff placeholders only
            for team in placeholder_teams:
                if hard_delete:
                    db.session.delete(team)
                else:
                    team.active = 0
                deleted['placeholders'] += 1
            db.session.commit()
            logger.info(f'Deleted {deleted["placeholders"]} placeholders from {season_name}')
            flash(f'Deleted {deleted["placeholders"]} playoff placeholders', 'success')

        elif action == 'delete_teams':
            # Delete teams → cascades to games (teams are referenced by games)
            for game in games:
                if hard_delete:
                    db.session.delete(game)
                else:
                    game.active = 0
                deleted['games'] += 1

            for team in teams:  # includes placeholders
                if hard_delete:
                    db.session.delete(team)
                else:
                    team.active = 0
                if team.is_placeholder:
                    deleted['placeholders'] += 1
                else:
                    deleted['teams'] += 1

            db.session.commit()
            logger.info(f'Deleted {deleted["teams"]} teams, {deleted["placeholders"]} placeholders, {deleted["games"]} games from {season_name}')
            flash(f'Deleted {deleted["teams"]} teams, {deleted["placeholders"]} placeholders, and {deleted["games"]} games', 'success')

        elif action == 'delete_season':
            # Delete everything for this season
            for game in games:
                if hard_delete:
                    db.session.delete(game)
                else:
                    game.active = 0
                deleted['games'] += 1

            for team in teams:
                if hard_delete:
                    db.session.delete(team)
                else:
                    team.active = 0
                if team.is_placeholder:
                    deleted['placeholders'] += 1
                else:
                    deleted['teams'] += 1

            for slot in slots:
                if hard_delete:
                    db.session.delete(slot)
                else:
                    slot.active = 0
                deleted['slots'] += 1

            for config in league_configs:
                if hard_delete:
                    db.session.delete(config)
                else:
                    config.active = 0
                deleted['configs'] += 1

            db.session.commit()
            logger.info(f'Deleted entire season {season_name}: {deleted}')
            flash(f'Deleted entire season: {deleted["teams"]} teams, {deleted["placeholders"]} placeholders, {deleted["games"]} games, {deleted["slots"]} slots, {deleted["configs"]} league configs', 'success')
            return redirect(url_for('seasons.index'))

        return redirect(url_for('seasons.reset_season', year=year, is_spring=is_spring))

    return render_template(
        'seasons/reset.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        counts=counts
    )


@seasons_bp.route('/<int:year>/<int:is_spring>/playoffs/<league_name>', methods=['GET', 'POST'])
@login_required
def manage_playoffs(year, is_spring, league_name):
    """Manage playoff placeholders for a specific league"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage playoffs.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get league config
    config = LeagueSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        league=league_name,
        active=1
    ).first()

    if not config:
        flash(f'League {league_name} not found for this season.', 'error')
        return redirect(url_for('seasons.manage_leagues', year=year, is_spring=is_spring))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'resolve_placeholder':
            placeholder_id = int(request.form.get('placeholder_id'))
            actual_team_id = request.form.get('actual_team_id')

            placeholder = TeamSeason.query.get(placeholder_id)
            if placeholder and placeholder.is_placeholder:
                if actual_team_id:
                    placeholder.resolved_team_id = int(actual_team_id)
                    db.session.commit()
                    actual_team = TeamSeason.query.get(int(actual_team_id))
                    logger.info(f'Resolved {placeholder.display_name} to {actual_team.computed_display_name}')
                    flash(f'Resolved {placeholder.display_name} to {actual_team.computed_display_name}', 'success')
                else:
                    placeholder.resolved_team_id = None
                    db.session.commit()
                    logger.info(f'Cleared resolution for {placeholder.display_name}')
                    flash(f'Cleared resolution for {placeholder.display_name}', 'success')

        elif action == 'delete_placeholder':
            placeholder_id = int(request.form.get('placeholder_id'))
            placeholder = TeamSeason.query.get(placeholder_id)
            if placeholder and placeholder.is_placeholder:
                placeholder.active = 0
                db.session.commit()
                logger.info(f'Deleted placeholder {placeholder.display_name}')
                flash(f'Deleted {placeholder.display_name}', 'success')

        elif action == 'regenerate_seeds':
            # Clear existing unresolved seed placeholders and regenerate
            existing = TeamSeason.query.filter_by(
                year=year,
                is_spring=is_spring,
                league=league_name,
                is_placeholder=1,
                active=1
            ).filter(
                TeamSeason.seed_number.isnot(None),
                TeamSeason.resolved_team_id.is_(None)
            ).all()
            for p in existing:
                p.active = 0
            db.session.commit()

            seeds = TeamSeason.generate_seed_placeholders(
                year, is_spring, league_name, config.actual_playoff_teams
            )
            flash(f'Regenerated {len(seeds)} seed placeholders', 'success')

        elif action == 'regenerate_brackets':
            # Clear existing unresolved bracket placeholders and regenerate
            existing = TeamSeason.query.filter_by(
                year=year,
                is_spring=is_spring,
                league=league_name,
                is_placeholder=1,
                active=1
            ).filter(
                TeamSeason.bracket_position.isnot(None),
                TeamSeason.resolved_team_id.is_(None)
            ).all()
            for p in existing:
                p.active = 0
            db.session.commit()

            brackets = TeamSeason.generate_bracket_placeholders(
                year, is_spring, league_name, config.playoff_format, config.actual_playoff_teams
            )
            flash(f'Regenerated {len(brackets)} bracket placeholders', 'success')

        return redirect(url_for('seasons.manage_playoffs', year=year, is_spring=is_spring, league_name=league_name))

    # GET - show placeholders and resolution UI
    placeholders = TeamSeason.get_playoff_placeholders(year, is_spring, league_name)
    regular_teams = TeamSeason.get_regular_teams(year, is_spring, league_name)

    # Separate seeds from bracket positions
    seed_placeholders = [p for p in placeholders if p.seed_number is not None]
    bracket_placeholders = [p for p in placeholders if p.bracket_position is not None]

    return render_template(
        'seasons/manage_playoffs.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        league_name=league_name,
        config=config,
        seed_placeholders=seed_placeholders,
        bracket_placeholders=bracket_placeholders,
        regular_teams=regular_teams
    )


@seasons_bp.route('/<int:year>/<int:is_spring>/leagues', methods=['GET', 'POST'])
@login_required
def manage_leagues(year, is_spring):
    """Manage league configurations for a season (playoff formats, etc.)"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league settings.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_format':
            league_id = int(request.form.get('league_id'))
            playoff_format = request.form.get('playoff_format')
            playoff_teams = int(request.form.get('playoff_teams', 4))
            regular_season_games = int(request.form.get('regular_season_games', 10))
            notes = request.form.get('notes', '').strip() or None

            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                config.playoff_format = playoff_format
                config.playoff_teams = playoff_teams
                config.regular_season_games = regular_season_games
                config.notes = notes
                db.session.commit()
                logger.info(f'Updated {config.league}: {playoff_format}, {playoff_teams} playoff teams, {regular_season_games} games/team')
                flash(f'Updated {config.league} settings', 'success')

        elif action == 'generate_bracket':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                num_playoff_teams = config.actual_playoff_teams
                # Generate seed placeholders
                seed_placeholders = TeamSeason.generate_seed_placeholders(
                    year, is_spring, config.league, num_playoff_teams
                )
                # Generate bracket placeholders
                bracket_placeholders = TeamSeason.generate_bracket_placeholders(
                    year, is_spring, config.league, config.playoff_format, num_playoff_teams
                )
                total = len(seed_placeholders) + len(bracket_placeholders)
                logger.info(f'Generated {total} playoff placeholders for {config.league}')
                flash(f'Generated {len(seed_placeholders)} seeds + {len(bracket_placeholders)} bracket positions for {config.league}', 'success')

        elif action == 'generate_regular_games':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                # Get regular teams (not placeholders)
                regular_teams = TeamSeason.get_regular_teams(year, is_spring, config.league)
                if len(regular_teams) < 2:
                    flash(f'{config.league}: Need at least 2 teams to generate games', 'error')
                else:
                    games = Game.generate_regular_season_games(
                        year, is_spring, config.league,
                        regular_teams, config.regular_season_games or 10
                    )
                    logger.info(f'Generated {len(games)} regular season games for {config.league}')
                    flash(f'Generated {len(games)} regular season games for {config.league}', 'success')

        elif action == 'generate_playoff_games':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                num_playoff_teams = config.actual_playoff_teams
                if num_playoff_teams < 2:
                    flash(f'{config.league}: Need at least 2 teams to generate playoff games.', 'error')
                else:
                    # Auto-generate seed placeholders if they don't exist
                    seed_placeholders = TeamSeason.get_playoff_placeholders(year, is_spring, config.league)
                    seeds_only = [p for p in seed_placeholders if p.seed_number is not None]
                    if len(seeds_only) < num_playoff_teams:
                        new_seeds = TeamSeason.generate_seed_placeholders(
                            year, is_spring, config.league, num_playoff_teams
                        )
                        logger.info(f'Auto-generated {len(new_seeds)} seed placeholders for {config.league}')
                        # Refresh the list
                        seed_placeholders = TeamSeason.get_playoff_placeholders(year, is_spring, config.league)
                        seeds_only = [p for p in seed_placeholders if p.seed_number is not None]

                    games = Game.generate_playoff_games(
                        year, is_spring, config.league,
                        seeds_only, config.playoff_format
                    )
                    logger.info(f'Generated {len(games)} playoff games for {config.league}')
                    flash(f'Generated {len(games)} playoff games for {config.league}', 'success')

        elif action == 'clear_regular_games':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                games = Game.query.filter_by(
                    year=year, is_spring=is_spring, league=config.league,
                    game_type='regular', active=1
                ).all()
                for g in games:
                    g.active = 0
                db.session.commit()
                logger.info(f'Cleared {len(games)} regular games for {config.league}')
                flash(f'Cleared {len(games)} regular season games for {config.league}', 'success')

        elif action == 'clear_playoff_games':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                games = Game.query.filter_by(
                    year=year, is_spring=is_spring, league=config.league,
                    game_type='playoff', active=1
                ).all()
                for g in games:
                    g.active = 0
                db.session.commit()
                logger.info(f'Cleared {len(games)} playoff games for {config.league}')
                flash(f'Cleared {len(games)} playoff games for {config.league}', 'success')

        elif action == 'sync_leagues':
            # Get leagues that have teams in this season
            teams = TeamSeason.get_by_season(year, is_spring)
            league_names = set(t.league for t in teams if t.league)

            # Ensure each has a config
            LeagueSeason.ensure_leagues_for_season(year, is_spring, league_names)
            flash(f'Synced {len(league_names)} leagues', 'success')

        # Redirect with anchor to scroll back to the league row (for game generation actions)
        redirect_url = url_for('seasons.manage_leagues', year=year, is_spring=is_spring)
        if action in ('generate_regular_games', 'generate_playoff_games', 'clear_regular_games', 'clear_playoff_games', 'generate_bracket') and 'league_id' in request.form:
            redirect_url += f'#league-{request.form.get("league_id")}'
        return redirect(redirect_url)

    # GET - show league configurations
    # First, ensure leagues are synced from teams
    teams = TeamSeason.get_by_season(year, is_spring)
    league_names = set(t.league for t in teams if t.league)
    LeagueSeason.ensure_leagues_for_season(year, is_spring, league_names)

    # Get all league configs
    league_configs = LeagueSeason.get_by_season(year, is_spring)

    # Count regular teams and placeholders per league
    teams_by_league = {}
    placeholders_by_league = {}
    for team in teams:
        if team.league:
            if team.is_placeholder:
                placeholders_by_league[team.league] = placeholders_by_league.get(team.league, 0) + 1
            else:
                teams_by_league[team.league] = teams_by_league.get(team.league, 0) + 1

    # Count games by type per league
    games_by_league = {}
    for config in league_configs:
        games_by_league[config.league] = Game.count_by_type(year, is_spring, config.league)

    return render_template(
        'seasons/manage_leagues.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        league_configs=league_configs,
        teams_by_league=teams_by_league,
        placeholders_by_league=placeholders_by_league,
        games_by_league=games_by_league,
        playoff_formats=LeagueSeason.PLAYOFF_FORMATS
    )


@seasons_bp.route('/schedule-settings')
@login_required
def schedule_settings_picker():
    """Pick a season for schedule settings"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage schedule settings.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get seasons that have teams
    seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring,
        db.func.count(TeamSeason.team_ID).label('team_count')
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).order_by(
        TeamSeason.year.desc(),
        TeamSeason.is_spring.desc()
    ).all()

    season_list = []
    for year, is_spring, team_count in seasons:
        season_list.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{"Spring" if is_spring else "Fall"} {year}',
            'team_count': team_count
        })

    return render_template(
        'seasons/schedule_settings_picker.html',
        seasons=season_list
    )


@seasons_bp.route('/<int:year>/<int:is_spring>/schedule-settings', methods=['GET', 'POST'])
@login_required
def schedule_settings(year, is_spring):
    """Manage schedule settings for a season (practice/game days, key dates)"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage schedule settings.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Ensure leagues are synced from teams
    teams = TeamSeason.get_by_season(year, is_spring)
    league_names = set(t.league for t in teams if t.league)
    LeagueSeason.ensure_leagues_for_season(year, is_spring, league_names)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'bulk_update':
            from datetime import datetime

            # Get all league configs for this season
            league_configs = LeagueSeason.get_by_season(year, is_spring)
            updated_count = 0
            validation_errors = []

            for config in league_configs:
                # Update day types
                for i, col in enumerate(LeagueSeason.DAY_COLUMNS):
                    day_type = request.form.get(f'league_{config.ID}_day_{i}')
                    setattr(config, col, day_type if day_type else None)

                # Update dates
                first_practice = request.form.get(f'league_{config.ID}_first_practice')
                opening_day = request.form.get(f'league_{config.ID}_opening_day')

                first_practice_date = datetime.strptime(first_practice, '%Y-%m-%d').date() if first_practice else None
                opening_day_date = datetime.strptime(opening_day, '%Y-%m-%d').date() if opening_day else None

                # Validate: first practice cannot be after opening day
                if first_practice_date and opening_day_date and first_practice_date > opening_day_date:
                    validation_errors.append(f'{config.league}: First practice cannot be after opening day')
                else:
                    config.first_practice_date = first_practice_date
                    config.opening_day_date = opening_day_date
                    updated_count += 1

            if validation_errors:
                db.session.rollback()
                for error in validation_errors:
                    flash(error, 'error')
                return redirect(url_for('seasons.schedule_settings', year=year, is_spring=is_spring))

            db.session.commit()
            logger.info(f'Bulk updated schedule settings for {updated_count} leagues in {season_name}')
            flash(f'Saved schedule settings for {updated_count} leagues', 'success')

            return redirect(url_for('seasons.schedule_settings', year=year, is_spring=is_spring))

        elif action == 'update_days':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                # Update day types
                for i, col in enumerate(LeagueSeason.DAY_COLUMNS):
                    day_type = request.form.get(f'day_{i}')
                    setattr(config, col, day_type if day_type else None)
                db.session.commit()
                logger.info(f'Updated day settings for {config.league}')
                flash(f'Updated day settings for {config.league}', 'success')

            return redirect(url_for('seasons.schedule_settings', year=year, is_spring=is_spring) + f'#league-{league_id}')

        elif action == 'update_dates':
            league_id = int(request.form.get('league_id'))
            config = LeagueSeason.query.get(league_id)
            if config and config.year == year and config.is_spring == is_spring:
                from datetime import datetime
                first_practice = request.form.get('first_practice_date')
                opening_day = request.form.get('opening_day_date')

                config.first_practice_date = datetime.strptime(first_practice, '%Y-%m-%d').date() if first_practice else None
                config.opening_day_date = datetime.strptime(opening_day, '%Y-%m-%d').date() if opening_day else None
                db.session.commit()
                logger.info(f'Updated dates for {config.league}: practice={first_practice}, opening={opening_day}')
                flash(f'Updated dates for {config.league}', 'success')

            return redirect(url_for('seasons.schedule_settings', year=year, is_spring=is_spring) + f'#league-{league_id}')

    # GET - show schedule settings
    league_configs = LeagueSeason.get_by_season(year, is_spring)

    return render_template(
        'seasons/schedule_settings.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        league_configs=league_configs,
        day_abbrevs=LeagueSeason.DAY_ABBREVS
    )
