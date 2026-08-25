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
from app.models.schedule_proposal import ScheduleProposal
from app.extensions import db
from app.utils.scheduler import ScheduleGenerator, ScheduleValidator
from app.utils.logging import SDLLLogger

scheduler_bp = Blueprint('scheduler', __name__)
logger = SDLLLogger('scheduler')

# All scheduling rules with their metadata
ALL_RULES = {
    # Tier I - Hard Rules
    'd1': {'name': 'One activity per day', 'severity': 'hard', 'description': 'Max one game or practice per team per day'},
    'slot': {'name': 'Field double-booked', 'severity': 'hard', 'description': 'No two games/practices at same time on same field'},
    'f1': {'name': 'Practice field capacity', 'severity': 'hard', 'description': 'Enforces field practice_capacity setting'},
    'f1c': {'name': 'Cross-league practice sharing', 'severity': 'hard', 'description': 'Teams sharing practice slot must be same league'},
    'g1': {'name': 'Time restrictions', 'severity': 'hard', 'description': 'No games/practices outside allowed time window'},
    'h1': {'name': 'Season blackouts', 'severity': 'hard', 'description': 'No activities on league blackout dates'},
    'h2': {'name': 'Field availability', 'severity': 'hard', 'description': 'No activities before field start date or on field blackouts'},
    # Tier II - Soft Rules
    'a1': {'name': 'Matchup balance', 'severity': 'soft', 'description': 'Play everyone at least once; max 1 game difference between pairs'},
    'a2': {'name': 'Alternate home/away', 'severity': 'soft', 'description': 'No team is home twice against same opponent while never away'},
    'b1': {'name': 'Home/away balance', 'severity': 'soft', 'description': 'Balance home/away per team (max 1 game difference)'},
    'b2': {'name': 'Early/late balance', 'severity': 'soft', 'description': 'Balance early (5:30) vs late (7:30) games per team'},
    'c1': {'name': 'Practice field balance', 'severity': 'soft', 'description': 'Spread practices across available fields'},
    'c4': {'name': 'Practice count balance', 'severity': 'soft', 'description': 'No team should have 2+ more practices than another'},
    'e1': {'name': 'Minimum games', 'severity': 'soft', 'description': 'Each team plays required number of regular season games'},
    'f1b': {'name': 'Day-of-week game balance', 'severity': 'soft', 'description': 'Balance game days across teams'},
    'gap': {'name': 'Same team gap', 'severity': 'soft', 'description': 'No back-to-back games against same opponent'},
}


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

    # Check if there's already a proposed schedule in database
    proposal = ScheduleProposal.get_for_season(year, is_spring)
    has_proposal = proposal is not None

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
    import sys
    print(f"[ROUTE] Generate called for {year}/{is_spring}", flush=True)

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

    print(f"[ROUTE] Starting ScheduleGenerator", flush=True)
    try:
        import time
        start_time = time.time()
        print(f"[ROUTE] Creating generator object", flush=True)
        generator = ScheduleGenerator(year, is_spring)
        print(f"[ROUTE] Calling generate()", flush=True)
        result = generator.generate(start_fresh=start_fresh)
        generation_time = time.time() - start_time
        print(f"[ROUTE] Generation complete in {generation_time:.2f}s", flush=True)

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

        # Store in database for persistence and sharing
        user_id = current_user.ID if current_user.is_authenticated else None
        ScheduleProposal.create_or_update(year, is_spring, result, user_id)

        logger.info(f'Generated schedule for {season_name}: {result["summary"]}')

        # Show summary
        if result['warnings']:
            for warning in result['warnings']:
                flash(warning['message'], 'warning')

        action = 'Regenerated (start fresh)' if start_fresh else 'Generated'
        flash(
            f'{action} {summary["total_games"]} games, {summary["total_practices"]} practices, '
            f'{summary["total_scrimmages"]} scrimmages in {generation_time:.1f}s. '
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

    # Get proposed schedule from database
    proposal_record = ScheduleProposal.get_for_season(year, is_spring)

    if not proposal_record:
        flash('No proposed schedule found. Generate one first.', 'warning')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Extract data from proposal record
    proposal = proposal_record.data

    # Get filter options
    view_mode = request.args.get('view', 'calendar')  # 'calendar' or 'list'
    filter_league = request.args.get('league', '')
    filter_type = request.args.get('type', '')  # 'games', 'practices', 'scrimmages', ''

    games = proposal.get('games', [])

    # Include manually-created league practices from the database
    # These are division-wide practices that were created outside the scheduler
    league_practices = Game.query.filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        Game.is_league_practice == True
    ).all()

    # Build field lookup for resolving location IDs to names
    from app.models.field import Field
    all_fields = Field.query.filter_by(active=1).all()
    field_lookup = {str(f.ID): f.location_title for f in all_fields}
    field_lookup.update({f.location_title: f.location_title for f in all_fields})

    for lp in league_practices:
        # Use field_id FK if available, otherwise fall back to location string
        lp_field_id = lp.field_id
        field_name = lp.field_name  # Uses the model's field_name property (FK lookup)

        # Convert to proposal-style dict format
        lp_dict = {
            'id': f'lp_{lp.ID}',  # Prefix to distinguish from proposal games
            'game_type': 'practice',
            'league': lp.league,
            'year': lp.year,
            'is_spring': lp.is_spring,
            'home_team_id': lp.home_ID,
            'home_team_name': lp.home_team.scheduler_display_name if lp.home_team else 'Unknown',
            'away_team_id': None,
            'away_team_name': None,
            'field_id': lp_field_id,
            'field_name': field_name,
            'game_date': lp.game_date.isoformat() if lp.game_date else None,
            'is_scrimmage': False,
            'is_league_practice': True,
            'slot_id': None
        }
        games.append(lp_dict)

    # Also add to proposal for template access (field usage matrix, etc.)
    proposal['games'] = games

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

    # Get violated rule codes
    violated_rules = set(v['rule_code'] for v in proposal['violations'])

    # Build list of passed rules (rules with no violations)
    passed_rules = {code: info for code, info in ALL_RULES.items() if code not in violated_rules}

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
        leagues=leagues,
        all_rules=ALL_RULES,
        passed_rules=passed_rules
    )


@scheduler_bp.route('/<int:year>/<int:is_spring>/save', methods=['POST'])
@login_required
def save(year, is_spring):
    """Phase 3: Save the proposed schedule and lock it."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to save schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get proposed schedule from database
    proposal_record = ScheduleProposal.get_for_season(year, is_spring)

    if not proposal_record:
        flash('No proposed schedule found.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    proposal = proposal_record.data

    # Check for hard violations
    hard_violations = [v for v in proposal.get('violations', []) if v['severity'] == 'hard']
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
                # Set field_id FK only - field_name property handles display
                game.field_id = assignment.get('field_id')
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

            # Determine game type and flags
            game_type = proposed_game['game_type']
            is_scrimmage = 1 if game_type == 'scrimmage' else 0
            is_league_practice = proposed_game.get('is_league_practice', False)

            # Normalize game_type for storage
            if game_type == 'scrimmage':
                game_type = 'regular'  # Scrimmages are stored as regular with is_scrimmage flag
            elif game_type == 'division_practice':
                game_type = 'practice'
                is_league_practice = True

            # Create the game record
            # Set field_id FK only - field_name property handles display
            game = Game(
                active=1,
                year=year,
                is_spring=is_spring,
                league=proposed_game['league'],
                home_ID=proposed_game['home_team_id'],
                away_ID=proposed_game['away_team_id'],  # None for practices
                field_id=proposed_game.get('field_id'),
                game_date=game_date,
                game_type=game_type,
                is_scrimmage=is_scrimmage,
                is_league_practice=is_league_practice,
                status='scheduled'
            )
            db.session.add(game)
            saved_count += 1

        db.session.commit()

        # Lock the schedule if requested
        if should_lock:
            LeagueSeason.lock_all_for_season(year, is_spring, current_user.ID)
            logger.info(f'Locked schedule for {season_name}')

        # Mark proposal as accepted and clear it
        ScheduleProposal.mark_accepted(year, is_spring)
        ScheduleProposal.delete_for_season(year, is_spring)

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
    """Clear the proposed schedule from database."""
    if not current_user.can_edit_schedule():
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    proposal = ScheduleProposal.get_for_season(year, is_spring)
    if proposal:
        ScheduleProposal.delete_for_season(year, is_spring)
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
    proposal_record = ScheduleProposal.get_for_season(year, is_spring)

    if not proposal_record:
        return jsonify({'error': 'No proposal found'}), 404

    return jsonify(proposal_record.data)


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/trace/<date_str>')
@login_required
def api_trace_date(year, is_spring, date_str):
    """API endpoint to get slot assignment decisions for a specific date.

    Returns detailed trace of why each slot was assigned, skipped, or rejected.
    """
    # Get proposed schedule from database
    proposal_record = ScheduleProposal.get_for_season(year, is_spring)

    if not proposal_record:
        return jsonify({'error': 'No proposal found. Generate a schedule first.'}), 404

    proposal = proposal_record.data
    slot_decisions = proposal.get('slot_decisions', {})

    # Get decisions for this date
    decisions = slot_decisions.get(date_str, [])

    # Also gather what games were scheduled on this date for context
    games_on_date = []
    for game in proposal.get('games', []):
        if game.get('game_date', '')[:10] == date_str:
            games_on_date.append({
                'type': game.get('game_type'),
                'league': game.get('league'),
                'home': game.get('home_team_name'),
                'away': game.get('away_team_name'),
                'field': game.get('field_name'),
                'time': game.get('game_date', '')[11:16] if game.get('game_date') and len(game.get('game_date', '')) > 11 else 'TBD'
            })

    # Group decisions by league for easier reading
    decisions_by_league = {}
    for d in decisions:
        league = d.get('league', 'Unknown')
        if league not in decisions_by_league:
            decisions_by_league[league] = []
        decisions_by_league[league].append(d)

    # Summary stats
    summary = {
        'total_decisions': len(decisions),
        'assigned': len([d for d in decisions if d.get('decision') == 'assigned']),
        'skipped': len([d for d in decisions if d.get('decision') == 'skipped']),
        'rejected': len([d for d in decisions if d.get('decision') == 'rejected']),
        'games_scheduled': len(games_on_date),
        'leagues': list(decisions_by_league.keys())
    }

    return jsonify({
        'date': date_str,
        'season': f'{"Spring" if is_spring else "Fall"} {year}',
        'decisions': decisions,
        'decisions_by_league': decisions_by_league,
        'games_on_date': games_on_date,
        'summary': summary
    })


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
    team_name = team.scheduler_display_name if team else f'Team {team_id}'

    # Check if there's a current proposal in database
    proposal_record = ScheduleProposal.get_for_season(year, is_spring)
    proposal = proposal_record.data if proposal_record else None

    if proposal and 'games' in proposal:
        # Get games from proposal
        for game in proposal['games']:
            home_id = game.get('home_team_id')
            away_id = game.get('away_team_id')

            if team_id in (home_id, away_id):
                # Calculate day abbreviation from date
                day_abbrev = ''
                game_date_str = game.get('game_date', '')
                if game_date_str and len(game_date_str) >= 10:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(game_date_str[:19])
                        day_abbrev = dt.strftime('%a')[:3]  # Mon, Tue, etc.
                    except (ValueError, TypeError):
                        pass

                games_list.append({
                    'id': game.get('id'),
                    'date': game_date_str[:10] if game_date_str else 'TBD',
                    'time': game_date_str[11:16] if game_date_str and len(game_date_str) > 11 else 'TBD',
                    'type': game.get('game_type', 'regular'),
                    'home': game.get('home_team_name') or 'TBD',
                    'away': game.get('away_team_name') or '-',
                    'field': game.get('field_name', 'TBD'),
                    'league': game.get('league', ''),
                    'is_home': team_id == home_id,
                    'day_abbrev': day_abbrev
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
                home_name = game.home_team.scheduler_display_name if game.home_team else 'TBD'
                away_name = game.away_team.scheduler_display_name if game.away_team else '-'

                games_list.append({
                    'id': game.ID,
                    'date': game.game_date.strftime('%Y-%m-%d') if game.game_date else 'TBD',
                    'time': game.game_date.strftime('%H:%M') if game.game_date else 'TBD',
                    'type': game.game_type,
                    'home': home_name,
                    'away': away_name,
                    'field': game.location or 'TBD',
                    'league': game.league,
                    'is_home': team_id == home_id,
                    'day_abbrev': game.game_date.strftime('%a')[:3] if game.game_date else ''
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


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/add-event', methods=['POST'])
@login_required
def api_add_event(year, is_spring):
    """API endpoint to add a new game/practice/scrimmage.

    Works with both active proposals and saved (locked) schedules.

    Expects JSON body:
    {
        "game_type": "regular"|"practice"|"scrimmage"|"division_practice",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "field_name": str,
        "league": str,
        "home_team_id": int (optional for division_practice),
        "away_team_id": int (optional for practices)
    }
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Validate required fields
        game_type = data.get('game_type')
        date_str = data.get('date')
        time_str = data.get('time')
        field_name = data.get('field_name')
        league = data.get('league')

        if not all([game_type, date_str, time_str, field_name, league]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Get team info
        home_team_id = data.get('home_team_id')
        away_team_id = data.get('away_team_id')

        if home_team_id:
            home_team_id = int(home_team_id)
        if away_team_id:
            away_team_id = int(away_team_id)

        home_team_name = None
        away_team_name = None

        if home_team_id:
            home_team = TeamSeason.query.filter_by(team_ID=home_team_id).first()
            home_team_name = home_team.scheduler_display_name if home_team else f'Team {home_team_id}'

        if away_team_id:
            away_team = TeamSeason.query.filter_by(team_ID=away_team_id).first()
            away_team_name = away_team.scheduler_display_name if away_team else f'Team {away_team_id}'

        # For division practice, use league name as the "team"
        is_division_practice = game_type == 'division_practice'
        if is_division_practice:
            home_team_name = league

        # Parse game datetime
        from datetime import datetime as dt
        game_datetime = dt.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')

        # Check if there's an active proposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)

        if proposal:
            # Add to proposal
            game_datetime_str = f'{date_str}T{time_str}:00'
            new_id = proposal.add_game({
                'game_type': 'practice' if is_division_practice else game_type,
                'game_date': game_datetime_str,
                'field_name': field_name,
                'league': league,
                'home_team_id': home_team_id,
                'home_team_name': home_team_name,
                'away_team_id': away_team_id,
                'away_team_name': away_team_name
            })
            logger.info(f'API: Added {game_type} to proposal - {league} at {field_name} on {date_str} {time_str}')
            target = 'proposal'
        else:
            # No proposal - add directly to Game table (saved/locked schedule)
            actual_game_type = 'practice' if is_division_practice or game_type == 'practice' else game_type
            is_scrimmage = 1 if game_type == 'scrimmage' else 0

            new_game = Game(
                year=year,
                is_spring=is_spring,
                game_date=game_datetime,
                home_ID=home_team_id,
                away_ID=away_team_id,
                league=league,
                location=field_name,
                game_type=actual_game_type,
                is_scrimmage=is_scrimmage,
                is_league_practice=is_division_practice,
                status='scheduled',
                active=1
            )
            db.session.add(new_game)
            db.session.commit()
            new_id = new_game.ID
            logger.info(f'API: Added {game_type} to saved schedule (ID {new_id}) - {league} at {field_name} on {date_str} {time_str}')
            target = 'schedule'

        return jsonify({
            'success': True,
            'message': f'{game_type.replace("_", " ").title()} added to {target}',
            'game_id': new_id
        })

    except Exception as e:
        logger.error(f'API add-event error: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/event-options')
@login_required
def api_event_options(year, is_spring):
    """API endpoint to get options for adding a new event.

    Query params:
        date: YYYY-MM-DD (optional, to filter available times)
        field: Field name (optional, to filter)

    Returns leagues, teams, fields, and available time slots.
    """
    from app.models.field import Field

    date_str = request.args.get('date')

    # Get active leagues for this season
    league_configs = LeagueSeason.get_by_season(year, is_spring)
    leagues = [{'name': c.league, 'has_scrimmages': c.has_scrimmages} for c in league_configs]

    # Get all teams grouped by league
    teams_by_league = {}
    all_teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1,
        is_placeholder=0
    ).all()

    for team in all_teams:
        if team.league not in teams_by_league:
            teams_by_league[team.league] = []
        teams_by_league[team.league].append({
            'id': team.team_ID,
            'name': team.scheduler_display_name
        })

    # Get available fields
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()
    field_list = [{'id': f.ID, 'name': f.location_title} for f in fields]

    # Get common time slots (from field slots)
    time_slots = set()
    slots = FieldSlot.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).all()

    for slot in slots:
        if slot.start_time:
            time_str = slot.start_time.strftime('%H:%M')
            time_slots.add(time_str)

    # Standard time slots if none found
    if not time_slots:
        time_slots = {'17:30', '19:00', '19:30', '09:00', '10:30', '12:00'}

    return jsonify({
        'leagues': sorted(leagues, key=lambda x: x['name']),
        'teams_by_league': teams_by_league,
        'fields': field_list,
        'time_slots': sorted(list(time_slots))
    })


@scheduler_bp.route('/api/<int:year>/<int:is_spring>/delete-event', methods=['POST'])
@login_required
def api_delete_event(year, is_spring):
    """API endpoint to delete a game.

    Works with both active proposals and saved (locked) schedules.
    For saved games, performs a soft delete (sets active=0).
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        game_id = data.get('game_id')

        if game_id is None:
            return jsonify({'success': False, 'message': 'game_id is required'}), 400

        game_id = int(game_id)

        # Check if there's an active proposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)

        if proposal:
            # Try to delete from proposal first
            if proposal.delete_game(game_id):
                logger.info(f'API: Deleted game {game_id} from proposal')
                return jsonify({'success': True, 'message': 'Event deleted from proposal'})

            # If game_id is positive, it might be a saved game shown in the proposal view
            if game_id > 0:
                game = Game.query.get(game_id)
                if game and game.year == year and game.is_spring == is_spring:
                    game.active = 0
                    db.session.commit()
                    logger.info(f'API: Soft-deleted saved game {game_id}')
                    return jsonify({'success': True, 'message': 'Event deleted from schedule'})

            return jsonify({'success': False, 'message': 'Game not found'}), 404
        else:
            # No proposal - delete from Game table (saved/locked schedule)
            game = Game.query.get(game_id)
            if not game:
                return jsonify({'success': False, 'message': 'Game not found'}), 404

            if game.year != year or game.is_spring != is_spring:
                return jsonify({'success': False, 'message': 'Game not in this season'}), 400

            # Soft delete
            game.active = 0
            db.session.commit()
            logger.info(f'API: Soft-deleted saved game {game_id}')
            return jsonify({'success': True, 'message': 'Event deleted from schedule'})

    except Exception as e:
        logger.error(f'API delete-event error: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500


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


@scheduler_bp.route('/<int:year>/<int:is_spring>/clear-league', methods=['POST'])
@login_required
def clear_league(year, is_spring):
    """Clear all games for a single league (while schedule is not locked)."""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to modify schedules.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    league = request.form.get('league')
    clear_type = request.form.get('clear_type', 'all')  # 'all', 'regular', 'playoff', 'practice'

    if not league:
        flash('No league specified.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    # Check if league schedule is locked
    config = LeagueSeason.query.filter_by(
        year=year, is_spring=is_spring, league=league, active=1
    ).first()

    if config and config.schedule_locked:
        flash(f'{league} schedule is locked. Unlock it first to clear games.', 'error')
        return redirect(url_for('scheduler.index', year=year, is_spring=is_spring))

    try:
        # Build query based on clear type
        query = Game.query.filter_by(
            year=year, is_spring=is_spring, league=league, active=1
        )

        if clear_type == 'regular':
            query = query.filter_by(game_type='regular', is_scrimmage=0)
        elif clear_type == 'playoff':
            query = query.filter_by(game_type='playoff')
        elif clear_type == 'practice':
            query = query.filter_by(game_type='practice')
        elif clear_type == 'scrimmage':
            query = query.filter_by(is_scrimmage=1)
        # 'all' uses the unfiltered query

        games = query.all()
        count = len(games)

        # Soft delete the games
        for game in games:
            game.active = 0

        db.session.commit()

        type_label = {
            'all': 'all games',
            'regular': 'regular season games',
            'playoff': 'playoff games',
            'practice': 'practice slots',
            'scrimmage': 'scrimmage games'
        }.get(clear_type, 'games')

        logger.info(f'Cleared {count} {type_label} for {league}')
        flash(f'Cleared {count} {type_label} for {league}.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.info(f'Failed to clear games for {league}: {str(e)}')
        flash(f'Error clearing games: {str(e)}', 'error')

    anchor = f'league-{league.replace(" ", "-")}'
    return redirect(url_for('scheduler.index', year=year, is_spring=is_spring) + f'#{anchor}')


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
        import time
        # Clear existing assignments
        cleared = Game.clear_slot_assignments(year, is_spring)
        logger.info(f'Cleared {cleared} game assignments for {season_name}')

        # Regenerate with timing
        start_time = time.time()
        generator = ScheduleGenerator(year, is_spring)
        result = generator.generate(start_fresh=True)
        generation_time = time.time() - start_time

        # Store in database for persistence
        user_id = current_user.ID if current_user.is_authenticated else None
        ScheduleProposal.create_or_update(year, is_spring, result, user_id)

        summary = result['summary']
        flash(
            f'Started fresh: Cleared {cleared} existing assignments. '
            f'Generated {summary["total_games"]} games, {summary["total_practices"]} practices in {generation_time:.1f}s. '
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


# ============================================================================
# Email Coaches Feature
# ============================================================================

def can_email_coaches():
    """Check if current user can use email coaches feature."""
    if not current_user.is_authenticated:
        return False
    return current_user.has_role('admin', 'scheduler', 'SBPlayerAgent', 'BBPlayerAgent')


@scheduler_bp.route('/email-coaches', methods=['GET', 'POST'])
@login_required
def email_coaches():
    """Compose and send email blast to coaches."""
    if not can_email_coaches():
        flash('You do not have permission to email coaches.', 'error')
        return redirect(url_for('main.dashboard'))

    from app.models.scheduled_email import ScheduledEmail
    from app.services.email_blast_service import (
        get_coaches_by_leagues, html_to_plain_text, parse_manual_recipients,
        send_scheduled_email
    )

    # Get current season
    current_season = LeagueSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'error')
        return redirect(url_for('main.dashboard'))

    year = current_season.year
    is_spring = current_season.is_spring
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get available leagues for this season
    league_configs = LeagueSeason.get_by_season(year, is_spring)
    leagues = [config.league for config in league_configs]

    if request.method == 'POST':
        # Get form data
        selected_leagues = request.form.getlist('leagues')
        subject = request.form.get('subject', '').strip()
        body_html = request.form.get('body_html', '').strip()
        send_mode = request.form.get('send_mode', 'cc')
        manual_recipients_text = request.form.get('manual_recipients', '').strip()
        schedule_date = request.form.get('schedule_date', '').strip()
        schedule_time = request.form.get('schedule_time', '').strip()
        action = request.form.get('action', 'send_now')

        # Parse manual recipients first
        manual_recipients = parse_manual_recipients(manual_recipients_text)

        # Validate - need either leagues selected OR manual recipients
        if not selected_leagues and not manual_recipients:
            flash('Please select at least one league or enter manual recipients.', 'error')
            return redirect(url_for('scheduler.email_coaches'))

        if not subject:
            flash('Please enter a subject.', 'error')
            return redirect(url_for('scheduler.email_coaches'))

        if not body_html:
            flash('Please enter a message.', 'error')
            return redirect(url_for('scheduler.email_coaches'))

        # Get coach recipients (only if leagues selected)
        recipients = []
        if selected_leagues:
            recipients = get_coaches_by_leagues(year, is_spring, selected_leagues)

        # Ensure we have at least one recipient total
        if not recipients and not manual_recipients:
            flash('No recipients found. Please select leagues with coaches or enter manual recipients.', 'error')
            return redirect(url_for('scheduler.email_coaches'))

        # Convert HTML to plain text
        body_text = html_to_plain_text(body_html)

        # Get reply-to from current user
        reply_to = current_user.email or 'scheduler@sdll.org'

        # Parse scheduled time
        scheduled_for = None
        if action == 'schedule' and schedule_date and schedule_time:
            try:
                scheduled_for = datetime.strptime(f'{schedule_date} {schedule_time}', '%Y-%m-%d %H:%M')
            except ValueError:
                flash('Invalid schedule date/time format.', 'error')
                return redirect(url_for('scheduler.email_coaches'))

        # Create the scheduled email
        email_record = ScheduledEmail.create_coach_blast(
            user_id=current_user.ID,
            year=year,
            is_spring=is_spring,
            leagues=selected_leagues,
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            reply_to=reply_to,
            send_mode=send_mode,
            manual_recipients=manual_recipients,
            scheduled_for=scheduled_for
        )

        # Send immediately if not scheduled
        if action == 'send_now':
            send_scheduled_email(email_record)

            if email_record.status == ScheduledEmail.STATUS_SENT:
                flash(f'Email sent successfully to {email_record.sent_count} recipients!', 'success')
            elif email_record.status == ScheduledEmail.STATUS_PARTIAL:
                flash(f'Email partially sent: {email_record.sent_count} sent, {email_record.failed_count} failed.', 'warning')
            else:
                flash(f'Email failed to send: {email_record.error_message}', 'error')
        else:
            flash(f'Email scheduled for {scheduled_for.strftime("%b %d, %Y at %I:%M %p")}!', 'success')

        return redirect(url_for('scheduler.email_coaches_history'))

    return render_template(
        'scheduler/email_coaches.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        leagues=leagues,
        user_email=current_user.email or 'scheduler@sdll.org'
    )


@scheduler_bp.route('/email-coaches/history')
@login_required
def email_coaches_history():
    """View email history."""
    if not can_email_coaches():
        flash('You do not have permission to view email history.', 'error')
        return redirect(url_for('main.dashboard'))

    from app.models.scheduled_email import ScheduledEmail

    emails = ScheduledEmail.get_history(limit=50)

    return render_template(
        'scheduler/email_history.html',
        emails=emails
    )


@scheduler_bp.route('/api/coach-email-preview')
@login_required
def api_coach_email_preview():
    """Get recipient list preview for selected leagues."""
    if not can_email_coaches():
        return jsonify({'error': 'Permission denied'}), 403

    from app.services.email_blast_service import get_coaches_by_leagues

    leagues = request.args.get('leagues', '').split(',')
    leagues = [l.strip() for l in leagues if l.strip()]
    show_emails = request.args.get('show_emails', 'false') == 'true'

    if not leagues:
        return jsonify({'coach_count': 0, 'team_count': 0, 'recipients': []})

    # Get current season
    current_season = LeagueSeason.get_current_season()
    if not current_season:
        return jsonify({'error': 'No active season'}), 400

    coaches = get_coaches_by_leagues(current_season.year, current_season.is_spring, leagues)

    # Count unique teams
    teams = set(c['team'] for c in coaches)

    response = {
        'coach_count': len(coaches),
        'team_count': len(teams)
    }

    if show_emails:
        response['recipients'] = coaches

    return jsonify(response)
