"""Coach routes - post-game reports and coach-specific features."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.coach import CoachSeason, CoachUser
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.models.post_game_report import PostGameReport
from app.models.player import PlayerSeason
from app.models.pitching_stats import PitchingStats
from app.models.gc_screenshot_session import GCScreenshotSession
from app.services import post_game_service
from app.services.pitch_count_service import PitchCountService
from app.services.gc_screenshot_service import GCScreenshotService


coach_bp = Blueprint('coach', __name__)


def _parse_int(value):
    """Parse integer from form value, returning None if invalid."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_innings(value):
    """Parse innings pitched from form value (e.g., '2.1' = 2 and 1/3).

    Returns None if invalid.
    """
    if not value or not value.strip():
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


@coach_bp.route('/postgame/<token>')
def postgame_entry(token):
    """Entry point from email link - redirects to form after login.

    The token parameter is kept for backwards compatibility with old email links,
    but is no longer validated. Authorization is handled by the form itself via
    can_user_submit() which verifies the user is a coach for the team.

    Query params:
        g: game_id
        t: team_id
    """
    game_id = request.args.get('g', type=int)
    team_id = request.args.get('t', type=int)

    if not game_id or not team_id:
        flash('Invalid link. Please use the link from your email.', 'error')
        return redirect(url_for('main.dashboard'))

    # Verify game and team exist
    game = Game.query.get(game_id)
    team = TeamSeason.query.get(team_id)

    if not game or not team:
        flash('Game or team not found.', 'error')
        return redirect(url_for('main.dashboard'))

    if team_id not in (game.home_ID, game.away_ID):
        flash('Team is not part of this game.', 'error')
        return redirect(url_for('main.dashboard'))

    # If not logged in, redirect to login with next URL
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))

    # Check if this is a "not played" link (use 'skip' to avoid &not HTML entity issue)
    skip = request.args.get('skip')
    if skip == '1':
        return redirect(url_for('coach.postgame_not_played', game_id=game_id, team_id=team_id))

    # Redirect to the actual form (which does authorization via can_user_submit)
    return redirect(url_for('coach.postgame_form', game_id=game_id, team_id=team_id))


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>', methods=['GET', 'POST'])
@login_required
def postgame_form(game_id, team_id):
    """Display and handle post-game report form."""
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        flash(f'Access denied: {error}', 'error')
        return redirect(url_for('main.dashboard'))

    # Load game and team with relationships
    game = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).get(game_id)

    if not game:
        flash('Game not found.', 'error')
        return redirect(url_for('main.dashboard'))

    team = TeamSeason.query.get(team_id)
    if not team:
        flash('Team not found.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get opponent
    opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)

    # Get existing report if any
    report = PostGameReport.query.filter_by(game_id=game_id, team_id=team_id).first()

    # Check if edit window expired
    if report and report.edit_window_expired:
        flash('The edit window for this report has expired (24 hours after submission).', 'warning')
        return redirect(url_for('coach.postgame_success', game_id=game_id, team_id=team_id))

    # Check if league is kid-pitch and baseball (softball doesn't have pitch count rules)
    league = League.get_by_name(game.league)
    is_kid_pitch = league and league.pitch_type == 'kid_pitch' if league else False
    is_baseball = league and league.is_baseball if league else True

    # Check if pitching stats should be shown based on league setting
    show_pitching = league and league.captures_pitching_data if league else False

    # Get team roster for pitching stats if enabled
    roster = []
    roster_json = []  # JSON-serializable version for JavaScript
    existing_pitching_stats = {}
    if show_pitching:
        roster = PlayerSeason.query.filter_by(team_id=team_id).options(
            joinedload(PlayerSeason.player)
        ).all()
        # Sort by player name
        roster.sort(key=lambda ps: ps.player.full_name if ps.player else '')

        # Build JSON-serializable roster for screenshot tab JavaScript
        roster_json = GCScreenshotService.get_roster_for_prompt(team_id)

        # Get existing pitching stats for this report if it exists
        if report:
            for ps in PitchingStats.get_for_report(report.id):
                existing_pitching_stats[ps.player_id] = ps

    # Check if SDLL provided an umpire for this game
    # SDLL didn't provide if: umpire_override is NULL, umpire_was_unassigned=1, or umpire_count_override=0
    sdll_provided_umpire = (
        game.umpire_override is not None and
        game.umpire_was_unassigned != 1 and
        game.umpire_count_override != 0
    )

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'not_played':
            # Redirect to not-played form
            return redirect(url_for('coach.postgame_not_played', game_id=game_id, team_id=team_id))

        elif action == 'submit':
            # Validate and submit directly (no review step)
            errors = []

            our_score = request.form.get('our_score', '').strip()
            opponent_score = request.form.get('opponent_score', '').strip()
            innings_batted = request.form.get('innings_batted', '').strip()
            innings_fielded = request.form.get('innings_fielded', '').strip()
            umpire_rating = request.form.get('umpire_rating', '').strip()
            umpire_name = request.form.get('umpire_name', '').strip()
            umpire_comments = request.form.get('umpire_comments', '').strip()

            # Validate required fields
            if not our_score:
                errors.append('Your team score is required')
            elif not our_score.isdigit():
                errors.append('Your team score must be a number')

            if not opponent_score:
                errors.append('Opponent score is required')
            elif not opponent_score.isdigit():
                errors.append('Opponent score must be a number')

            if not innings_batted:
                errors.append('Innings batted is required')

            if not innings_fielded:
                errors.append('Innings fielded is required')

            # Umpire rating is only required if SDLL provided the umpire
            if sdll_provided_umpire:
                if not umpire_rating:
                    errors.append('Umpire rating is required')
                elif umpire_rating not in PostGameReport.RATINGS:
                    errors.append('Invalid umpire rating')
            elif umpire_rating and umpire_rating not in PostGameReport.RATINGS:
                # If they provided a rating anyway, validate it
                errors.append('Invalid umpire rating')

            if errors:
                for err in errors:
                    flash(err, 'error')
                return render_template('coach/postgame_form.html',
                                       game=game,
                                       team=team,
                                       opponent=opponent,
                                       report=report,
                                       is_kid_pitch=is_kid_pitch,
                                       is_baseball=is_baseball,
                                       show_pitching=show_pitching,
                                       roster=roster,
                                       roster_json=roster_json,
                                       existing_pitching_stats=existing_pitching_stats,
                                       sdll_provided_umpire=sdll_provided_umpire,
                                       ratings=PostGameReport.RATINGS,
                                       rating_labels=PostGameReport.RATING_LABELS,
                                       form_data=request.form)

            # Submit directly
            data = {
                'our_score': int(our_score),
                'opponent_score': int(opponent_score),
                'innings_batted': int(innings_batted),
                'innings_fielded': int(innings_fielded),
                'umpire_rating': umpire_rating,
                'umpire_name': umpire_name or None,
                'umpire_comments': umpire_comments
            }

            success, report_obj, error = post_game_service.submit_report(game_id, team_id, current_user.ID, data)

            if success:
                # Save pitching stats if enabled
                if show_pitching and report_obj:
                    pitch_data = []
                    for ps in roster:
                        player_id = ps.player_id
                        pitch_count_str = request.form.get(f'pitch_count_{player_id}', '').strip()
                        if pitch_count_str and pitch_count_str.isdigit() and int(pitch_count_str) > 0:
                            pitch_data.append({
                                'player_id': player_id,
                                'pitch_count': int(pitch_count_str),
                                'innings_pitched': _parse_innings(request.form.get(f'innings_{player_id}', '')),
                                'walks': _parse_int(request.form.get(f'walks_{player_id}', '')),
                                'batters_faced': _parse_int(request.form.get(f'batters_faced_{player_id}', '')),
                            })
                    if pitch_data:
                        PitchCountService.save_pitching_stats(report_obj.id, pitch_data)

                flash('Post-game report submitted successfully.', 'success')
                return redirect(url_for('coach.postgame_success', game_id=game_id, team_id=team_id))
            else:
                flash(f'Failed to submit report: {error}', 'error')
                return render_template('coach/postgame_form.html',
                                       game=game,
                                       team=team,
                                       opponent=opponent,
                                       report=report,
                                       is_kid_pitch=is_kid_pitch,
                                       is_baseball=is_baseball,
                                       show_pitching=show_pitching,
                                       roster=roster,
                                       roster_json=roster_json,
                                       existing_pitching_stats=existing_pitching_stats,
                                       sdll_provided_umpire=sdll_provided_umpire,
                                       ratings=PostGameReport.RATINGS,
                                       rating_labels=PostGameReport.RATING_LABELS,
                                       form_data=request.form)

    # GET request - show form
    # Get response time info for screenshot timeout detection
    response_time_info = GCScreenshotService.get_response_time_info()

    return render_template('coach/postgame_form.html',
                           game=game,
                           team=team,
                           opponent=opponent,
                           report=report,
                           is_kid_pitch=is_kid_pitch,
                           is_baseball=is_baseball,
                           show_pitching=show_pitching,
                           roster=roster,
                           roster_json=roster_json,
                           existing_pitching_stats=existing_pitching_stats,
                           sdll_provided_umpire=sdll_provided_umpire,
                           ratings=PostGameReport.RATINGS,
                           rating_labels=PostGameReport.RATING_LABELS,
                           response_time_info=response_time_info,
                           form_data={})


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/confirm', methods=['POST'])
@login_required
def postgame_confirm(game_id, team_id):
    """Final submission of post-game report."""
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        flash(f'Access denied: {error}', 'error')
        return redirect(url_for('main.dashboard'))

    # Get form data
    data = {
        'our_score': int(request.form.get('our_score', 0)),
        'opponent_score': int(request.form.get('opponent_score', 0)),
        'innings_batted': int(request.form.get('innings_batted', 0)),
        'innings_fielded': int(request.form.get('innings_fielded', 0)),
        'umpire_name': request.form.get('umpire_name', '').strip(),
        'umpire_rating': request.form.get('umpire_rating', '').strip(),
        'umpire_comments': request.form.get('umpire_comments', '').strip()
    }

    # Submit report
    success, report, error = post_game_service.submit_report(game_id, team_id, current_user.ID, data)

    if success:
        flash('Post-game report submitted successfully.', 'success')
        return redirect(url_for('coach.postgame_success', game_id=game_id, team_id=team_id))
    else:
        flash(f'Failed to submit report: {error}', 'error')
        return redirect(url_for('coach.postgame_form', game_id=game_id, team_id=team_id))


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/not-played', methods=['GET', 'POST'])
@login_required
def postgame_not_played(game_id, team_id):
    """Mark game as not played."""
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        flash(f'Access denied: {error}', 'error')
        return redirect(url_for('main.dashboard'))

    # Load game and team
    game = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).get(game_id)

    if not game:
        flash('Game not found.', 'error')
        return redirect(url_for('main.dashboard'))

    team = TeamSeason.query.get(team_id)
    opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)

    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        notes = request.form.get('notes', '').strip()

        if not reason:
            flash('Please select a reason.', 'error')
            return render_template('coach/postgame_not_played.html',
                                   game=game,
                                   team=team,
                                   opponent=opponent,
                                   reasons=PostGameReport.NOT_PLAYED_REASONS,
                                   reason_labels=PostGameReport.REASON_LABELS)

        if reason not in PostGameReport.NOT_PLAYED_REASONS:
            flash('Invalid reason selected.', 'error')
            return render_template('coach/postgame_not_played.html',
                                   game=game,
                                   team=team,
                                   opponent=opponent,
                                   reasons=PostGameReport.NOT_PLAYED_REASONS,
                                   reason_labels=PostGameReport.REASON_LABELS)

        success, report, error = post_game_service.mark_not_played(
            game_id, team_id, current_user.ID, reason, notes
        )

        if success:
            flash('Game marked as not played.', 'success')
            return redirect(url_for('coach.postgame_success', game_id=game_id, team_id=team_id))
        else:
            flash(f'Failed to mark game: {error}', 'error')

    return render_template('coach/postgame_not_played.html',
                           game=game,
                           team=team,
                           opponent=opponent,
                           reasons=PostGameReport.NOT_PLAYED_REASONS,
                           reason_labels=PostGameReport.REASON_LABELS)


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/success')
@login_required
def postgame_success(game_id, team_id):
    """Show success page after report submission."""
    game = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).get(game_id)

    team = TeamSeason.query.get(team_id)
    report = PostGameReport.query.filter_by(game_id=game_id, team_id=team_id).first()

    opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)

    return render_template('coach/postgame_success.html',
                           game=game,
                           team=team,
                           opponent=opponent,
                           report=report)


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/edit')
@login_required
def postgame_edit(game_id, team_id):
    """Edit a submitted report within the 24-hour window."""
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        flash(f'Access denied: {error}', 'error')
        return redirect(url_for('main.dashboard'))

    report = PostGameReport.query.filter_by(game_id=game_id, team_id=team_id).first()

    if not report:
        flash('No report found to edit.', 'error')
        return redirect(url_for('coach.postgame_form', game_id=game_id, team_id=team_id))

    if report.edit_window_expired:
        flash('The edit window for this report has expired (24 hours after submission).', 'warning')
        return redirect(url_for('coach.postgame_success', game_id=game_id, team_id=team_id))

    # Redirect to the form - it will show the existing data for editing
    return redirect(url_for('coach.postgame_form', game_id=game_id, team_id=team_id))


@coach_bp.route('/my-games')
@login_required
def my_games():
    """Show games pending post-game report submission for current user."""
    from app.models.org_season import OrgSeason

    # Get current season
    current_season = OrgSeason.get_current_season()
    year = current_season.year if current_season else None
    is_spring = current_season.is_spring if current_season else None

    # Find teams this user coaches
    coach_user = CoachUser.get_by_user(current_user.ID)

    if not coach_user:
        flash('You are not registered as a coach.', 'info')
        return render_template('coach/my_games.html',
                               pending_games=[],
                               submitted_games=[],
                               teams=[])

    # Get coach's team assignments
    assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()
    team_ids = [a.team_id for a in assignments]

    if not team_ids:
        return render_template('coach/my_games.html',
                               pending_games=[],
                               submitted_games=[],
                               teams=[])

    teams = TeamSeason.query.filter(TeamSeason.team_ID.in_(team_ids)).all()

    # Get completed games for these teams
    completed_games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.active == 1,
        Game.game_date < db.func.now(),
        Game.game_type.in_(['regular', 'playoff']),
        db.or_(
            Game.home_ID.in_(team_ids),
            Game.away_ID.in_(team_ids)
        )
    )

    if year is not None:
        completed_games = completed_games.filter(Game.year == year)
    if is_spring is not None:
        completed_games = completed_games.filter(Game.is_spring == is_spring)

    completed_games = completed_games.order_by(Game.game_date.desc()).all()

    # Categorize into pending and submitted
    pending_games = []
    submitted_games = []

    for game in completed_games:
        # Determine which team the coach is on
        coach_team_id = None
        for tid in team_ids:
            if tid == game.home_ID or tid == game.away_ID:
                coach_team_id = tid
                break

        if not coach_team_id:
            continue

        report = PostGameReport.query.filter_by(
            game_id=game.ID,
            team_id=coach_team_id
        ).first()

        game_info = {
            'game': game,
            'team_id': coach_team_id,
            'report': report
        }

        if report and report.status in (PostGameReport.STATUS_SUBMITTED, PostGameReport.STATUS_NOT_PLAYED):
            submitted_games.append(game_info)
        else:
            pending_games.append(game_info)

    return render_template('coach/my_games.html',
                           pending_games=pending_games,
                           submitted_games=submitted_games,
                           teams=teams)


@coach_bp.route('/pitch-counts')
@login_required
def pitch_counts():
    """Show pitch count summary for coach's team."""
    from app.models.org_season import OrgSeason

    # Get current season
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'info')
        return redirect(url_for('main.dashboard'))

    year = current_season.year
    is_spring = current_season.is_spring

    # Find teams this user coaches
    coach_user = CoachUser.get_by_user(current_user.ID)
    if not coach_user:
        flash('You are not registered as a coach.', 'info')
        return redirect(url_for('main.dashboard'))

    # Get coach's team assignments
    assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()
    team_ids = [a.team_id for a in assignments]

    if not team_ids:
        flash('You are not assigned to any teams.', 'info')
        return redirect(url_for('main.dashboard'))

    # Get teams with leagues that have pitching tracking enabled
    teams = TeamSeason.query.filter(TeamSeason.team_ID.in_(team_ids)).all()

    # Filter to teams in leagues with pitching stats enabled
    teams_with_pitching = []
    for team in teams:
        league = League.get_by_name(team.league)
        if league and league.captures_pitching_data:
            pitching_summary = PitchCountService.get_team_pitching_summary(
                team.team_ID, year, is_spring
            )
            teams_with_pitching.append({
                'team': team,
                'league': league,
                'pitching_summary': pitching_summary
            })

    if not teams_with_pitching:
        flash('None of your teams have pitch count tracking enabled.', 'info')
        return redirect(url_for('coach.my_games'))

    return render_template('coach/pitch_counts.html',
                           teams_with_pitching=teams_with_pitching,
                           year=year,
                           is_spring=is_spring,
                           season_name=f'{"Spring" if is_spring else "Fall"} {year}')


# =============================================================================
# GameChanger Screenshot Routes (BETA)
# =============================================================================

@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/screenshot', methods=['POST'])
@login_required
def postgame_screenshot_upload(game_id, team_id):
    """Upload and parse GameChanger screenshot.

    Returns JSON:
    - success: {session_id, session_uuid, data: {our_score, opponent_score, pitchers}, warnings}
    - error: {error, session_uuid, attempt, can_retry}
    """
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        return jsonify({'error': f'Access denied: {error}'}), 403

    # Check if API is configured
    if not GCScreenshotService.is_configured():
        return jsonify({'error': 'Screenshot parsing is not available. Please use manual entry.'}), 503

    # Get file from request
    if 'screenshot' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['screenshot']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Read file data
    file_data = file.read()
    content_type = file.content_type or 'image/png'
    filename = file.filename

    # Validate image
    is_valid, validation_error = GCScreenshotService.validate_image(file_data, content_type, filename)
    if not is_valid:
        return jsonify({'error': validation_error}), 400

    # Check for retry (existing session_uuid)
    session_uuid = request.form.get('session_uuid')

    # Check attempt limit
    if session_uuid:
        existing_attempts = GCScreenshotSession.query.filter_by(session_uuid=session_uuid).count()
        if existing_attempts >= 2:
            return jsonify({
                'error': 'Maximum attempts reached. Please use manual entry.',
                'can_retry': False
            }), 400

    # Create session
    session = GCScreenshotService.create_session(
        game_id=game_id,
        team_id=team_id,
        user_id=current_user.ID,
        session_uuid=session_uuid
    )

    # Store image
    GCScreenshotService.store_image(session, file_data, filename, content_type)

    # Get context for parsing
    team = TeamSeason.query.get(team_id)
    game = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).get(game_id)

    if not team or not game:
        return jsonify({'error': 'Game or team not found'}), 404

    team_name = team.computed_display_name
    opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)
    opponent_name = opponent.computed_display_name if opponent else 'Unknown'

    # Get roster
    roster = GCScreenshotService.get_roster_for_prompt(team_id)

    # Parse screenshot
    parsed_data, parse_error = GCScreenshotService.parse_screenshot(
        session, team_name, opponent_name, roster
    )

    if parse_error:
        can_retry = session.attempt_number < 2
        return jsonify({
            'error': parse_error,
            'session_uuid': session.session_uuid,
            'attempt': session.attempt_number,
            'can_retry': can_retry
        }), 422

    # Convert parsed data to response format
    pitchers_response = []
    for p in parsed_data.pitchers:
        pitchers_response.append({
            'name': p.name,
            'player_code': p.player_code,
            'pitches_thrown': p.pitches_thrown,
            'innings_pitched': p.innings_pitched,
            'strikes_thrown': p.strikes_thrown,
            'batters_faced': p.batters_faced,
            'runs_allowed': p.runs_allowed,
            'strikeouts': p.strikeouts,
            'walks': p.walks
        })

    return jsonify({
        'session_id': session.id,
        'session_uuid': session.session_uuid,
        'data': {
            'our_score': parsed_data.our_score,
            'opponent_score': parsed_data.opponent_score,
            'pitchers': pitchers_response
        },
        'confidence': parsed_data.confidence,
        'warnings': parsed_data.warnings,
        'roster': roster  # Include roster for player matching in UI
    })


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/screenshot/submit', methods=['POST'])
@login_required
def postgame_screenshot_submit(game_id, team_id):
    """Submit post-game report from parsed screenshot data.

    Compares to parsed_json to detect edits (was_edited flag).
    Creates PostGameReport + PitchingStats records.
    """
    # Check authorization
    can_submit, role, error = post_game_service.can_user_submit(current_user.ID, game_id, team_id)
    if not can_submit:
        return jsonify({'error': f'Access denied: {error}'}), 403

    # Get session ID
    session_id = request.form.get('session_id', type=int)
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400

    session = GCScreenshotSession.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Verify session belongs to this game/team/user
    if session.game_id != game_id or session.team_id != team_id:
        return jsonify({'error': 'Session mismatch'}), 403

    # Check if league supports pitching tracking
    league = League.get_by_name(Game.query.get(game_id).league)
    show_pitching = league and league.captures_pitching_data if league else False

    # Extract form data
    our_score = request.form.get('our_score', type=int)
    opponent_score = request.form.get('opponent_score', type=int)
    innings_batted = request.form.get('innings_batted', type=int)
    innings_fielded = request.form.get('innings_fielded', type=int)
    umpire_rating = request.form.get('umpire_rating', '').strip()
    umpire_name = request.form.get('umpire_name', '').strip()
    umpire_comments = request.form.get('umpire_comments', '').strip()

    # Validate required fields
    errors = []
    if our_score is None:
        errors.append('Your team score is required')
    if opponent_score is None:
        errors.append('Opponent score is required')
    if not innings_batted:
        errors.append('Innings batted is required')
    if not innings_fielded:
        errors.append('Innings fielded is required')

    if errors:
        return jsonify({'error': '; '.join(errors)}), 400

    # Build final data for diff computation
    final_pitchers = []
    roster = PlayerSeason.query.filter_by(team_id=team_id).options(
        joinedload(PlayerSeason.player)
    ).all()

    # Build player_code -> player lookup
    player_by_code = {}
    for ps in roster:
        if ps.player and ps.player.player_code:
            player_by_code[ps.player.player_code] = ps.player

    pitch_data = []

    # Process pitch data sent by player_code (from screenshot form)
    for key in request.form.keys():
        if key.startswith('pitch_code_'):
            player_code = key.replace('pitch_code_', '')
            player = player_by_code.get(player_code)
            if player:
                pitch_count_str = request.form.get(key, '').strip()
                if pitch_count_str and pitch_count_str.isdigit() and int(pitch_count_str) > 0:
                    pitch_count = int(pitch_count_str)
                    innings = _parse_innings(request.form.get(f'innings_code_{player_code}', ''))
                    strikes = _parse_int(request.form.get(f'strikes_code_{player_code}', ''))
                    strikeouts = _parse_int(request.form.get(f'strikeouts_code_{player_code}', ''))
                    walks = _parse_int(request.form.get(f'walks_code_{player_code}', ''))

                    pitch_data.append({
                        'player_id': player.id,
                        'pitch_count': pitch_count,
                        'strikes': strikes,
                        'innings_pitched': innings,
                        'strikeouts': strikeouts,
                        'walks': walks,
                    })

                    # For diff computation
                    final_pitchers.append({
                        'player_code': player_code,
                        'name': player.full_name,
                        'pitches_thrown': pitch_count,
                        'strikes_thrown': strikes,
                        'innings_pitched': innings,
                        'strikeouts': strikeouts,
                        'walks': walks
                    })

    # Build final JSON for audit
    final_json = {
        'our_score': our_score,
        'opponent_score': opponent_score,
        'pitchers': final_pitchers
    }

    # Record submission with diff
    GCScreenshotService.record_submission(session, final_json)

    # Submit the actual post-game report
    data = {
        'our_score': our_score,
        'opponent_score': opponent_score,
        'innings_batted': innings_batted,
        'innings_fielded': innings_fielded,
        'umpire_rating': umpire_rating if umpire_rating else None,
        'umpire_name': umpire_name or None,
        'umpire_comments': umpire_comments
    }

    success, report_obj, submit_error = post_game_service.submit_report(game_id, team_id, current_user.ID, data)

    if not success:
        return jsonify({'error': f'Failed to submit report: {submit_error}'}), 500

    # Save pitching stats if enabled and data provided
    if show_pitching and report_obj and pitch_data:
        PitchCountService.save_pitching_stats(report_obj.id, pitch_data)

    return jsonify({
        'success': True,
        'redirect': url_for('coach.postgame_success', game_id=game_id, team_id=team_id)
    })


@coach_bp.route('/postgame/<int:game_id>/<int:team_id>/screenshot/abandon', methods=['POST'])
@login_required
def postgame_screenshot_abandon(game_id, team_id):
    """Mark screenshot session as abandoned (user switched to manual entry)."""
    session_uuid = request.form.get('session_uuid')
    if session_uuid:
        session = GCScreenshotSession.query.filter_by(
            session_uuid=session_uuid,
            game_id=game_id,
            team_id=team_id
        ).order_by(GCScreenshotSession.attempt_number.desc()).first()

        if session and session.status not in [
            GCScreenshotSession.STATUS_SUBMITTED,
            GCScreenshotSession.STATUS_ABANDONED
        ]:
            GCScreenshotService.mark_abandoned(session)

    return jsonify({'success': True})
