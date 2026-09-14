"""Umpire lead management routes.

Provides UI for:
- Viewing prospective umpire leads
- Adding leads manually
- Importing leads from CSV
- Updating lead status
"""

import csv
from io import StringIO
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.umpires import umpires_bp, umpire_coordinator_required
from app.extensions import db
from app.models.umpire_profile import UmpireProfile
from app.models.org_season import OrgSeason


@umpires_bp.route('/leads/<int:org_season_id>')
@login_required
@umpire_coordinator_required
def leads(org_season_id):
    """List prospective/lead umpires for a season."""
    from datetime import date

    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Check if training has passed for this season
    training_date = org_season.get_training_date()
    training_passed = training_date and training_date < date.today()

    # Get future seasons for moving leads (ordered by most recent first)
    available_seasons = OrgSeason.query.filter(
        OrgSeason.org_id == org_season.org_id,
        OrgSeason.ID != org_season_id
    ).order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).all()

    # Auto-redirect to next season if training has passed and there's a newer season
    # Check if user explicitly requested this season via URL (not navbar)
    force_view = request.args.get('force') == '1'
    if training_passed and available_seasons and not force_view:
        # Find the next upcoming season (first one that's after current season)
        next_season = None
        for s in available_seasons:
            # Check if this season is "after" the current one
            if (s.year > org_season.year or
                (s.year == org_season.year and s.is_spring > org_season.is_spring)):
                next_season = s
                break
        if next_season:
            flash(f'Training for {org_season.season_desc} has passed. Showing {next_season.season_desc} leads.', 'info')
            return redirect(url_for('umpires.leads', org_season_id=next_season.ID))

    # Get leads for this season or unassigned leads
    leads_list = UmpireProfile.query.filter(
        UmpireProfile.status.in_(UmpireProfile.LEAD_STATUSES),
        db.or_(
            UmpireProfile.target_org_season_id == org_season_id,
            UmpireProfile.target_org_season_id.is_(None)
        )
    ).order_by(UmpireProfile.created_at.desc()).all()

    # Group by status
    prospective = [l for l in leads_list if l.status == UmpireProfile.STATUS_PROSPECTIVE]
    contacted = [l for l in leads_list if l.status == UmpireProfile.STATUS_CONTACTED]
    declined = [l for l in leads_list if l.status == UmpireProfile.STATUS_DECLINED]

    return render_template(
        'umpires/leads.html',
        org_season=org_season,
        prospective=prospective,
        contacted=contacted,
        declined=declined,
        lead_sources=UmpireProfile.LEAD_SOURCES,
        training_passed=training_passed,
        training_date=training_date,
        available_seasons=available_seasons
    )


@umpires_bp.route('/leads/<int:org_season_id>/add', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def lead_add(org_season_id):
    """Add a single lead manually."""
    from datetime import date

    org_season = OrgSeason.query.get_or_404(org_season_id)

    if request.method == 'POST':
        # Umpire info
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        umpire_email = request.form.get('umpire_email', '').strip()
        umpire_phone = request.form.get('umpire_phone', '').strip()

        # Parent/guardian info
        parent_name = request.form.get('parent_name', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()

        # Target season (from dropdown)
        target_season_id = request.form.get('target_season_id')
        if target_season_id:
            target_season_id = int(target_season_id)
        else:
            target_season_id = org_season_id

        # Other fields
        lead_source = request.form.get('lead_source', '').strip() or UmpireProfile.LEAD_SOURCE_MANUAL
        lead_notes = request.form.get('notes', '').strip()

        if not first_name or not last_name:
            flash('First name and last name are required.', 'error')
            # Need to pass all template vars on error
            available_seasons = _get_available_seasons_for_leads(org_season)
            default_season_id = _get_default_season_for_lead(available_seasons)
            return render_template(
                'umpires/lead_add.html',
                org_season=org_season,
                lead_sources=UmpireProfile.LEAD_SOURCES,
                available_seasons=available_seasons,
                default_season_id=default_season_id
            )

        # Create the lead
        profile = UmpireProfile.create_lead(
            first_name=first_name,
            last_name=last_name,
            umpire_email=umpire_email or None,
            umpire_phone=umpire_phone or None,
            parent_name=parent_name or None,
            parent_email=parent_email or None,
            parent_phone=parent_phone or None,
            lead_source=lead_source,
            lead_notes=lead_notes or None,
            target_org_season_id=target_season_id
        )

        flash(f'Lead "{profile.name}" created successfully.', 'success')
        return redirect(url_for('umpires.leads', org_season_id=target_season_id))

    # GET: Prepare available seasons
    available_seasons = _get_available_seasons_for_leads(org_season)
    default_season_id = _get_default_season_for_lead(available_seasons)

    return render_template(
        'umpires/lead_add.html',
        org_season=org_season,
        lead_sources=UmpireProfile.LEAD_SOURCES,
        available_seasons=available_seasons,
        default_season_id=default_season_id
    )


def _get_available_seasons_for_leads(org_season):
    """Get all current and future seasons for the lead dropdown."""
    from datetime import date

    # Get all seasons for this org, ordered by year/season
    all_seasons = OrgSeason.query.filter_by(
        org_id=org_season.org_id
    ).order_by(
        OrgSeason.year.asc(),
        OrgSeason.is_spring.asc()
    ).all()

    # Filter to current and future seasons
    # A season is "current or future" if its training date hasn't passed
    # or if it's marked as current/setup_mode
    today = date.today()
    available = []
    for s in all_seasons:
        training = s.get_training_date()
        # Include if: training hasn't passed, OR is current, OR in setup mode
        if s.is_current or s.setup_mode:
            available.append(s)
        elif training and training >= today:
            available.append(s)
        elif not training:
            # No training date - include if year >= current year
            if s.year >= today.year:
                available.append(s)

    return available


def _get_default_season_for_lead(available_seasons):
    """Determine the default season for a new lead.

    Returns the season whose training date is closest to (but not before) today,
    or the current season if all training dates have passed.
    """
    from datetime import date

    if not available_seasons:
        return None

    today = date.today()

    # Find season with training date closest to today (but >= today)
    best_match = None
    best_delta = None

    for s in available_seasons:
        training = s.get_training_date()
        if training and training >= today:
            delta = (training - today).days
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_match = s

    # If found one with upcoming training, use it
    if best_match:
        return best_match.ID

    # Otherwise, use the current season or first available
    for s in available_seasons:
        if s.is_current:
            return s.ID

    return available_seasons[0].ID if available_seasons else None


@umpires_bp.route('/leads/<int:org_season_id>/import', methods=['POST'])
@login_required
@umpire_coordinator_required
def leads_import(org_season_id):
    """Bulk import leads from CSV."""
    org_season = OrgSeason.query.get_or_404(org_season_id)

    if 'csv_file' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    file = request.files['csv_file']
    if not file.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    try:
        # Read CSV file
        content = file.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        imported = 0
        errors = []

        for row in reader:
            first_name = row.get('first_name', row.get('First Name', '')).strip()
            last_name = row.get('last_name', row.get('Last Name', '')).strip()
            email = row.get('email', row.get('Email', '')).strip()
            phone = row.get('phone', row.get('Phone', '')).strip()
            source = row.get('source', row.get('Source', '')).strip()
            notes = row.get('notes', row.get('Notes', '')).strip()

            if not first_name or not last_name:
                errors.append(f"Row missing name: {row}")
                continue

            # Determine lead source
            lead_source = UmpireProfile.LEAD_SOURCE_MANUAL
            if source:
                source_lower = source.lower()
                if 'website' in source_lower or 'form' in source_lower:
                    lead_source = UmpireProfile.LEAD_SOURCE_WEBSITE
                elif 'referral' in source_lower:
                    lead_source = UmpireProfile.LEAD_SOURCE_REFERRAL
                elif 'return' in source_lower:
                    lead_source = UmpireProfile.LEAD_SOURCE_RETURNING

            try:
                UmpireProfile.create_lead(
                    first_name=first_name,
                    last_name=last_name,
                    email=email or None,
                    phone=phone or None,
                    lead_source=lead_source,
                    lead_notes=notes or None,
                    target_org_season_id=org_season_id
                )
                imported += 1
            except Exception as e:
                errors.append(f"Error for {first_name} {last_name}: {e}")

        if imported > 0:
            flash(f'Successfully imported {imported} lead(s).', 'success')
        if errors:
            flash(f'{len(errors)} row(s) had errors.', 'warning')

    except Exception as e:
        flash(f'Error reading CSV: {e}', 'error')

    return redirect(url_for('umpires.leads', org_season_id=org_season_id))


@umpires_bp.route('/leads/<int:org_season_id>/<int:id>/status', methods=['POST'])
@login_required
@umpire_coordinator_required
def lead_status(org_season_id, id):
    """Update lead status."""
    profile = UmpireProfile.query.get_or_404(id)

    # Verify this lead belongs to the right season
    if profile.target_org_season_id and profile.target_org_season_id != org_season_id:
        flash('Lead not found.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    new_status = request.form.get('status', '').strip()
    anchor = f'lead-{id}'

    if new_status == 'contacted':
        profile.mark_contacted()
        flash(f'{profile.name} marked as contacted.', 'success')

    elif new_status == 'active':
        profile.convert_to_active()
        flash(f'{profile.name} converted to active umpire.', 'success')
        # Redirect to umpire management instead
        return redirect(url_for('umpires.management'))

    elif new_status == 'declined':
        profile.mark_declined()
        flash(f'{profile.name} marked as declined.', 'info')

    elif new_status in UmpireProfile.STATUSES:
        profile.status = new_status
        db.session.commit()
        flash(f'{profile.name} status updated.', 'success')

    else:
        flash('Invalid status.', 'error')

    redirect_url = url_for('umpires.leads', org_season_id=org_season_id)
    redirect_url += f'#{anchor}'
    return redirect(redirect_url)


@umpires_bp.route('/leads/<int:org_season_id>/<int:id>/notes', methods=['POST'])
@login_required
@umpire_coordinator_required
def lead_notes(org_season_id, id):
    """Update lead notes via AJAX."""
    profile = UmpireProfile.query.get_or_404(id)

    if profile.target_org_season_id and profile.target_org_season_id != org_season_id:
        return jsonify({'error': 'Lead not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    notes = data.get('notes', '').strip()
    profile.lead_notes = notes if notes else None
    db.session.commit()

    return jsonify({'success': True})


@umpires_bp.route('/leads/<int:org_season_id>/<int:id>/delete', methods=['POST'])
@login_required
@umpire_coordinator_required
def lead_delete(org_season_id, id):
    """Delete a lead (only for prospective leads that haven't been contacted)."""
    profile = UmpireProfile.query.get_or_404(id)

    if profile.target_org_season_id and profile.target_org_season_id != org_season_id:
        flash('Lead not found.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    # Only allow deletion of prospective leads
    if profile.status != UmpireProfile.STATUS_PROSPECTIVE:
        flash('Can only delete prospective leads.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    name = profile.name
    db.session.delete(profile)
    db.session.commit()

    flash(f'Lead "{name}" deleted.', 'info')
    return redirect(url_for('umpires.leads', org_season_id=org_season_id))


@umpires_bp.route('/leads/<int:org_season_id>/<int:id>/move', methods=['POST'])
@login_required
@umpire_coordinator_required
def lead_move(org_season_id, id):
    """Move a lead to a different season."""
    profile = UmpireProfile.query.get_or_404(id)

    # Verify this lead belongs to the current season view
    if profile.target_org_season_id and profile.target_org_season_id != org_season_id:
        flash('Lead not found.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    new_season_id = request.form.get('new_season_id')
    if not new_season_id:
        flash('No target season specified.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    new_season = OrgSeason.query.get(int(new_season_id))
    if not new_season:
        flash('Target season not found.', 'error')
        return redirect(url_for('umpires.leads', org_season_id=org_season_id))

    profile.target_org_season_id = new_season.ID
    db.session.commit()

    flash(f'"{profile.name}" moved to {new_season.season_name}.', 'success')
    return redirect(url_for('umpires.leads', org_season_id=org_season_id))
