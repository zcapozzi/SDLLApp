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
from app.services.notification_service import GmailService


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

        umpire_rows.append({
            'profile': ump,
            'has_been_sent': ump.id in sent_ids,
            'last_sent': last_sent,
            'send_count': send_count,
            'has_responded': ump.id in responded_ids,
            'response': response,
            'has_email': bool(ump.contact_email)
        })

    # Counts for summary
    total = len(umpire_rows)
    sent_count = sum(1 for r in umpire_rows if r['has_been_sent'])
    not_sent_count = total - sent_count
    responded_count = sum(1 for r in umpire_rows if r['has_responded'])

    return render_template(
        'umpires/survey_management.html',
        season=current_season,
        umpire_rows=umpire_rows,
        total=total,
        sent_count=sent_count,
        not_sent_count=not_sent_count,
        responded_count=responded_count
    )


@umpires_bp.route('/survey/send', methods=['POST'])
@umpire_coordinator_required
def survey_send():
    """Send survey emails to selected umpires."""
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

    # Get umpire profiles
    umpires = UmpireProfile.query.filter(UmpireProfile.id.in_(umpire_ids)).all()

    # Build survey URL
    survey_url = url_for('public.umpire_survey', _external=True)

    sent_count = 0
    skipped_count = 0

    for ump in umpires:
        email = ump.contact_email
        if not email:
            skipped_count += 1
            continue

        # Build email content
        first_name = ump.first_name or 'Umpire'
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
        flash(f'Survey sent to {sent_count} umpire(s).', 'success')
    if skipped_count > 0:
        flash(f'Skipped {skipped_count} umpire(s) with no email address.', 'warning')

    return redirect(url_for('umpires.survey_management'))


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
