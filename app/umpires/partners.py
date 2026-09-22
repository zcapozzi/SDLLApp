"""Umpire partner organization management routes.

Handles:
- Listing partner organizations (Diamond, Dynamic, etc.)
- Adding new partners
- Editing partner details and contacts
- Generating schedule tokens
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models.user import User
from app.models.umpire_partner import UmpirePartner
from app.models.partner_contact import PartnerContact
from app.models.partner_league_rate import PartnerLeagueRate
from app.models.league import League

from . import umpires_bp, umpire_coordinator_required, logger


@umpires_bp.route('/partners')
@login_required
@umpire_coordinator_required
def partners():
    """List umpire partner organizations."""
    partners = UmpirePartner.query.filter_by(org_id=1).all()
    return render_template('umpires/partners.html', partners=partners)


@umpires_bp.route('/partners/add', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def add_partner():
    """Add a new umpire partner organization."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_code = request.form.get('short_code', '').strip().upper()
        notification_preference = request.form.get('notification_preference', 'weekly')

        if not name or not short_code:
            flash('Name and short code are required.', 'error')
            return render_template('umpires/add_partner.html')

        # Check for duplicate
        existing = UmpirePartner.query.filter_by(org_id=1, short_code=short_code).first()
        if existing:
            flash(f'A partner with code {short_code} already exists.', 'error')
            return render_template('umpires/add_partner.html')

        partner = UmpirePartner(
            org_id=1,
            name=name,
            short_code=short_code,
            notification_preference=notification_preference,
            active=True
        )

        db.session.add(partner)
        db.session.commit()

        logger.info(f'Added partner: {name} ({short_code})')
        flash(f'Added partner: {name}. You can now add contacts.', 'success')
        return redirect(url_for('umpires.edit_partner', id=partner.id))

    return render_template('umpires/add_partner.html')


@umpires_bp.route('/partners/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def edit_partner(id):
    """Edit umpire partner organization."""
    partner = UmpirePartner.query.get_or_404(id)
    contacts = partner.get_active_contacts()
    # User.name is a property (encrypted), so fetch all and sort in Python
    users = User.query.filter(User.role.like('%partner_contact%')).all()
    users = sorted(users, key=lambda u: (u.name or '').lower())

    if request.method == 'POST':
        action = request.form.get('action', 'save_partner')

        if action == 'save_partner':
            partner.name = request.form.get('name', '').strip()
            partner.short_code = request.form.get('short_code', '').strip().upper()
            partner.notification_preference = request.form.get('notification_preference', 'weekly')
            partner.active = request.form.get('active') == 'on'
            partner.prepays_invoices = request.form.get('prepays_invoices') == 'on'

            db.session.commit()
            logger.info(f'Updated partner: {partner.name}')
            flash(f'Updated partner: {partner.name}', 'success')
            return redirect(url_for('umpires.edit_partner', id=id))

        elif action == 'add_contact':
            user_id = request.form.get('user_id')
            email = request.form.get('contact_email', '').strip()
            name = request.form.get('contact_name', '').strip()
            phone = request.form.get('contact_phone', '').strip()
            message_types = request.form.getlist('message_types')
            is_primary = request.form.get('is_primary') == 'on'

            if not email and not user_id:
                flash('Email is required for a contact.', 'error')
                return redirect(url_for('umpires.edit_partner', id=id))

            # If using a user, get their email
            if user_id:
                user = User.query.get(user_id)
                if user:
                    email = user.decrypted_email
                    name = user.name

            contact = PartnerContact(
                partner_id=partner.id,
                user_id=int(user_id) if user_id else None,
                email=email,
                name=name or None,
                phone=phone or None,
                message_types='|'.join(message_types) if message_types else '',
                is_primary=is_primary
            )
            db.session.add(contact)

            # If this is primary, unset other primary contacts
            if is_primary:
                for c in contacts:
                    c.is_primary = False

            db.session.commit()
            flash(f'Added contact: {name or email}', 'success')
            return redirect(url_for('umpires.edit_partner', id=id) + '#contacts')

        elif action == 'update_contact':
            contact_id = request.form.get('contact_id')
            contact = PartnerContact.query.get(contact_id)
            if contact and contact.partner_id == partner.id:
                contact.email = request.form.get('contact_email', '').strip()
                contact.name = request.form.get('contact_name', '').strip() or None
                contact.phone = request.form.get('contact_phone', '').strip() or None
                message_types = request.form.getlist('message_types')
                contact.message_types = '|'.join(message_types) if message_types else ''
                is_primary = request.form.get('is_primary') == 'on'

                # If this is primary, unset other primary contacts
                if is_primary and not contact.is_primary:
                    for c in contacts:
                        c.is_primary = False
                contact.is_primary = is_primary

                db.session.commit()
                flash(f'Updated contact: {contact.display_name}', 'success')
            return redirect(url_for('umpires.edit_partner', id=id) + '#contacts')

        elif action == 'delete_contact':
            contact_id = request.form.get('contact_id')
            contact = PartnerContact.query.get(contact_id)
            if contact and contact.partner_id == partner.id:
                name = contact.display_name
                db.session.delete(contact)
                db.session.commit()
                flash(f'Removed contact: {name}', 'success')
            return redirect(url_for('umpires.edit_partner', id=id) + '#contacts')

        return redirect(url_for('umpires.partners'))

    return render_template('umpires/edit_partner.html',
                           partner=partner,
                           contacts=contacts,
                           users=users,
                           message_types=PartnerContact.ALL_MESSAGE_TYPES)


@umpires_bp.route('/partners/<int:id>/generate-token', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_partner_token(id):
    """Generate a new schedule token for a partner."""
    partner = UmpirePartner.query.get_or_404(id)
    partner.generate_schedule_token()
    db.session.commit()

    logger.info(f'Generated schedule token for partner: {partner.name}')
    flash(f'Generated new schedule token for {partner.name}', 'success')
    return redirect(url_for('umpires.partners'))


@umpires_bp.route('/partners/<int:id>/league-rates')
@login_required
@umpire_coordinator_required
def partner_league_rates(id):
    """View and manage league-specific rates for a partner."""
    partner = UmpirePartner.query.get_or_404(id)
    leagues = League.get_all_active()

    # Get existing rate records
    rates = PartnerLeagueRate.get_for_partner(partner.id)
    rate_by_league = {r.league_id: r for r in rates if r.org_season_id is None}

    # Build rate data for template
    league_rates = []
    for league in leagues:
        rate_record = rate_by_league.get(league.ID)
        league_rates.append({
            'league': league,
            'rate_normal': rate_record.rate_normal if rate_record else None,
            'rate_ntl': rate_record.rate_ntl if rate_record else None,
            'has_override': rate_record is not None and rate_record.has_override,
            'effective_normal': partner.get_rate_for_league(league.ID, is_ntl=False),
            'effective_ntl': partner.get_rate_for_league(league.ID, is_ntl=True),
        })

    return render_template('umpires/partner_league_rates.html',
                           partner=partner,
                           league_rates=league_rates)


@umpires_bp.route('/partners/<int:id>/league-rates', methods=['POST'])
@login_required
@umpire_coordinator_required
def save_partner_league_rates(id):
    """Save league-specific rate overrides for a partner."""
    from decimal import Decimal, InvalidOperation

    partner = UmpirePartner.query.get_or_404(id)
    leagues = League.get_all_active()
    updated_count = 0
    anchor = None

    for league in leagues:
        rate_normal_str = request.form.get(f'rate_normal_{league.ID}', '').strip()
        rate_ntl_str = request.form.get(f'rate_ntl_{league.ID}', '').strip()

        # Parse values (empty string = None = use partner default)
        rate_normal = None
        rate_ntl = None
        try:
            if rate_normal_str:
                rate_normal = Decimal(rate_normal_str)
            if rate_ntl_str:
                rate_ntl = Decimal(rate_ntl_str)
        except InvalidOperation:
            flash(f'Invalid rate value for {league.display_name}', 'error')
            continue

        # Get or create rate record
        rate_record, created = PartnerLeagueRate.get_or_create(
            partner_id=partner.id,
            league_id=league.ID,
            org_season_id=None  # All seasons
        )

        # Check if anything changed
        old_normal = rate_record.rate_normal
        old_ntl = rate_record.rate_ntl

        if rate_normal != old_normal or rate_ntl != old_ntl:
            rate_record.rate_normal = rate_normal
            rate_record.rate_ntl = rate_ntl

            if created:
                db.session.add(rate_record)

            updated_count += 1
            anchor = f'league-{league.ID}'

    if updated_count > 0:
        db.session.commit()
        logger.info(f'Updated {updated_count} league rate(s) for partner {partner.name}')
        flash(f'Updated {updated_count} league rate(s)', 'success')
    else:
        flash('No changes made', 'info')

    redirect_url = url_for('umpires.partner_league_rates', id=id)
    if anchor:
        redirect_url += f'#{anchor}'
    return redirect(redirect_url)
