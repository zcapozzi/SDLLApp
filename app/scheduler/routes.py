"""Scheduler routes for generating and managing proposed schedules.

Three-phase workflow:
- Phase 1 (Setup): Create empty game slots via create_slots route
- Phase 2 (Draft): Generate fills in matchups/dates/fields, can regenerate
- Phase 3 (Locked): Save & Lock freezes schedule, manual edits only
"""

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

    # Build league display name mapping
    league_display_names = {}
    for config in league_configs:
        league_obj = League.get_by_name(config.league)
        if league_obj:
            league_display_names[config.league] = league_obj.get_seasonal_name(is_spring)
        else:
            league_display_names[config.league] = config.league

    # Check if season schedule is locked
    is_locked = LeagueSeason.is_season_locked(year, is_spring)

    # Check prerequisites for each league
    prerequisites = {}
    for config in league_configs:
        prereqs = {
            'has_teams': False,
            'has_slots': False,
            'has_game_slots': False,
            'has_dates': False,
            'has_days': False,
            'ready': False,
            'locked': config.schedule_locked,
            'locked_at': config.schedule_locked_at,
            'locked_by': config.schedule_locked_by
        }

        # Check teams
        teams = TeamSeason.query.filter_by(
            year=year, is_spring=is_spring, league=config.league,
            active=1, is_placeholder=0
        ).count()
        prereqs['has_teams'] = teams >= 2
        prereqs['team_count'] = teams

        # Add league settings info for display
        prereqs['games_per_team'] = config.regular_season_games or 10
        prereqs['playoff_format'] = config.playoff_format_display

        # Check field slots
        slots = FieldSlot.query.filter_by(
            year=year, is_spring=is_spring, active=1
        ).count()
        prereqs['has_slots'] = slots > 0
        prereqs['slot_count'] = slots

        # Check if game slots exist (Phase 1 complete)
        game_slots = Game.query.filter_by(
            year=year, is_spring=is_spring, league=config.league,
            active=1, game_type='regular'
        ).count()
        prereqs['has_game_slots'] = game_slots > 0
        prereqs['game_slot_count'] = game_slots

        # Check how many are filled vs empty
        empty_slots = Game.query.filter_by(
            year=year, is_spring=is_spring, league=config.league,
            active=1, game_type='regular'
        ).filter(Game.home_ID.is_(None)).count()
        prereqs['empty_slot_count'] = empty_slots
        prereqs['filled_slot_count'] = game_slots - empty_slots

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
        has_proposal=has_proposal,
        is_locked=is_locked,
        league_display_names=league_display_names
    )


@scheduler_bp.route('/<int:year>/<int:is_spring>/create-slots', methods=['POST'])
@login_required
def create_slots(year, is_spring):
    """Phase 1: Create empty game slots for a league."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to create game slots.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'
    league = request.form.get('league')

    if not league:
        flash('No league specified.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Helper for scroll-back anchor
    def redirect_with_anchor():
        anchor = f'league-{league.replace(" ", "-")}'
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring) + f'#{anchor}')

    # Check if schedule is locked
    config = LeagueSeason.query.filter_by(
        year=year, is_spring=is_spring, league=league, active=1
    ).first()

    if config and config.schedule_locked:
        flash(f'{league} schedule is locked. Unlock it first to make changes.', 'error')
        return redirect_with_anchor()

    # Get number of teams
    teams = TeamSeason.query.filter_by(
        year=year, is_spring=is_spring, league=league, active=1, is_placeholder=0
    ).all()

    if len(teams) < 2:
        flash(f'{league}: Need at least 2 teams to create game slots.', 'error')
        return redirect_with_anchor()

    # Calculate number of games needed
    games_per_team = config.regular_season_games if config else 10
    num_games = (len(teams) * games_per_team) // 2

    # Check if slots already exist
    existing = Game.query.filter_by(
        year=year, is_spring=is_spring, league=league, active=1, game_type='regular'
    ).count()

    if existing > 0:
        flash(f'{league}: {existing} game slots already exist. Delete them first or use "Start Fresh".', 'warning')
        return redirect_with_anchor()

    try:
        new_games = Game.generate_game_slots(year, is_spring, league, num_games, game_type='regular')
        logger.info(f'Created {len(new_games)} empty game slots for {league} in {season_name}')
        flash(f'Created {len(new_games)} empty game slots for {league}. Now generate to fill them.', 'success')
    except Exception as e:
        logger.info(f'Failed to create game slots: {str(e)}')
        flash(f'Error creating game slots: {str(e)}', 'error')

    return redirect_with_anchor()


@scheduler_bp.route('/<int:year>/<int:is_spring>/create-all-slots', methods=['POST'])
@login_required
def create_all_slots(year, is_spring):
    """Phase 1: Create empty game slots for all ready leagues at once."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to create game slots.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Check if schedule is locked
    if LeagueSeason.is_season_locked(year, is_spring):
        flash('Schedule is locked. Unlock it first to create game slots.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Get all league configurations
    league_configs = LeagueSeason.get_by_season(year, is_spring)

    created_leagues = []
    skipped_leagues = []

    for config in league_configs:
        league = config.league

        # Skip locked leagues
        if config.schedule_locked:
            skipped_leagues.append((league, 'locked'))
            continue

        # Check if slots already exist
        existing = Game.query.filter_by(
            year=year, is_spring=is_spring, league=league, active=1, game_type='regular'
        ).count()
        if existing > 0:
            skipped_leagues.append((league, f'{existing} slots exist'))
            continue

        # Get number of teams
        teams = TeamSeason.query.filter_by(
            year=year, is_spring=is_spring, league=league, active=1, is_placeholder=0
        ).all()
        if len(teams) < 2:
            skipped_leagues.append((league, 'needs 2+ teams'))
            continue

        # Check field slots
        slots = FieldSlot.query.filter_by(
            year=year, is_spring=is_spring, active=1
        ).count()
        if slots == 0:
            skipped_leagues.append((league, 'no field slots'))
            continue

        # Check dates configured
        if not config.first_practice_date or not config.opening_day_date:
            skipped_leagues.append((league, 'dates not set'))
            continue

        # Check days configured
        if not config.practice_days and not config.game_days:
            skipped_leagues.append((league, 'days not configured'))
            continue

        # All prerequisites met - create slots
        games_per_team = config.regular_season_games or 10
        num_games = (len(teams) * games_per_team) // 2

        try:
            new_games = Game.generate_game_slots(year, is_spring, league, num_games, game_type='regular')
            created_leagues.append((league, len(new_games)))
            logger.info(f'Created {len(new_games)} empty game slots for {league} in {season_name}')
        except Exception as e:
            skipped_leagues.append((league, f'error: {str(e)}'))
            logger.info(f'Failed to create game slots for {league}: {str(e)}')

    # Build feedback message
    if created_leagues:
        details = ', '.join([f'{league} ({count})' for league, count in created_leagues])
        flash(f'Created game slots for {len(created_leagues)} league(s): {details}. Now generate to fill them.', 'success')

    if skipped_leagues:
        details = ', '.join([f'{league} ({reason})' for league, reason in skipped_leagues])
        flash(f'Skipped {len(skipped_leagues)} league(s): {details}', 'warning')

    if not created_leagues and not skipped_leagues:
        flash('No leagues found to create slots for.', 'info')

    return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/generate', methods=['POST'])
@login_required
def generate(year, is_spring):
    """Phase 2: Generate a proposed schedule (fills in matchups, dates, fields)."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to generate schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Check if schedule is locked
    if LeagueSeason.is_season_locked(year, is_spring):
        flash('Schedule is locked. Unlock it first to regenerate.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Check if this is a "start fresh" request
    start_fresh = request.form.get('start_fresh') == '1'

    # Optionally filter to specific leagues
    selected_leagues = request.form.getlist('leagues')

    try:
        generator = ScheduleGenerator(year, is_spring)
        result = generator.generate(start_fresh=start_fresh)

        # Check if generation produced anything
        summary = result['summary']
        if summary['total_games'] == 0 and summary['total_practices'] == 0 and summary['total_scrimmages'] == 0:
            # Show warnings about why nothing was generated
            if result['warnings']:
                for warning in result['warnings']:
                    flash(warning['message'], 'warning')
            else:
                flash('No games, practices, or scrimmages were generated. Check prerequisites.', 'warning')
            return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

        # Store in session for review
        proposed_key = f'proposed_schedule_{year}_{is_spring}'
        session[proposed_key] = result

        # Verify session storage worked (Flask cookies have ~4KB limit)
        session.modified = True
        if proposed_key not in session or session.get(proposed_key) is None:
            flash('Schedule generated but too large to store in session. Try generating fewer leagues at once.', 'error')
            logger.info(f'Session storage failed for {season_name} - result too large')
            return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

        logger.info(f'Generated schedule for {season_name}: {result["summary"]}')

        # Show summary
        if result['warnings']:
            for warning in result['warnings']:
                flash(warning['message'], 'warning')

        action = 'Regenerated (start fresh)' if start_fresh else 'Generated'
        flash(
            f'{action} {summary["total_games"]} games, {summary["total_practices"]} practices, '
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
    """Phase 3: Save the proposed schedule and lock it."""
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

    # Check if locking is requested (default yes)
    should_lock = request.form.get('lock_schedule', '1') == '1'

    try:
        saved_count = 0
        updated_count = 0

        # First, apply assignments to existing game records
        assignments = proposal.get('assignments', {})
        for game_id, assignment in assignments.items():
            game = Game.query.get(int(game_id))
            if game:
                game.home_ID = assignment['home_id']
                game.away_ID = assignment['away_id']
                if assignment['game_date']:
                    game.game_date = datetime.fromisoformat(assignment['game_date'])
                game.location = assignment['field_id']
                updated_count += 1

        # Then, create new games for any proposed that don't have existing records
        for proposed_game in proposal['games']:
            # Skip if this was an assignment to existing record
            if proposed_game['id'] in [int(k) for k in assignments.keys()]:
                continue

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

        # Lock the schedule if requested
        if should_lock:
            LeagueSeason.lock_all_for_season(year, is_spring, current_user.ID)
            logger.info(f'Locked schedule for {season_name}')

        # Clear the proposal from session
        del session[proposed_key]

        logger.info(f'Saved {saved_count} new games, updated {updated_count} existing games for {season_name}')

        if should_lock:
            flash(f'Successfully saved schedule ({saved_count} new, {updated_count} updated) and locked it!', 'success')
        else:
            flash(f'Successfully saved schedule ({saved_count} new, {updated_count} updated).', 'success')

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


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/team-schedule/<int:team_id>')
@login_required
def api_team_schedule(year, is_spring, team_id):
    """API endpoint to get all games/practices for a team by ID.

    Used by the violations navigator to show team schedules.
    First checks the current proposal, then falls back to saved games.
    """
    games_list = []

    # Get team name for display
    team = TeamSeason.query.filter_by(team_ID=team_id).first()
    team_name = team.computed_display_name if team else f'Team {team_id}'

    # Check if there's a current proposal
    proposed_key = f'proposed_schedule_{year}_{is_spring}'
    proposal = session.get(proposed_key)

    if proposal and 'games' in proposal:
        # Get games from proposal
        for game in proposal['games']:
            home_id = game.get('home_team_id')
            away_id = game.get('away_team_id')

            if team_id in (home_id, away_id):
                games_list.append({
                    'id': game.get('id'),
                    'date': game.get('game_date', '')[:10] if game.get('game_date') else 'TBD',
                    'time': game.get('game_date', '')[11:16] if game.get('game_date') and len(game.get('game_date', '')) > 11 else 'TBD',
                    'type': game.get('game_type', 'regular'),
                    'home': game.get('home_team_name') or 'TBD',
                    'away': game.get('away_team_name') or '-',
                    'field': game.get('field_name', 'TBD'),
                    'league': game.get('league', ''),
                    'is_home': team_id == home_id
                })

    # Always check database for saved games too (in case proposal is incomplete)
    if not games_list:
        games = Game.query.filter_by(
            year=year,
            is_spring=is_spring,
            active=1
        ).all()

        for game in games:
            home_id = game.home_ID
            away_id = game.away_ID

            if team_id in (home_id, away_id):
                home_name = game.home_team.computed_display_name if game.home_team else 'TBD'
                away_name = game.away_team.computed_display_name if game.away_team else '-'

                games_list.append({
                    'id': game.ID,
                    'date': game.game_date.strftime('%Y-%m-%d') if game.game_date else 'TBD',
                    'time': game.game_date.strftime('%H:%M') if game.game_date else 'TBD',
                    'type': game.game_type,
                    'home': home_name,
                    'away': away_name,
                    'field': game.location or 'TBD',
                    'league': game.league,
                    'is_home': team_id == home_id
                })

    # Sort by date/time
    games_list.sort(key=lambda g: (g['date'], g['time']))

    return jsonify({
        'team': team_name,
        'team_id': team_id,
        'season': f'{"Spring" if is_spring else "Fall"} {year}',
        'games': games_list,
        'total': len(games_list)
    })


@scheduler_bp.route('/<int:year>/<int:is_spring>/unlock', methods=['POST'])
@login_required
def unlock(year, is_spring):
    """Unlock the schedule to allow regeneration (admin only)."""
    if not current_user.is_admin():
        flash('Only administrators can unlock schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Confirm action
    confirm = request.form.get('confirm')
    if confirm != 'UNLOCK':
        flash('You must type UNLOCK to confirm this action.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    try:
        LeagueSeason.unlock_all_for_season(year, is_spring)
        logger.info(f'Unlocked schedule for {season_name} by user {current_user.ID}')
        flash(f'Schedule for {season_name} has been unlocked. You can now regenerate.', 'success')
    except Exception as e:
        logger.info(f'Failed to unlock schedule: {str(e)}')
        flash(f'Error unlocking schedule: {str(e)}', 'error')

    return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))


@scheduler_bp.route('/<int:year>/<int:is_spring>/start-fresh', methods=['POST'])
@login_required
def start_fresh(year, is_spring):
    """Clear all assignments and regenerate from scratch."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to modify schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Check if schedule is locked
    if LeagueSeason.is_season_locked(year, is_spring):
        flash('Schedule is locked. Unlock it first to start fresh.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    try:
        # Clear existing assignments
        cleared = Game.clear_slot_assignments(year, is_spring)
        logger.info(f'Cleared {cleared} game assignments for {season_name}')

        # Regenerate
        generator = ScheduleGenerator(year, is_spring)
        result = generator.generate(start_fresh=True)

        # Store in session for review
        proposed_key = f'proposed_schedule_{year}_{is_spring}'
        session[proposed_key] = result

        summary = result['summary']
        flash(
            f'Started fresh: Cleared {cleared} existing assignments. '
            f'Generated {summary["total_games"]} games, {summary["total_practices"]} practices. '
            f'{summary["hard_violations"]} hard violations, {summary["soft_violations"]} soft violations.',
            'success' if summary['hard_violations'] == 0 else 'warning'
        )

        return redirect(url_for('scheduler.review', year=year, is_spring=is_spring))

    except Exception as e:
        logger.info(f'Start fresh failed: {str(e)}')
        flash(f'Error starting fresh: {str(e)}', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))


@scheduler_bp.route('/')
@login_required
def picker():
    """Season picker for the scheduler."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to use the scheduler.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get all seasons with LeagueSeason configs
    from sqlalchemy import distinct
    seasons = db.session.query(
        distinct(LeagueSeason.year),
        LeagueSeason.is_spring
    ).filter_by(active=1).order_by(
        LeagueSeason.year.desc(),
        LeagueSeason.is_spring.desc()
    ).all()

    return render_template(
        'scheduler/picker.html',
        seasons=seasons
    )
