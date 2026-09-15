"""Email campaign management routes for umpire coordinators.

Provides UI for:
- Viewing campaign dashboard for a season
- Previewing campaign content
- Editing campaign content and trigger dates
- Sending campaigns
- Regenerating campaigns
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from app.umpires import umpires_bp, umpire_coordinator_required
from app.extensions import db
from app.models.email_campaign_template import EmailCampaignTemplate
from app.models.email_campaign_instance import EmailCampaignInstance
from app.models.org_season import OrgSeason
from app.services.email_campaign_service import EmailCampaignService


@umpires_bp.route('/campaigns/<int:org_season_id>')
@login_required
@umpire_coordinator_required
def campaigns(org_season_id):
    """Campaign dashboard for a season.

    Simplified view with three sections:
    - Scheduled: Will auto-send on their trigger date
    - Paused: Will not send (can be resumed)
    - Sent: Already sent
    """
    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Get all campaign instances for this season
    instances = EmailCampaignInstance.get_for_season(org_season_id)

    # Group by effective status (handles legacy status values)
    scheduled = [i for i in instances if i.effective_status == EmailCampaignInstance.STATUS_SCHEDULED]
    paused = [i for i in instances if i.effective_status == EmailCampaignInstance.STATUS_PAUSED]
    sent = [i for i in instances if i.effective_status == EmailCampaignInstance.STATUS_SENT]

    # Get available templates (not yet generated for this season)
    all_templates = EmailCampaignTemplate.get_active()
    existing_template_ids = {i.template_id for i in instances}
    available_templates = [t for t in all_templates if t.id not in existing_template_ids]

    return render_template(
        'umpires/campaigns.html',
        org_season=org_season,
        scheduled=scheduled,
        paused=paused,
        sent=sent,
        available_templates=available_templates
    )


@umpires_bp.route('/campaigns/<int:org_season_id>/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaigns_generate(org_season_id):
    """Generate all campaigns for a season.

    Note: Campaigns are now auto-generated when OrgSeason is created.
    This route is kept for manual regeneration if needed.
    """
    org_season = OrgSeason.query.get_or_404(org_season_id)

    service = EmailCampaignService()
    created = service.generate_all_campaigns_for_season(org_season)

    if created:
        flash(f'Generated {len(created)} campaign(s).', 'success')
    else:
        flash('No new campaigns to generate. Campaigns are auto-generated when the season is created.', 'info')

    return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>')
@login_required
@umpire_coordinator_required
def campaign_preview(org_season_id, id):
    """Preview a campaign."""
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    org_season = OrgSeason.query.get(org_season_id)

    return render_template(
        'umpires/campaign_preview.html',
        org_season=org_season,
        instance=instance
    )


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def campaign_edit(org_season_id, id):
    """Edit campaign content and trigger date."""
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    if not instance.is_editable:
        flash('This campaign cannot be edited.', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    org_season = OrgSeason.query.get(org_season_id)

    if request.method == 'POST':
        # Update content
        subject = request.form.get('subject', '').strip()
        body_html = request.form.get('body_html', '').strip()
        body_text = request.form.get('body_text', '').strip()

        if subject and body_html:
            instance.update_content(subject=subject, body_html=body_html, body_text=body_text)

        # Update trigger date if changed
        trigger_date_str = request.form.get('trigger_date', '').strip()
        if trigger_date_str:
            try:
                new_date = datetime.strptime(trigger_date_str, '%Y-%m-%d').date()
                if new_date != instance.trigger_date:
                    instance.update_trigger_date(new_date)
            except ValueError:
                flash('Invalid trigger date format.', 'error')

        flash('Campaign updated.', 'success')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    # Get template variables for reference
    template = instance.template
    available_vars = template.get_available_variables() if template else {}

    return render_template(
        'umpires/campaign_edit.html',
        org_season=org_season,
        instance=instance,
        available_vars=available_vars
    )


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/send', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaign_send(org_season_id, id):
    """Send a campaign manually (bypasses trigger date check).

    Note: Campaigns auto-send at 8 AM on their trigger date.
    This route allows coordinators to send early if needed.
    """
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    if not instance.is_scheduled:
        flash('This campaign cannot be sent (must be scheduled, not paused or already sent).', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    if instance.recipient_count == 0:
        flash('This campaign has no recipients.', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    service = EmailCampaignService()
    # Use force=True to allow sending before trigger date
    sent, failed = service.send_campaign(instance, current_user.ID, force=True)

    if sent > 0:
        flash(f'Campaign sent to {sent} recipient(s).', 'success')
    if failed > 0:
        flash(f'Failed to send to {failed} recipient(s).', 'warning')

    return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/pause', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaign_pause(org_season_id, id):
    """Pause a campaign (prevent auto-send)."""
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    if not instance.is_scheduled:
        flash('Only scheduled campaigns can be paused.', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    instance.pause()
    flash('Campaign paused. It will not auto-send until resumed.', 'info')

    return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/resume', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaign_resume(org_season_id, id):
    """Resume a paused campaign (re-enable auto-send)."""
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    if not instance.is_paused:
        flash('Only paused campaigns can be resumed.', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    instance.resume()
    flash('Campaign resumed. It will auto-send on its trigger date.', 'success')

    return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/skip', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaign_skip(org_season_id, id):
    """Legacy: Skip a campaign (now redirects to pause)."""
    return campaign_pause(org_season_id, id)


@umpires_bp.route('/campaigns/<int:org_season_id>/<int:id>/regenerate', methods=['POST'])
@login_required
@umpire_coordinator_required
def campaign_regenerate(org_season_id, id):
    """Regenerate campaign content (re-fetch recipients, re-render)."""
    instance = EmailCampaignInstance.query.get_or_404(id)
    if instance.org_season_id != org_season_id:
        flash('Campaign not found.', 'error')
        return redirect(url_for('umpires.campaigns', org_season_id=org_season_id))

    if not instance.is_editable:
        flash('This campaign cannot be regenerated.', 'error')
        return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))

    service = EmailCampaignService()
    if service.regenerate_campaign(instance):
        flash(f'Campaign regenerated with {instance.recipient_count} recipient(s).', 'success')
    else:
        flash('Failed to regenerate campaign.', 'error')

    return redirect(url_for('umpires.campaign_preview', org_season_id=org_season_id, id=id))
