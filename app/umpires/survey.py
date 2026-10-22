"""Umpire survey management routes."""

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.umpires import umpires_bp, umpire_coordinator_required
from app.extensions import db
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_survey import UmpireSurveyResponse
from app.models.umpire_survey_send import UmpireSurveySend
from app.models.org_season import OrgSeason
from app.models.game import Game
from app.models.training_completion import TrainingCompletion
from app.models.training_type import TrainingType
from app.services.notification_service import GmailService


def get_umpire_game_counts_from_assignr(org_season_id):
    """Get count of games worked by each umpire for a season from Assignr.

    This fetches real game data from Assignr and maps it back to local
    UmpireProfile records using their assignr_id.

    Returns dict mapping umpire_profile_id -> game_count
    """
    from datetime import datetime, date
    from collections import defaultdict
    from app.models.org_season import OrgSeason
    from app.models.league_season import LeagueSeason
    from app.services.assignr_service import get_assignr_service

    season = OrgSeason.query.get(org_season_id)
    if not season:
        return {}

    # Get season date range from LeagueSeason
    league_seasons = LeagueSeason.query.filter_by(
        year=season.year,
        is_spring=season.is_spring,
        active=1
    ).all()

    if not league_seasons:
        return {}

    # Find the earliest opening_day_date and latest season_end_date
    start_date = None
    end_date = None
    for ls in league_seasons:
        if ls.opening_day_date:
            if start_date is None or ls.opening_day_date < start_date:
                start_date = ls.opening_day_date
        if ls.season_end_date:
            if end_date is None or ls.season_end_date > end_date:
                end_date = ls.season_end_date

    if not start_date or not end_date:
        return {}

    # Fetch games from Assignr
    assignr = get_assignr_service()
    if not assignr.is_configured():
        return {}

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    try:
        assignr_games = assignr.get_all_games(start_dt, end_dt)
    except Exception:
        return {}

    # Get local game statuses for filtering cancelled games
    assignr_ids = [str(g.get('id')) for g in assignr_games if g.get('id')]
    local_games = {}
    if assignr_ids:
        games_query = Game.query.filter(
            Game.assignr_id.in_(assignr_ids),
            Game.active == 1
        ).all()
        local_games = {g.assignr_id: g for g in games_query}

    # Count games per Assignr official_id
    games_by_official = defaultdict(int)
    for game in assignr_games:
        # Skip cancelled games
        if game.get('is_cancelled'):
            continue

        # Skip if local game is cancelled/rainout/postponed
        assignr_id = str(game.get('id', ''))
        local_game = local_games.get(assignr_id)
        if local_game and local_game.status in ('cancelled', 'rainout', 'postponed'):
            continue

        # Only count completed games (game date has passed)
        game_date = game.get('_game_date')
        if not game_date or game_date.date() > date.today():
            continue

        # Count accepted assignments
        assignments = game.get('_embedded', {}).get('assignments', []) or []
        for assignment in assignments:
            if assignment.get('accepted') not in [True, 'True']:
                continue

            embedded = assignment.get('_embedded', {}) or {}
            official = embedded.get('official', {}) or {}
            official_id = official.get('id')

            if official_id:
                games_by_official[str(official_id)] += 1

    # Map Assignr official_ids to local UmpireProfile IDs
    # Get all umpire profiles with assignr_ids
    profiles_with_assignr = UmpireProfile.query.filter(
        UmpireProfile.assignr_id.isnot(None),
        UmpireProfile.assignr_id != ''
    ).all()

    assignr_to_profile = {str(p.assignr_id): p.id for p in profiles_with_assignr}

    # Build final result mapping profile_id -> game_count
    result = {}
    for assignr_official_id, count in games_by_official.items():
        profile_id = assignr_to_profile.get(assignr_official_id)
        if profile_id:
            result[profile_id] = count

    return result


def get_umpire_training_status(umpire_ids):
    """Get training completion status for umpires.

    Returns dict mapping umpire_profile_id -> {
        'completed_trainings': bool (all required trainings complete),
        'training_list': list of completed training names
    }
    """
    # Get required trainings for umpires
    required_trainings = TrainingType.get_required_for_umpires()
    required_ids = {t.id for t in required_trainings}

    # Get completions for all these umpires
    completions = TrainingCompletion.query.filter(
        TrainingCompletion.umpire_profile_id.in_(umpire_ids)
    ).options(
        joinedload(TrainingCompletion.training_type)
    ).all()

    # Build per-umpire status
    result = {}
    for ump_id in umpire_ids:
        ump_completions = [c for c in completions if c.umpire_profile_id == ump_id]
        valid_completions = [c for c in ump_completions if c.is_valid]
        completed_ids = {c.training_type_id for c in valid_completions}
        training_names = [c.training_type.name for c in valid_completions if c.training_type]

        result[ump_id] = {
            'completed_trainings': required_ids.issubset(completed_ids) if required_ids else True,
            'training_list': training_names
        }

    return result


@umpires_bp.route('/survey')
@umpire_coordinator_required
def survey_management():
    """Manage umpire survey sends - view who's received, select and send."""
    # Get current season
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'error')
        return redirect(url_for('umpires.index'))

    # Get all active umpires with their survey status
    umpires = UmpireProfile.query.filter(
        UmpireProfile.status == 'active'
    ).options(
        joinedload(UmpireProfile.user)
    ).order_by(UmpireProfile._last_name, UmpireProfile._first_name).all()

    # Get who's been sent the survey
    sent_ids = UmpireSurveySend.get_sent_umpire_ids(current_season.ID)

    # Get who's responded
    responded_ids = set()
    responses = UmpireSurveyResponse.query.filter_by(
        org_season_id=current_season.ID
    ).all()
    for r in responses:
        responded_ids.add(r.umpire_profile_id)

    # Get game counts for all umpires this season (from Assignr)
    game_counts = get_umpire_game_counts_from_assignr(current_season.ID)

    # Get training status for all umpires
    umpire_ids = [ump.id for ump in umpires]
    training_status = get_umpire_training_status(umpire_ids)

    # Build umpire list with status
    umpire_rows = []
    for ump in umpires:
        # Get send history for this umpire
        sends = UmpireSurveySend.get_send_history(ump.id, current_season.ID)
        last_sent = sends[0].sent_at if sends else None
        send_count = len(sends)

        # Get response if any
        response = None
        if ump.id in responded_ids:
            response = UmpireSurveyResponse.get_for_umpire_season(ump.id, current_season.ID)

        # Check login status (has_logged_in = user exists and has logged in)
        has_logged_in = False
        has_account = False
        if ump.user:
            has_account = True
            has_logged_in = ump.user.last_login is not None

        # Get game count
        games_worked = game_counts.get(ump.id, 0)

        # Get training status
        training = training_status.get(ump.id, {'completed_trainings': False, 'training_list': []})

        umpire_rows.append({
            'profile': ump,
            'has_been_sent': ump.id in sent_ids,
            'last_sent': last_sent,
            'send_count': send_count,
            'has_responded': ump.id in responded_ids,
            'response': response,
            'has_email': bool(ump.contact_email),
            'has_account': has_account,
            'has_logged_in': has_logged_in,
            'games_worked': games_worked,
            'trained': training['completed_trainings'],
            'training_list': training['training_list']
        })

    # Counts for summary
    total = len(umpire_rows)
    sent_count = sum(1 for r in umpire_rows if r['has_been_sent'])
    not_sent_count = total - sent_count
    responded_count = sum(1 for r in umpire_rows if r['has_responded'])
    worked_games_count = sum(1 for r in umpire_rows if r['games_worked'] > 0)
    trained_count = sum(1 for r in umpire_rows if r['trained'])

    return render_template(
        'umpires/survey_management.html',
        season=current_season,
        umpire_rows=umpire_rows,
        total=total,
        sent_count=sent_count,
        not_sent_count=not_sent_count,
        responded_count=responded_count,
        worked_games_count=worked_games_count,
        trained_count=trained_count
    )


@umpires_bp.route('/survey/send', methods=['POST'])
@umpire_coordinator_required
def survey_send():
    """Send survey emails to selected umpires.

    For umpires who have never logged in, sends a password setup email first.
    For umpires who have logged in, sends direct survey link.
    """
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'error')
        return redirect(url_for('umpires.survey_management'))

    # Get selected umpire IDs
    selected_ids = request.form.getlist('umpire_ids')
    if not selected_ids:
        flash('No umpires selected.', 'warning')
        return redirect(url_for('umpires.survey_management'))

    # Convert to integers
    try:
        umpire_ids = [int(uid) for uid in selected_ids]
    except ValueError:
        flash('Invalid umpire selection.', 'error')
        return redirect(url_for('umpires.survey_management'))

    # Get umpire profiles with user relationships
    umpires = UmpireProfile.query.filter(
        UmpireProfile.id.in_(umpire_ids)
    ).options(
        joinedload(UmpireProfile.user)
    ).all()

    # Build survey URL
    survey_url = url_for('public.umpire_survey', _external=True)

    sent_count = 0
    skipped_count = 0
    setup_count = 0  # Track password setup emails

    for ump in umpires:
        email = ump.contact_email
        if not email:
            skipped_count += 1
            continue

        first_name = ump.first_name or 'Umpire'

        # Check if user has ever logged in
        has_logged_in = ump.user and ump.user.last_login is not None

        if not has_logged_in and ump.user:
            # User has account but never logged in - send password setup + survey
            try:
                token = ump.user.generate_reset_token()
                reset_url = url_for('auth.reset_password', token=token, _external=True)

                subject = f'SDLL Umpire Survey - Set Up Your Account'
                body_text = f"""Hi {first_name},

Thank you for being part of the SDLL umpire team this season!

We'd love to hear your feedback about your experience. Before you can access the survey, you'll need to set up your account password.

Step 1: Set up your password
{reset_url}

Step 2: Take the survey (after logging in)
{survey_url}

The survey only takes a minute and helps us improve the program for next season.

This password link will expire in 24 hours.

Thanks,
SDLL Umpire Coordinator
"""

                body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: rgb(34, 139, 34);">SDLL Umpire Survey</h2>
    <p>Hi {first_name},</p>
    <p>Thank you for being part of the SDLL umpire team this season!</p>
    <p>We'd love to hear your feedback about your experience. Before you can access the survey, you'll need to set up your account password.</p>

    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0 0 15px 0;"><strong>Step 1:</strong> Set up your password</p>
        <a href="{reset_url}" style="background-color: rgb(255, 140, 0); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Set Your Password
        </a>
        <p style="font-size: 12px; color: #666; margin-top: 10px;">This link expires in 24 hours</p>
    </div>

    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0 0 15px 0;"><strong>Step 2:</strong> Take the survey (after logging in)</p>
        <a href="{survey_url}" style="background-color: rgb(34, 139, 34); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Take the Survey
        </a>
    </div>

    <p>The survey only takes a minute and helps us improve the program for next season.</p>
    <p>Thanks,<br>SDLL Umpire Coordinator</p>
</div>
"""
                email_service = GmailService()
                email_service.send_email(
                    to=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )

                # Record the send
                UmpireSurveySend.record_send(
                    umpire_profile_id=ump.id,
                    org_season_id=current_season.ID,
                    sent_by_user_id=current_user.ID
                )
                sent_count += 1
                setup_count += 1
            except Exception as e:
                flash(f'Error sending to {ump.name}: {str(e)}', 'error')

        elif not ump.user:
            # Managed umpire without account - can't send survey (no way to authenticate)
            skipped_count += 1

        else:
            # User has logged in before - send direct survey link
            subject = f'SDLL Umpire Survey - {current_season.season_name}'

            body_text = f"""Hi {first_name},

Thank you for being part of the SDLL umpire team this season!

We'd love to hear your feedback about your experience. Please take a moment to complete our brief survey:

{survey_url}

The survey only takes a minute and helps us improve the program for next season.

Thanks,
SDLL Umpire Coordinator
"""

            body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: rgb(34, 139, 34);">SDLL Umpire Survey</h2>
    <p>Hi {first_name},</p>
    <p>Thank you for being part of the SDLL umpire team this season!</p>
    <p>We'd love to hear your feedback about your experience. Please take a moment to complete our brief survey:</p>
    <p style="margin: 25px 0;">
        <a href="{survey_url}" style="background-color: rgb(34, 139, 34); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Take the Survey
        </a>
    </p>
    <p>The survey only takes a minute and helps us improve the program for next season.</p>
    <p>Thanks,<br>SDLL Umpire Coordinator</p>
</div>
"""

            # Send the email
            try:
                email_service = GmailService()
                email_service.send_email(
                    to=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )

                # Record the send
                UmpireSurveySend.record_send(
                    umpire_profile_id=ump.id,
                    org_season_id=current_season.ID,
                    sent_by_user_id=current_user.ID
                )
                sent_count += 1
            except Exception as e:
                flash(f'Error sending to {ump.name}: {str(e)}', 'error')

    db.session.commit()

    if sent_count > 0:
        msg = f'Survey sent to {sent_count} umpire(s).'
        if setup_count > 0:
            msg += f' ({setup_count} included password setup instructions)'
        flash(msg, 'success')
    if skipped_count > 0:
        flash(f'Skipped {skipped_count} umpire(s) with no email or no account.', 'warning')

    return redirect(url_for('umpires.survey_management'))


@umpires_bp.route('/survey/preview/<int:umpire_id>')
@umpire_coordinator_required
def survey_preview(umpire_id):
    """Preview the email that would be sent to an umpire."""
    from flask import jsonify

    current_season = OrgSeason.get_current_season()
    if not current_season:
        return jsonify({'error': 'No active season found'}), 400

    ump = UmpireProfile.query.options(
        joinedload(UmpireProfile.user)
    ).get(umpire_id)

    if not ump:
        return jsonify({'error': 'Umpire not found'}), 404

    # Build survey URL
    survey_url = url_for('public.umpire_survey', _external=True)

    email = ump.contact_email
    first_name = ump.first_name or 'Umpire'

    # Check login status
    has_logged_in = ump.user and ump.user.last_login is not None

    if not ump.user:
        # No account - can't send
        return jsonify({
            'can_send': False,
            'reason': 'No account linked to this umpire profile',
            'umpire_name': ump.name,
            'email': email or 'No email'
        })

    if not email:
        return jsonify({
            'can_send': False,
            'reason': 'No email address on file',
            'umpire_name': ump.name,
            'email': None
        })

    if not has_logged_in:
        # Password setup + survey email
        # Note: We don't actually generate the token for preview, just show placeholder
        reset_url = '[Password Reset Link - generated at send time]'

        subject = 'SDLL Umpire Survey - Set Up Your Account'
        body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: rgb(34, 139, 34);">SDLL Umpire Survey</h2>
    <p>Hi {first_name},</p>
    <p>Thank you for being part of the SDLL umpire team this season!</p>
    <p>We'd love to hear your feedback about your experience. Before you can access the survey, you'll need to set up your account password.</p>

    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0 0 15px 0;"><strong>Step 1:</strong> Set up your password</p>
        <a href="#" style="background-color: rgb(255, 140, 0); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Set Your Password
        </a>
        <p style="font-size: 12px; color: #666; margin-top: 10px;">This link expires in 24 hours</p>
    </div>

    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0 0 15px 0;"><strong>Step 2:</strong> Take the survey (after logging in)</p>
        <a href="{survey_url}" style="background-color: rgb(34, 139, 34); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Take the Survey
        </a>
    </div>

    <p>The survey only takes a minute and helps us improve the program for next season.</p>
    <p>Thanks,<br>SDLL Umpire Coordinator</p>
</div>
"""
        email_type = 'password_setup'

    else:
        # Direct survey link
        subject = f'SDLL Umpire Survey - {current_season.season_name}'
        body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: rgb(34, 139, 34);">SDLL Umpire Survey</h2>
    <p>Hi {first_name},</p>
    <p>Thank you for being part of the SDLL umpire team this season!</p>
    <p>We'd love to hear your feedback about your experience. Please take a moment to complete our brief survey:</p>
    <p style="margin: 25px 0;">
        <a href="{survey_url}" style="background-color: rgb(34, 139, 34); color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Take the Survey
        </a>
    </p>
    <p>The survey only takes a minute and helps us improve the program for next season.</p>
    <p>Thanks,<br>SDLL Umpire Coordinator</p>
</div>
"""
        email_type = 'direct_survey'

    return jsonify({
        'can_send': True,
        'umpire_name': ump.name,
        'email': email,
        'subject': subject,
        'body_html': body_html,
        'email_type': email_type,
        'has_logged_in': has_logged_in
    })


@umpires_bp.route('/survey/responses')
@umpire_coordinator_required
def survey_responses():
    """View all survey responses for the current season."""
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No active season found.', 'error')
        return redirect(url_for('umpires.index'))

    # Get all responses with umpire info
    responses = UmpireSurveyResponse.query.filter_by(
        org_season_id=current_season.ID
    ).options(
        joinedload(UmpireSurveyResponse.umpire_profile)
    ).order_by(UmpireSurveyResponse.created_at.desc()).all()

    # Get summary stats
    summary = UmpireSurveyResponse.get_season_summary(current_season.ID)

    return render_template(
        'umpires/survey_responses.html',
        season=current_season,
        responses=responses,
        summary=summary
    )
