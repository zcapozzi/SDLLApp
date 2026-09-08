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
