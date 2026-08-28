"""Game management routes"""

from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.field import Field
from app.models.organization import Organization
from app.extensions import db
from app.utils.logging import SDLLLogger

games_bp = Blueprint('games', __name__)
logger = SDLLLogger('games')


# =============================================================================
# API Endpoints for Drag-and-Drop Game Editing
# =============================================================================

@games_bp.route('/api/move-game', methods=['POST'])
@login_required
def api_move_game():
    """
    API endpoint for moving a game via drag-and-drop.

    Expects JSON body:
    {
        "game_id": int,
        "new_field": str (optional),
        "new_time": str (HH:MM format, optional),
        "new_date": str (YYYY-MM-DD format, optional),
        "reason": str (optional)
    }

    Returns JSON with success status and message.
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        game_id = data.get('game_id')
        if not game_id:
            return jsonify({'success': False, 'message': 'game_id is required'}), 400

        new_field = data.get('new_field')
        new_time = data.get('new_time')
        new_date = data.get('new_date')
        reason = data.get('reason', '')
        is_proposed = data.get('is_proposed', False)
        year = data.get('year')
        is_spring = data.get('is_spring')

        # Check if this is a proposed game (not yet saved to Game table)
        if is_proposed and year is not None and is_spring is not None:
            from app.models.schedule_proposal import ScheduleProposal
            proposal = ScheduleProposal.get_for_season(int(year), int(is_spring))

            if not proposal:
                return jsonify({'success': False, 'message': 'No proposal found for this season'}), 404

            # Update the game in the proposal
            updated = proposal.update_game(
                game_id=int(game_id),
                new_field=new_field,
                new_time=new_time,
                new_date=new_date
            )

            if not updated:
                return jsonify({'success': False, 'message': f'Game {game_id} not found in proposal'}), 404

            logger.info(f'API: Moved proposed game {game_id} - field={new_field}, time={new_time}, date={new_date}')

            return jsonify({
                'success': True,
                'message': 'Proposed game moved successfully',
                'game_id': game_id,
                'notifications_queued': 0,
                'change_id': None
            })

        # Otherwise, update the saved game in the Game table
        from app.services.game_changes import GameChangeService

        # Move the game
        game, change, notifications_queued = GameChangeService.move_game(
            game_id=int(game_id),
            user_id=current_user.ID,
            new_field=new_field,
            new_time=new_time,
            new_date=new_date,
            reason=reason
        )

        logger.info(f'API: Moved game {game_id} - field={new_field}, time={new_time}, date={new_date}')

        return jsonify({
            'success': True,
            'message': 'Game moved successfully',
            'game_id': game.ID,
            'notifications_queued': notifications_queued,
            'change_id': change.id if change else None
        })

    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        logger.error(f'API: Error moving game: {e}')
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@games_bp.route('/api/cancel-game', methods=['POST'])
@login_required
def api_cancel_game():
    """
    API endpoint for cancelling a game via drag-and-drop to cancel zone.

    Expects JSON body:
    {
        "game_id": int,
        "reason": str (optional),
        "is_proposed": bool (optional),
        "year": int (optional, required if is_proposed),
        "is_spring": int (optional, required if is_proposed)
    }

    Returns JSON with success status and message.
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        game_id = data.get('game_id')
        if not game_id:
            return jsonify({'success': False, 'message': 'game_id is required'}), 400

        reason = data.get('reason', '')
        is_proposed = data.get('is_proposed', False)
        year = data.get('year')
        is_spring = data.get('is_spring')

        # Check if this is a proposed game (negative ID or explicitly marked)
        if is_proposed and year is not None and is_spring is not None:
            from app.models.schedule_proposal import ScheduleProposal
            proposal = ScheduleProposal.get_for_season(int(year), int(is_spring))

            if not proposal:
                return jsonify({'success': False, 'message': 'No proposal found for this season'}), 404

            # Delete the game from the proposal
            deleted = proposal.delete_game(int(game_id))

            if not deleted:
                return jsonify({'success': False, 'message': f'Game {game_id} not found in proposal'}), 404

            logger.info(f'API: Deleted proposed game {game_id} from proposal')

            return jsonify({
                'success': True,
                'message': 'Proposed game deleted',
                'game_id': game_id,
                'notifications_queued': 0,
                'change_id': None
            })

        # Otherwise, cancel the saved game in the Game table
        from app.services.game_changes import GameChangeService

        # Cancel the game
        game, change, notifications_queued = GameChangeService.cancel_game(
            game_id=int(game_id),
            user_id=current_user.ID,
            reason=reason
        )

        logger.info(f'API: Cancelled game {game_id} - reason: {reason}')

        return jsonify({
            'success': True,
            'message': 'Game cancelled',
            'game_id': game.ID,
            'notifications_queued': notifications_queued,
            'change_id': change.id if change else None
        })

    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        logger.error(f'API: Error cancelling game: {e}')
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@games_bp.route('/api/game/<int:game_id>', methods=['GET'])
@login_required
def api_get_game(game_id):
    """
    API endpoint to get game details.

    Returns JSON with game details for editing.
    """
    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    # Get team names
    home_team_name = None
    away_team_name = None
    if game.home_ID:
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.scheduler_display_name
    if game.away_ID:
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.scheduler_display_name

    return jsonify({
        'success': True,
        'game': {
            'id': game.ID,
            'date': game.game_date.strftime('%Y-%m-%d') if game.game_date else None,
            'time': game.game_date.strftime('%H:%M') if game.game_date else None,
            'field': game.field_name,
            'field_id': game.field_id,
            'league': game.league,
            'status': game.status,
            'game_type': game.game_type,
            'is_scrimmage': game.is_scrimmage,
            'no_time_limit': game.no_time_limit,
            'home_team_id': game.home_ID,
            'away_team_id': game.away_ID,
            'home_team_name': home_team_name,
            'away_team_name': away_team_name
        }
    })


@games_bp.route('/api/<int:year>/<int:is_spring>/add-event', methods=['POST'])
@login_required
def api_add_event(year, is_spring):
    """
    API endpoint for adding a new game/practice/scrimmage.

    Expects JSON body:
    {
        "event_type": str ('game', 'practice', 'scrimmage', 'division_practice'),
        "league": str,
        "game_date": str (YYYY-MM-DD),
        "game_time": str (HH:MM),
        "field_name": str,
        "home_team_id": int (optional),
        "away_team_id": int (optional, for games/scrimmages)
    }
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        event_type = data.get('event_type', 'game')
        league = data.get('league')
        game_date = data.get('game_date')
        game_time = data.get('game_time')
        field_name = data.get('field_name')
        home_team_id = data.get('home_team_id')
        away_team_id = data.get('away_team_id')

        if not league or not game_date or not game_time or not field_name:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Build datetime
        game_datetime = f'{game_date}T{game_time}:00'

        # Check if there's an active proposal
        from app.models.schedule_proposal import ScheduleProposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)

        if proposal:
            # Add to proposal
            # Get team names if provided
            home_team_name = None
            away_team_name = None
            if home_team_id:
                home_team = TeamSeason.query.get(int(home_team_id))
                if home_team:
                    home_team_name = home_team.scheduler_display_name
            if away_team_id:
                away_team = TeamSeason.query.get(int(away_team_id))
                if away_team:
                    away_team_name = away_team.scheduler_display_name

            game_data = {
                'game_type': 'practice' if event_type in ['practice', 'division_practice'] else 'regular',
                'game_date': game_datetime,
                'field_name': field_name,
                'league': league,
                'home_team_id': int(home_team_id) if home_team_id else None,
                'home_team_name': home_team_name or 'TBD',
                'away_team_id': int(away_team_id) if away_team_id and event_type in ['game', 'scrimmage'] else None,
                'away_team_name': away_team_name,
                'is_scrimmage': event_type == 'scrimmage',
                'is_league_practice': event_type == 'division_practice'
            }

            new_id = proposal.add_game(game_data)
            logger.info(f'API: Added event to proposal - ID={new_id}, type={event_type}, league={league}')

            return jsonify({
                'success': True,
                'message': 'Event added to proposal',
                'event_id': new_id,
                'is_proposal': True
            })
        else:
            # No proposal - add directly to Game table
            game_dt = datetime.strptime(f'{game_date} {game_time}', '%Y-%m-%d %H:%M')

            # Look up field_id from field_name
            from app.models.field import Field
            field_obj = Field.query.filter_by(location_title=field_name, active=1).first()
            field_id = field_obj.ID if field_obj else None

            new_game = Game(
                active=1,
                year=year,
                is_spring=is_spring,
                league=league,
                game_type='practice' if event_type in ['practice', 'division_practice'] else 'regular',
                game_date=game_dt,
                field_id=field_id,
                home_ID=int(home_team_id) if home_team_id else None,
                away_ID=int(away_team_id) if away_team_id and event_type in ['game', 'scrimmage'] else None,
                is_scrimmage=1 if event_type == 'scrimmage' else 0,
                is_league_practice=event_type == 'division_practice',
                status='scheduled'
            )
            db.session.add(new_game)
            db.session.commit()

            logger.info(f'API: Added game directly - ID={new_game.ID}, type={event_type}, league={league}')

            return jsonify({
                'success': True,
                'message': 'Event added',
                'event_id': new_game.ID,
                'is_proposal': False
            })

    except Exception as e:
        logger.error(f'API: Error adding event: {e}')
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@games_bp.route('/api/<int:year>/<int:is_spring>/delete-event', methods=['POST'])
@login_required
def api_delete_event(year, is_spring):
    """
    API endpoint for deleting a game/practice.

    Expects JSON body:
    {
        "event_id": int or str,
        "is_proposed": bool (optional)
    }
    """
    if not current_user.can_edit_schedule():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        event_id = data.get('event_id')
        is_proposed = data.get('is_proposed', False)

        if event_id is None:
            return jsonify({'success': False, 'message': 'event_id is required'}), 400

        # Check if there's an active proposal
        from app.models.schedule_proposal import ScheduleProposal
        proposal = ScheduleProposal.get_for_season(year, is_spring)

        if proposal and is_proposed:
            # Delete from proposal
            try:
                event_id_int = int(event_id)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': 'Invalid event_id for proposal'}), 400

            deleted = proposal.delete_game(event_id_int)
            if deleted:
                logger.info(f'API: Deleted event from proposal - ID={event_id}')
                return jsonify({
                    'success': True,
                    'message': 'Event deleted from proposal'
                })
            else:
                return jsonify({'success': False, 'message': 'Event not found in proposal'}), 404
        else:
            # Delete from Game table (soft delete)
            try:
                event_id_int = int(event_id)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': 'Invalid event_id'}), 400

            game = Game.query.get(event_id_int)
            if not game:
                return jsonify({'success': False, 'message': 'Game not found'}), 404

            game.active = 0
            db.session.commit()

            logger.info(f'API: Soft-deleted game - ID={event_id}')

            return jsonify({
                'success': True,
                'message': 'Event deleted'
            })

    except Exception as e:
        logger.error(f'API: Error deleting event: {e}')
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@games_bp.route('/api/<int:year>/<int:is_spring>/event-options')
@login_required
def api_event_options(year, is_spring):
    """
    API endpoint to get options for the Add Event modal.

    Returns leagues, teams by league, fields, and time slots.
    """
    # Get leagues for this season
    from app.models.league_season import LeagueSeason
    league_configs = LeagueSeason.get_by_season(year, is_spring)
    leagues = [lc.league for lc in league_configs]

    # Get teams by league
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1,
        is_placeholder=0
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    teams_by_league = {}
    for team in teams:
        if team.league not in teams_by_league:
            teams_by_league[team.league] = []
        teams_by_league[team.league].append({
            'id': team.team_ID,
            'name': team.scheduler_display_name
        })

    # Get fields
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()
    field_list = [{'id': f.ID, 'name': f.location_title} for f in fields]

    # Standard time slots
    time_slots = []
    for hour in range(17, 21):  # 5 PM to 8 PM
        for minute in [0, 30]:
            time_slots.append(f'{hour:02d}:{minute:02d}')

    return jsonify({
        'success': True,
        'leagues': leagues,
        'teams_by_league': teams_by_league,
        'fields': field_list,
        'time_slots': time_slots
    })


# =============================================================================
# Regular Page Routes
# =============================================================================


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
                    # Import change tracking service
                    from app.services.game_changes import GameChangeService

                    # Capture old values before update
                    old_values = GameChangeService.capture_old_values(game)

                    # Parse date and time
                    game_date_str = request.form.get('game_date')
                    game_time_str = request.form.get('game_time')
                    if game_date_str and game_time_str:
                        game.game_date = datetime.strptime(
                            f'{game_date_str} {game_time_str}', '%Y-%m-%d %H:%M'
                        )
                    elif game_date_str:
                        game.game_date = datetime.strptime(game_date_str, '%Y-%m-%d')

                    # Update field - use field_id (FK)
                    field_value = request.form.get('field_id') or request.form.get('location')
                    if field_value:
                        # Check if it's a numeric ID or a field name
                        if field_value.isdigit():
                            game.field_id = int(field_value)
                        else:
                            # Look up field by name and set field_id
                            field = Field.query.filter_by(location_title=field_value, active=1).first()
                            game.field_id = field.ID if field else None
                    else:
                        game.field_id = None

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

                    # Log the change
                    change = GameChangeService.compare_and_log(
                        game, old_values, current_user.ID
                    )
                    if change:
                        GameChangeService.queue_notifications_for_change(change, game)

                    logger.info(f'Updated game {game_id}: {game.home_team.scheduler_display_name if game.home_team else "TBD"} vs {game.away_team.scheduler_display_name if game.away_team else "N/A"}')
                    flash('Game updated successfully.', 'success')

                elif action == 'delete_game':
                    # Import change tracking service
                    from app.services.game_changes import GameChangeService

                    # Log the deletion
                    GameChangeService.log_change(
                        game_id=game.ID,
                        user_id=current_user.ID,
                        change_type='delete',
                        changes_dict={'active': {'old': 1, 'new': 0}}
                    )

                    game.active = 0
                    db.session.commit()
                    logger.info(f'Deleted game {game_id}')
                    flash('Game deleted.', 'success')
                    anchor = None  # Don't scroll to deleted game

        # Handle create action (no game_id required)
        if action == 'create_game':
            # Get form values
            league = request.form.get('league')
            game_type = request.form.get('game_type', 'regular')
            game_date_str = request.form.get('game_date')
            game_time_str = request.form.get('game_time')
            field_value = request.form.get('field_id') or request.form.get('location')
            home_id = request.form.get('home_id')
            away_id = request.form.get('away_id')
            is_scrimmage = 1 if request.form.get('is_scrimmage') else 0
            no_time_limit = 1 if request.form.get('no_time_limit') else 0

            if not league:
                flash('League is required.', 'error')
            elif not game_date_str or not game_time_str:
                flash('Date and time are required.', 'error')
            elif not field_value:
                flash('Field is required.', 'error')
            else:
                # Parse date and time
                game_date = datetime.strptime(
                    f'{game_date_str} {game_time_str}', '%Y-%m-%d %H:%M'
                )

                # Resolve field_id
                field_id = None
                if field_value.isdigit():
                    field_id = int(field_value)
                else:
                    field = Field.query.filter_by(location_title=field_value, active=1).first()
                    if field:
                        field_id = field.ID

                # Create the game
                new_game = Game(
                    active=1,
                    year=year,
                    is_spring=is_spring,
                    league=league,
                    game_type=game_type,
                    game_date=game_date,
                    field_id=field_id,
                    home_ID=int(home_id) if home_id else None,
                    away_ID=int(away_id) if away_id and game_type != 'practice' else None,
                    is_scrimmage=is_scrimmage,
                    no_time_limit=no_time_limit,
                    status='scheduled'
                )
                db.session.add(new_game)
                db.session.commit()

                logger.info(f'Created new game: {new_game.ID} - {league} at field {field_id} on {game_date}')
                flash(f'Game created successfully.', 'success')
                anchor = f'game-{new_game.ID}'

        # Check if we should return to a different page (e.g., calendar)
        return_to = request.form.get('return_to')
        logger.info(f'POST action={action}, return_to={return_to}')
        if return_to and return_to.startswith('/'):
            # Validate it's a relative URL (same origin) for security
            redirect_url = return_to
        else:
            redirect_url = url_for('games.manage', year=year, is_spring=is_spring)
        if anchor:
            # Only add anchor if URL doesn't already have a fragment
            if '#' not in redirect_url:
                redirect_url += f'#{anchor}'
        logger.info(f'Redirecting to: {redirect_url}')
        return redirect(redirect_url)

    # GET - show management page
    # Get filter parameters
    league = request.args.get('league')
    game_mode = request.args.get('game_mode', 'all')
    field_filter = request.args.get('field')
    date_filter = request.args.get('date')
    team_filter = request.args.get('team', type=int)
    view_mode = request.args.get('view', 'cards')  # 'cards' or 'table'

    # Build query - always exclude games without game_date
    query = Game.query.filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        Game.game_date.isnot(None)
    )

    if league:
        query = query.filter(Game.league == league)

    if game_mode == 'games':
        query = query.filter(Game.away_ID.isnot(None))
    elif game_mode == 'practices':
        query = query.filter(Game.away_ID.is_(None))

    # Filter by field
    if field_filter:
        field_obj = Field.query.filter_by(location_title=field_filter, active=1).first()
        if field_obj:
            query = query.filter(Game.field_id == field_obj.ID)

    # Filter by date
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Game.game_date) == filter_date)
        except ValueError:
            pass

    # Filter by team (home or away)
    if team_filter:
        query = query.filter(
            db.or_(
                Game.home_ID == team_filter,
                Game.away_ID == team_filter
            )
        )

    games = query.order_by(Game.game_date, Game.field_id).all()

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

    # Get unique field names from games for the filter dropdown
    field_ids = db.session.query(Game.field_id).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.field_id.isnot(None),
        Game.game_date.isnot(None)
    ).distinct().all()
    field_ids = [f[0] for f in field_ids if f[0]]
    field_names = sorted([f.location_title for f in Field.query.filter(Field.ID.in_(field_ids)).all()])

    return render_template(
        'games/manage.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        games=games,
        teams=teams,
        fields=fields,
        leagues=leagues,
        field_names=field_names,
        current_filters={
            'league': league,
            'game_mode': game_mode,
            'field': field_filter,
            'date': date_filter,
            'team': team_filter,
            'view': view_mode
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

        # Also include manually-created league practices from the database
        league_practices = Game.query.filter(
            Game.active == 1,
            Game.year == year,
            Game.is_spring == is_spring,
            Game.is_league_practice == True
        ).all()

        # Build field lookup for resolving location IDs to names
        all_fields = Field.query.filter_by(active=1).all()
        field_lookup = {str(f.ID): f.location_title for f in all_fields}
        field_lookup.update({f.location_title: f.location_title for f in all_fields})

        for lp in league_practices:
            if lp.game_date:
                lp_date = lp.game_date.date() if hasattr(lp.game_date, 'date') else lp.game_date
                if lp_date not in proposed_games_by_date:
                    proposed_games_by_date[lp_date] = []
                # Convert to proposal-style dict - use field_name property from Game model
                lp_dict = {
                    'id': f'lp_{lp.ID}',
                    'game_type': 'practice',
                    'league': lp.league,
                    'home_team_id': lp.home_ID,
                    'home_team_name': lp.home_team.scheduler_display_name if lp.home_team else 'Unknown',
                    'away_team_id': None,
                    'away_team_name': None,
                    'field_name': lp.field_name,  # Use Game.field_name property
                    'game_date': lp.game_date.isoformat() if lp.game_date else None,
                    'is_scrimmage': False,
                    'is_league_practice': True,
                    'no_time_limit': False
                }
                proposed_games_by_date[lp_date].append(lp_dict)

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
                field_name = g.get('field_name') or g.get('location') or ''
                # Resolve field_id from field_name if possible
                field_id = None
                if field_name:
                    field_obj = Field.query.filter_by(location_title=field_name, active=1).first()
                    if field_obj:
                        field_id = field_obj.ID
                game_obj = type('ProposedGame', (), {
                    'ID': g.get('id'),
                    'game_date': datetime.fromisoformat(g['game_date']) if g.get('game_date') else None,
                    'location': field_name,
                    'field_name': field_name,  # Add field_name for template compatibility
                    'field_id': field_id,  # Add field_id for edit modal compatibility
                    'league': g.get('league'),
                    'status': 'scheduled',
                    'game_type': g.get('game_type', 'regular'),
                    'is_scrimmage': g.get('is_scrimmage', False),
                    'is_league_practice': g.get('is_league_practice', False),
                    'display_type': 'div-practice' if g.get('is_league_practice') else (g.get('game_type', 'regular') if not g.get('is_scrimmage') else 'scrimmage'),
                    'home_ID': g.get('home_team_id'),
                    'away_ID': g.get('away_team_id'),
                    'home_team': type('Team', (), {'scheduler_display_name': g.get('home_team_name', 'TBD')})() if g.get('home_team_id') else None,
                    'away_team': type('Team', (), {'scheduler_display_name': g.get('away_team_name', 'TBD')})() if g.get('away_team_id') else None,
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

            day_games = query.order_by(Game.game_date, Game.field_id).all()

        week_days.append({
            'date': day_date,
            'is_today': day_date == today,
            'games': day_games
        })

    # Calculate prev/next/current week
    prev_week = (week_start - timedelta(days=7)).strftime('%G-%V')
    next_week = (week_start + timedelta(days=7)).strftime('%G-%V')
    current_week = week_start.strftime('%G-%V')

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
        current_week=current_week,
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
                        field_name = g.get('field_name') or g.get('location') or ''
                        game_obj = type('ProposedGame', (), {
                            'ID': g.get('id'),
                            'game_date': dt.fromisoformat(g['game_date']) if g.get('game_date') else None,
                            'location': field_name,
                            'field_name': field_name,  # Add field_name for template compatibility
                            'league': g.get('league'),
                            'status': 'scheduled',
                            'game_type': g.get('game_type', 'regular'),
                            'is_scrimmage': g.get('is_scrimmage', False),
                            'is_league_practice': g.get('is_league_practice', False),
                            'display_type': 'div-practice' if g.get('is_league_practice') else (g.get('game_type', 'regular') if not g.get('is_scrimmage') else 'scrimmage'),
                            'home_ID': g.get('home_team_id'),
                            'away_ID': g.get('away_team_id'),
                            'home_team': type('Team', (), {'scheduler_display_name': g.get('home_team_name', 'TBD')})() if g.get('home_team_id') else None,
                            'away_team': type('Team', (), {'scheduler_display_name': g.get('away_team_name', 'TBD')})() if g.get('away_team_id') else None,
                            'no_time_limit': g.get('no_time_limit', False),
                            'is_proposed': True
                        })()
                        games.append(game_obj)
                except (ValueError, TypeError):
                    pass

        # Also include manually-created league practices from the database
        league_practices = Game.query.filter(
            Game.active == 1,
            Game.year == year,
            Game.is_spring == is_spring,
            Game.is_league_practice == True,
            db.func.date(Game.game_date) == view_date
        ).all()

        # Build field lookup for resolving location IDs to names
        # Field is already imported at module level - do not re-import locally
        # as this causes UnboundLocalError when has_proposal is False (see error #18)
        all_fields_dv = Field.query.filter_by(active=1).all()
        field_lookup_dv = {str(f.ID): f.location_title for f in all_fields_dv}
        field_lookup_dv.update({f.location_title: f.location_title for f in all_fields_dv})

        for lp in league_practices:
            # Use field_name property from Game model (handles FK and fallback)
            field_name = lp.field_name or ''
            game_obj = type('ProposedGame', (), {
                'ID': f'lp_{lp.ID}',
                'game_date': lp.game_date,
                'location': field_name,
                'field_name': field_name,  # Add field_name for template compatibility
                'league': lp.league,
                'status': 'scheduled',
                'game_type': 'practice',
                'is_scrimmage': False,
                'is_league_practice': True,
                'display_type': 'div-practice',
                'home_ID': lp.home_ID,
                'away_ID': None,
                'home_team': lp.home_team,
                'away_team': None,
                'no_time_limit': False,
                'is_proposed': False  # These are saved in DB
            })()
            games.append(game_obj)

        # Sort by game_date
        games.sort(key=lambda x: x.game_date if x.game_date else dt.min)
    else:
        # Get games from database for this day
        games = Game.query.filter(
            Game.active == 1,
            Game.year == year,
            Game.is_spring == is_spring,
            db.func.date(Game.game_date) == view_date
        ).order_by(Game.game_date, Game.field_id).all()

    # Get all fields that have games on this day
    fields_with_games = set()
    game_hours = set()
    for game in games:
        field_name = game.field_name
        if field_name:
            fields_with_games.add(field_name)
        if game.game_date:
            game_hours.add(game.game_date.hour)

    # Get all fields for display (prioritize those with games)
    all_fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()
    field_lookup = {f.location_title: f for f in all_fields}
    field_id_lookup = {f.ID: f for f in all_fields}

    # Get field slots (recurring allocations) for this day of week
    day_of_week = view_date.weekday()  # 0=Monday, 6=Sunday
    from app.models.field_slot import FieldSlot
    from app.models.field_blackout import FieldBlackout
    from app.models.field_allocation_specific import FieldAllocationSpecific

    recurring_allocations = FieldSlot.query.filter_by(
        year=year,
        is_spring=is_spring,
        day_of_week=day_of_week,
        active=1
    ).all()

    # Get specific-date allocations for this exact date
    specific_allocations = FieldAllocationSpecific.get_by_date(year, is_spring, view_date)

    # Get blackouts for this date (to show fields as blacked out, not hide them)
    blackouts_today = FieldBlackout.query.filter_by(
        blackout_date=view_date, active=1
    ).all()
    blacked_out_fields = {}  # field_name -> reason
    for bo in blackouts_today:
        field = field_id_lookup.get(bo.field_ID)
        if field:
            blacked_out_fields[field.location_title] = bo.reason or 'Unavailable'

    # Track fields with allocations and their time slots
    fields_with_allocations = set()
    fields_with_owned_allocations = set()  # Only SDLL-owned fields
    allocation_times = set()
    allocation_info = {}  # (field_name, time_key) -> {'is_owned': bool, 'slot': obj, 'is_specific': bool}

    # Process recurring allocations first
    for alloc in recurring_allocations:
        field = field_id_lookup.get(alloc.field_ID)
        if field:
            fields_with_allocations.add(field.location_title)
            if alloc.is_owned == 1:
                fields_with_owned_allocations.add(field.location_title)
            start_hour = alloc.start_time.hour
            end_hour = alloc.end_time.hour
            for h in range(start_hour, end_hour + 1):
                for m in [0, 30]:
                    time_key = f'{h:02d}:{m:02d}'
                    allocation_times.add(time_key)
                    allocation_info[(field.location_title, time_key)] = {
                        'is_owned': alloc.is_owned == 1,
                        'slot': alloc,
                        'is_specific': False
                    }

    # Process specific-date allocations (these override recurring for specific dates)
    for alloc in specific_allocations:
        field = field_id_lookup.get(alloc.field_ID)
        if field:
            fields_with_allocations.add(field.location_title)
            if alloc.is_owned == 1:
                fields_with_owned_allocations.add(field.location_title)
            start_hour = alloc.start_time.hour
            end_hour = alloc.end_time.hour
            for h in range(start_hour, end_hour + 1):
                for m in [0, 30]:
                    time_key = f'{h:02d}:{m:02d}'
                    allocation_times.add(time_key)
                    # Specific allocations override recurring
                    allocation_info[(field.location_title, time_key)] = {
                        'is_owned': alloc.is_owned == 1,
                        'slot': alloc,
                        'is_specific': True
                    }

    # Build display_fields from SDLL-owned fields only
    # Include fields that have games OR have SDLL-owned allocations
    fields_to_show = (fields_with_games | fields_with_owned_allocations)

    if fields_to_show:
        display_fields = []
        for field_name in sorted(fields_to_show):
            if field_name:
                # Try to find matching field in DB
                if field_name in field_lookup:
                    display_fields.append(field_lookup[field_name])
                else:
                    # Create a placeholder field object for fields not in DB
                    placeholder = type('Field', (), {'ID': None, 'location_title': field_name})()
                    display_fields.append(placeholder)
    else:
        # Show only SDLL-owned fields from all fields
        display_fields = [f for f in all_fields if f.location_title in fields_with_owned_allocations][:8]

    # Define time slots based on actual game times AND allocation times (dynamic range)
    all_time_keys = set()
    if game_hours:
        min_hour = min(game_hours)
        max_hour = max(game_hours) + 1
        for hour in range(min_hour, max_hour + 1):
            for minute in [0, 30]:
                all_time_keys.add(f'{hour:02d}:{minute:02d}')

    # Also include times from allocations
    all_time_keys.update(allocation_times)

    if all_time_keys:
        time_slots = sorted(all_time_keys)
    else:
        # Default to evening if no games or allocations
        time_slots = []
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
        field_name = game.field_name
        if game.game_date and field_name:
            time_key = game.game_date.strftime('%H:%M')
            # Round to nearest 30-minute slot
            hour = game.game_date.hour
            minute = 0 if game.game_date.minute < 30 else 30
            time_key = f'{hour:02d}:{minute:02d}'

            if time_key in grid and field_name in grid[time_key]:
                grid[time_key][field_name].append(game)

    # Calculate prev/next day links
    prev_date = view_date - timedelta(days=1)
    next_date = view_date + timedelta(days=1)

    # Get teams for edit modal
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    # Get leagues for create modal
    leagues = db.session.query(Game.league).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league.isnot(None)
    ).distinct().order_by(Game.league).all()
    leagues = [l[0] for l in leagues]

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
        teams=teams,
        allocation_info=allocation_info,
        leagues=leagues,
        fields_with_games=fields_with_games,
        blacked_out_fields=blacked_out_fields
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

        # Import change tracking service
        from app.services.game_changes import GameChangeService

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
                    old_status = game.status
                    game.status = 'postponed'
                    count += 1

                db.session.commit()

                # Log changes for each game
                for game in games:
                    change = GameChangeService.log_change(
                        game_id=game.ID,
                        user_id=current_user.ID,
                        change_type='update',
                        changes_dict={'status': {'old': 'scheduled', 'new': 'postponed'}},
                        reason=f'Rainout on {rainout_date.strftime("%B %d, %Y")}'
                    )
                    GameChangeService.queue_notifications_for_change(change, game)

                logger.info(f'Postponed {count} games for rainout on {rainout_date}')
                flash(f'Postponed {count} games for {rainout_date.strftime("%B %d, %Y")}', 'success')

        elif action == 'reschedule_game':
            game_id = int(request.form.get('game_id'))
            new_date_str = request.form.get('new_date')
            new_time_str = request.form.get('new_time')
            new_field = request.form.get('new_field')

            game = Game.query.get(game_id)
            if game and new_date_str:
                # Capture old values
                old_values = GameChangeService.capture_old_values(game)

                if new_time_str:
                    game.game_date = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
                else:
                    # Keep original time
                    original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                    new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    game.game_date = datetime.combine(new_date, original_time)

                # Update field if specified
                if new_field:
                    # Look up field_id from name
                    field_obj = Field.query.filter_by(location_title=new_field, active=1).first()
                    game.field_id = field_obj.ID if field_obj else None

                game.status = 'scheduled'
                db.session.commit()

                # Log the change
                change = GameChangeService.compare_and_log(
                    game, old_values, current_user.ID,
                    reason='Rescheduled from rainout'
                )
                if change:
                    GameChangeService.queue_notifications_for_change(change, game)

                logger.info(f'Rescheduled game {game_id} to {game.game_date} at {game.field_name}')
                flash(f'Rescheduled game to {game.game_date.strftime("%B %d at %I:%M %p")}', 'success')

        elif action == 'swap_with_practice':
            game_id = int(request.form.get('game_id'))
            practice_date_str = request.form.get('practice_date')

            game = Game.query.get(game_id)
            if game and practice_date_str:
                # Capture old values
                old_values = GameChangeService.capture_old_values(game)

                practice_date = datetime.strptime(practice_date_str, '%Y-%m-%d').date()
                original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                game.game_date = datetime.combine(practice_date, original_time)
                game.status = 'scheduled'
                db.session.commit()

                # Log the change
                change = GameChangeService.compare_and_log(
                    game, old_values, current_user.ID,
                    reason='Swapped with practice date'
                )
                if change:
                    GameChangeService.queue_notifications_for_change(change, game)

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
                games_to_log = []
                for game_id in game_ids:
                    game = Game.query.get(int(game_id))
                    if game:
                        # Capture old values
                        old_values = GameChangeService.capture_old_values(game)

                        # Update date/time
                        if new_time_str:
                            game.game_date = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
                        else:
                            original_time = game.game_date.time() if game.game_date else datetime.strptime('17:30', '%H:%M').time()
                            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                            game.game_date = datetime.combine(new_date, original_time)

                        # Update field if specified
                        if new_field:
                            field_obj = Field.query.filter_by(location_title=new_field, active=1).first()
                            game.field_id = field_obj.ID if field_obj else None

                        game.status = 'scheduled'
                        count += 1
                        games_to_log.append((game, old_values))

                db.session.commit()

                # Log changes for all games
                for game, old_values in games_to_log:
                    change = GameChangeService.compare_and_log(
                        game, old_values, current_user.ID,
                        reason='Bulk reschedule from rainout'
                    )
                    if change:
                        GameChangeService.queue_notifications_for_change(change, game)

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
                field_id=field.ID,
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
        key = (p.game_date.date() if p.game_date else None, p.league, p.field_name)
        if key not in practice_groups:
            practice_groups[key] = {
                'date': p.game_date,
                'league': p.league,
                'location': p.field_name,  # Use field_name property (FK preferred)
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
