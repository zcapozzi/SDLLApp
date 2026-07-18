"""Scheduler routes for generating and managing proposed schedules."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.models.field_slot import FieldSlot
from app.extensions import db
from app.utils.scheduler import ScheduleGenerator, ScheduleValidator
from app.utils.logging import SDLLLogger

scheduler_bp = Blueprint('scheduler', __name__)
logger = SDLLLogger('scheduler')


@scheduler_bp.route('/<int:year>/<int:is_spring>')
@login_required
def index(year, is_spring):
    """Scheduler overview for a season."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to use the scheduler.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get league configurations
    league_configs = LeagueSeason.get_by_season(year, is_spring)

    # Check prerequisites for each league
    prerequisites = {}
    for config in league_configs:
        prereqs = {
            'has_teams': False,
            'has_slots': False,
            'has_dates': False,
            'has_days': False,
            'ready': False
        }

        # Check teams
        teams = TeamSeason.query.filter_by(
            year=year, is_spring=is_spring, league=config.league,
            active=1, is_placeholder=0
        ).count()
        prereqs['has_teams'] = teams >= 2
        prereqs['team_count'] = teams

        # Check field slots
        slots = FieldSlot.query.filter_by(
            year=year, is_spring=is_spring, active=1
        ).count()
        prereqs['has_slots'] = slots > 0
        prereqs['slot_count'] = slots

        # Check dates
        prereqs['has_dates'] = bool(config.first_practice_date and config.opening_day_date)
        prereqs['first_practice'] = config.first_practice_date
        prereqs['opening_day'] = config.opening_day_date

        # Check days configured
        prereqs['has_days'] = bool(config.practice_days or config.game_days)
        prereqs['practice_days'] = config.practice_days_display
        prereqs['game_days'] = config.game_days_display

        prereqs['ready'] = all([
            prereqs['has_teams'],
            prereqs['has_slots'],
            prereqs['has_dates'],
            prereqs['has_days']
        ])

        prerequisites[config.league] = prereqs

    # Check if there's already a proposed schedule in session
    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    has_proposal = proposed_key in session

    return render_template(
        'scheduler/index.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        league_configs=league_configs,
        prerequisites=prerequisites,
        has_proposal=has_proposal
    )


@scheduler_bp.route('/<int:year>/<int:is_spring>/generate', methods=['POST'])
@login_required
def generate(year, is_spring):
    """Generate a proposed schedule."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to generate schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Optionally filter to specific leagues
    selected_leagues = request.form.getlist('leagues')

    try:
        generator = ScheduleGenerator(year, is_spring)
        result = generator.generate()

        # Store in session for review
        proposed_key = f'proposed_schedule_{year}_{is_spring}'
        session[proposed_key] = result

        logger.info(f'Generated schedule for {season_name}: {result["summary"]}')

        # Show summary
        summary = result['summary']
        if result['warnings']:
            for warning in result['warnings']:
                flash(warning['message'], 'warning')

        flash(
            f'Generated {summary["total_games"]} games, {summary["total_practices"]} practices, '
            f'{summary["total_scrimmages"]} scrimmages. '
            f'{summary["hard_violations"]} hard violations, {summary["soft_violations"]} soft violations.',
            'success' if summary['hard_violations'] == 0 else 'warning'
        )

        return redirect(url_for('scheduler.review', year=year, is_spring=is_spring))

    except Exception as e:
        logger.info(f'Schedule generation failed: {str(e)}')
        flash(f'Error generating schedule: {str(e)}', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/review')
@login_required
def review(year, is_spring):
    """Review the proposed schedule."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to review schedules.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get proposed schedule from session
    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    proposal = session.get(proposed_key)

    if not proposal:
        flash('No proposed schedule found. Generate one first.', 'warning')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Get filter options
    view_mode = request.args.get('view', 'calendar')  # 'calendar' or 'list'
    filter_league = request.args.get('league', '')
    filter_type = request.args.get('type', '')  # 'games', 'practices', 'scrimmages', ''

    games = proposal['games']

    # Apply filters
    if filter_league:
        games = [g for g in games if g['league'] == filter_league]
    if filter_type == 'games':
        games = [g for g in games if g['game_type'] == 'regular']
    elif filter_type == 'practices':
        games = [g for g in games if g['game_type'] == 'practice']
    elif filter_type == 'scrimmages':
        games = [g for g in games if g['game_type'] == 'scrimmage']

    # Group by date for calendar view
    games_by_date = {}
    for game in games:
        if game['game_date']:
            date_str = game['game_date'][:10]  # YYYY-MM-DD
            if date_str not in games_by_date:
                games_by_date[date_str] = []
            games_by_date[date_str].append(game)

    # Get unique leagues for filter
    all_games = proposal['games']
    leagues = sorted(set(g['league'] for g in all_games if g['league']))

    return render_template(
        'scheduler/review.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        proposal=proposal,
        games=games,
        games_by_date=games_by_date,
        violations=proposal['violations'],
        warnings=proposal['warnings'],
        summary=proposal['summary'],
        view_mode=view_mode,
        filter_league=filter_league,
        filter_type=filter_type,
        leagues=leagues
    )


@scheduler_bp.route('/<int:year>/<int:is_spring>/save', methods=['POST'])
@login_required
def save(year, is_spring):
    """Save the proposed schedule to the database."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to save schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get proposed schedule from session
    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    proposal = session.get(proposed_key)

    if not proposal:
        flash('No proposed schedule found.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Check for hard violations
    hard_violations = [v for v in proposal['violations'] if v['severity'] == 'hard']
    if hard_violations and not request.form.get('force_save'):
        flash(f'Cannot save: {len(hard_violations)} hard rule violations. Fix them or check "Force save" to proceed.', 'error')
        return redirect(url_for('scheduler.review', year=year, is_spring=is_spring))

    try:
        saved_count = 0
        for proposed_game in proposal['games']:
            # Parse the game date
            game_date = None
            if proposed_game['game_date']:
                game_date = datetime.fromisoformat(proposed_game['game_date'])

            # Determine game type and is_scrimmage flag
            game_type = proposed_game['game_type']
            is_scrimmage = 1 if game_type == 'scrimmage' else 0
            if game_type == 'scrimmage':
                game_type = 'regular'  # Scrimmages are stored as regular with flag

            # Create the game record
            game = Game(
                active=1,
                year=year,
                is_spring=is_spring,
                league=proposed_game['league'],
                home_ID=proposed_game['home_team_id'],
                away_ID=proposed_game['away_team_id'],  # None for practices
                location=proposed_game['field_id'],
                game_date=game_date,
                game_type=game_type if game_type != 'practice' else 'regular',
                is_scrimmage=is_scrimmage,
                status='scheduled'
            )
            db.session.add(game)
            saved_count += 1

        db.session.commit()

        # Clear the proposal from session
        del session[proposed_key]

        logger.info(f'Saved {saved_count} games for {season_name}')
        flash(f'Successfully saved {saved_count} games/practices to the schedule!', 'success')

        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    except Exception as e:
        db.session.rollback()
        logger.info(f'Failed to save schedule: {str(e)}')
        flash(f'Error saving schedule: {str(e)}', 'error')
        return redirect(url_for('scheduler.review', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/clear', methods=['POST'])
@login_required
def clear(year, is_spring):
    """Clear the proposed schedule from session."""
    if not current_user.can_edit_schedule():
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    if proposed_key in session:
        del session[proposed_key]
        flash('Proposed schedule cleared.', 'success')

    return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/validate', methods=['POST'])
@login_required
def validate_existing(year, is_spring):
    """Validate the existing schedule against rules."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to validate schedules.', 'error')
        return redirect(url_for('seasons.view', year=year, is_spring=is_spring))

    # Get existing games
    games = Game.get_by_season(year, is_spring)

    # Validate
    validator = ScheduleValidator(year, is_spring)
    violations = validator.validate(games)

    # Store results
    validation_key = f'validation_results_{year}_{is_spring}'
    session[validation_key] = {
        'violations': [v.to_dict() for v in violations],
        'game_count': len(games),
        'timestamp': datetime.now().isoformat()
    }

    hard_count = len([v for v in violations if v.severity == 'hard'])
    soft_count = len([v for v in violations if v.severity == 'soft'])

    if violations:
        flash(f'Validation complete: {hard_count} hard violations, {soft_count} soft violations.', 'warning')
    else:
        flash('Validation complete: No violations found!', 'success')

    return redirect(url_for('scheduler.validation_results', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/validation')
@login_required
def validation_results(year, is_spring):
    """View validation results for existing schedule."""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    validation_key = f'validation_results_{year}_{is_spring}'
    results = session.get(validation_key)

    if not results:
        flash('No validation results. Run validation first.', 'info')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    return render_template(
        'scheduler/validation.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        results=results
    )


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/proposal')
@login_required
def api_proposal(year, is_spring):
    """API endpoint to get the current proposal."""
    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    proposal = session.get(proposed_key)

    if not proposal:
        return jsonify({'error': 'No proposal found'}), 404

    return jsonify(proposal)
