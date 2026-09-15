"""Coach routes - post-game reports and coach-specific features."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.coach import CoachSeason, CoachUser
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.models.post_game_report import PostGameReport
from app.services import post_game_service


coach_bp = Blueprint('coach', __name__)


@coach_bp.route('/postgame/<token>')
def postgame_entry(token):
    """Entry point from email link - validates token and redirects to form.

    Query params:
        g: game_id
        t: team_id
    """
    game_id = request.args.get('g', type=int)
    team_id = request.args.get('t', type=int)

    if not game_id or not team_id:
        flash('Invalid link. Please use the link from your email.', 'error')
        return redirect(url_for('main.dashboard'))

    # Validate token
    if not post_game_service.validate_report_token(token, game_id, team_id):
        flash('Invalid or expired link. Please use the link from your email.', 'error')
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

    # Redirect to the actual form
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

    # Check if league is kid-pitch
    league = League.get_by_name(game.league)
    is_kid_pitch = league and league.pitch_type == 'kid_pitch' if league else False

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'not_played':
            # Redirect to not-played form
            return redirect(url_for('coach.postgame_not_played', game_id=game_id, team_id=team_id))

        elif action == 'review':
            # Validate form data
            errors = []

            our_score = request.form.get('our_score', '').strip()
            opponent_score = request.form.get('opponent_score', '').strip()
            innings_batted = request.form.get('innings_batted', '').strip()
            innings_fielded = request.form.get('innings_fielded', '').strip()
            umpire_name = request.form.get('umpire_name', '').strip()
            umpire_rating = request.form.get('umpire_rating', '').strip()
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

            if not umpire_name:
                errors.append('Umpire name is required')

            if not umpire_rating:
                errors.append('Umpire rating is required')
            elif umpire_rating not in PostGameReport.RATINGS:
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
                                       form_data=request.form)

            # Store in session for review
            review_data = {
                'our_score': int(our_score),
                'opponent_score': int(opponent_score),
                'innings_batted': int(innings_batted),
                'innings_fielded': int(innings_fielded),
                'umpire_name': umpire_name,
                'umpire_rating': umpire_rating,
                'umpire_comments': umpire_comments
            }

            return render_template('coach/postgame_review.html',
                                   game=game,
                                   team=team,
                                   opponent=opponent,
                                   data=review_data,
                                   rating_labels=PostGameReport.RATING_LABELS)

    # GET request - show form
    return render_template('coach/postgame_form.html',
                           game=game,
                           team=team,
                           opponent=opponent,
                           report=report,
                           is_kid_pitch=is_kid_pitch,
                           ratings=PostGameReport.RATINGS,
                           rating_labels=PostGameReport.RATING_LABELS,
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
