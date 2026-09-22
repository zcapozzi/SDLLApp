"""Partner payment and credit management routes.

Handles:
- Recording payments to umpire partners
- Managing credits from postponed games
- Payment history and reconciliation

Access Control:
- Treasurer or admin can record payments
- Umpire coordinator, treasurer, or admin can view
"""

from datetime import datetime, date
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.umpire_partner import UmpirePartner
from app.models.umpire_profile import UmpireProfile
from app.models.partner_payment import PartnerPaymentRecord, PartnerCredit
from app.models.umpire_payment_event import UmpirePaymentEvent
from app.models.game import Game
from app.models.org_season import OrgSeason
from app.models.league import League

from . import umpires_bp, logger


def can_record_payments():
    """Check if current user can record payments."""
    return current_user.has_role('admin', 'treasurer')


def can_view_payments():
    """Check if current user can view payment records."""
    return current_user.has_role('admin', 'treasurer', 'umpire_coordinator')


def payment_view_required(f):
    """Decorator to require payment viewing permission."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not can_view_payments():
            flash('You do not have permission to view partner payments.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def payment_edit_required(f):
    """Decorator to require payment editing permission."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not can_record_payments():
            flash('You do not have permission to record partner payments.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@umpires_bp.route('/partner-payments')
@login_required
@payment_view_required
def partner_payments():
    """List all partner payment records."""
    # Get filter parameters
    partner_id = request.args.get('partner_id', type=int)
    org_season_id = request.args.get('org_season_id', type=int)
    status = request.args.get('status')

    # Get all active external partners (exclude league-managed like SDL)
    partners = UmpirePartner.query.filter(
        UmpirePartner.active == True,
        UmpirePartner.short_code != 'SDL'  # Exclude league-managed
    ).order_by(UmpirePartner.name).all()

    # Build query
    query = PartnerPaymentRecord.query

    # Filter to external partners only
    external_partner_ids = [p.id for p in partners]
    if external_partner_ids:
        query = query.filter(PartnerPaymentRecord.partner_id.in_(external_partner_ids))

    if partner_id:
        query = query.filter_by(partner_id=partner_id)
    if org_season_id:
        query = query.filter_by(org_season_id=org_season_id)
    if status:
        query = query.filter_by(status=status)

    # MySQL doesn't support NULLS FIRST, so use COALESCE workaround
    payments = query.order_by(
        db.func.coalesce(PartnerPaymentRecord.invoice_date, '9999-12-31').desc(),
        PartnerPaymentRecord.created_at.desc()
    ).all()

    # Get available seasons for filter
    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    # Calculate totals by partner
    partner_totals = {}
    for partner in partners:
        available_credit = PartnerCredit.get_total_available(partner.id)
        partner_totals[partner.id] = {
            'available_credit': available_credit
        }

    return render_template(
        'umpires/partner_payments.html',
        payments=payments,
        partners=partners,
        seasons=seasons,
        partner_totals=partner_totals,
        selected_partner_id=partner_id,
        selected_org_season_id=org_season_id,
        selected_status=status,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/partner-payments/new', methods=['GET', 'POST'])
@login_required
@payment_edit_required
def new_partner_payment():
    """Create a new partner payment record."""
    # Get all active external partners (exclude league-managed like SDL)
    partners = UmpirePartner.query.filter(
        UmpirePartner.active == True,
        UmpirePartner.short_code != 'SDL'  # Exclude league-managed
    ).order_by(UmpirePartner.name).all()

    # Get available seasons
    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    # Get current season for default selection
    current_season = OrgSeason.query.filter_by(org_id=1, is_current=1).first()

    if request.method == 'POST':
        partner_id = request.form.get('partner_id', type=int)
        org_season_id = request.form.get('org_season_id', type=int)

        invoice_number = request.form.get('invoice_number', '').strip()
        invoice_date_str = request.form.get('invoice_date')
        invoice_amount_str = request.form.get('invoice_amount', '').strip()

        calculated_games_str = request.form.get('calculated_games', '').strip()
        calculated_amount_str = request.form.get('calculated_amount', '').strip()

        notes = request.form.get('notes', '').strip()

        # Validate required fields
        if not partner_id:
            flash('Please select a partner.', 'error')
            return render_template('umpires/partner_payment_form.html',
                                   partners=partners, seasons=seasons, payment=None,
                                   current_season=current_season)

        # Parse dates and amounts
        invoice_date = None
        if invoice_date_str:
            try:
                invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        invoice_amount = None
        if invoice_amount_str:
            try:
                invoice_amount = Decimal(invoice_amount_str)
            except (ValueError, TypeError):
                pass

        calculated_games = None
        if calculated_games_str:
            try:
                calculated_games = int(calculated_games_str)
            except ValueError:
                pass

        calculated_amount = None
        if calculated_amount_str:
            try:
                calculated_amount = Decimal(calculated_amount_str)
            except (ValueError, TypeError):
                pass

        # Create payment record
        payment = PartnerPaymentRecord(
            partner_id=partner_id,
            org_season_id=org_season_id or None,
            invoice_number=invoice_number or None,
            invoice_date=invoice_date,
            invoice_amount=invoice_amount,
            calculated_games=calculated_games,
            calculated_amount=calculated_amount,
            notes=notes or None,
            status=PartnerPaymentRecord.STATUS_PENDING,
            created_by_user_id=current_user.ID
        )

        db.session.add(payment)
        db.session.commit()

        partner = UmpirePartner.query.get(partner_id)
        logger.info(f'Created payment record #{payment.id} for {partner.name}')
        flash(f'Created payment record for {partner.name}.', 'success')
        return redirect(url_for('umpires.view_partner_payment', id=payment.id))

    return render_template('umpires/partner_payment_form.html',
                           partners=partners, seasons=seasons, payment=None,
                           current_season=current_season)


@umpires_bp.route('/partner-payments/<int:id>')
@login_required
@payment_view_required
def view_partner_payment(id):
    """View a partner payment record."""
    payment = PartnerPaymentRecord.query.get_or_404(id)

    # Get available credits for this partner
    available_credits = PartnerCredit.get_available_for_partner(payment.partner_id)
    total_available = sum(c.amount for c in available_credits)

    # Get credits applied to this payment
    applied_credits = PartnerCredit.query.filter_by(
        applied_to_payment_id=payment.id
    ).all()

    return render_template(
        'umpires/partner_payment_detail.html',
        payment=payment,
        available_credits=available_credits,
        total_available=total_available,
        applied_credits=applied_credits,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/partner-payments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@payment_edit_required
def edit_partner_payment(id):
    """Edit a partner payment record."""
    payment = PartnerPaymentRecord.query.get_or_404(id)
    # Get all active external partners (exclude league-managed like SDL)
    partners = UmpirePartner.query.filter(
        UmpirePartner.active == True,
        UmpirePartner.short_code != 'SDL'  # Exclude league-managed
    ).order_by(UmpirePartner.name).all()

    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            payment.partner_id = request.form.get('partner_id', type=int)
            payment.org_season_id = request.form.get('org_season_id', type=int) or None

            payment.invoice_number = request.form.get('invoice_number', '').strip() or None
            invoice_date_str = request.form.get('invoice_date')
            if invoice_date_str:
                try:
                    payment.invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                payment.invoice_date = None

            invoice_amount_str = request.form.get('invoice_amount', '').strip()
            if invoice_amount_str:
                try:
                    payment.invoice_amount = Decimal(invoice_amount_str)
                except (ValueError, TypeError):
                    pass

            calculated_games_str = request.form.get('calculated_games', '').strip()
            if calculated_games_str:
                try:
                    payment.calculated_games = int(calculated_games_str)
                except ValueError:
                    pass

            calculated_amount_str = request.form.get('calculated_amount', '').strip()
            if calculated_amount_str:
                try:
                    payment.calculated_amount = Decimal(calculated_amount_str)
                except (ValueError, TypeError):
                    pass

            payment.notes = request.form.get('notes', '').strip() or None

            db.session.commit()
            logger.info(f'Updated payment record #{payment.id}')
            flash('Payment record updated.', 'success')
            return redirect(url_for('umpires.view_partner_payment', id=payment.id))

        elif action == 'void':
            if payment.status != PartnerPaymentRecord.STATUS_VOID:
                payment.status = PartnerPaymentRecord.STATUS_VOID
                db.session.commit()
                logger.info(f'Voided payment record #{payment.id}')
                flash('Payment record voided.', 'success')
            return redirect(url_for('umpires.partner_payments'))

    return render_template('umpires/partner_payment_form.html',
                           partners=partners, seasons=seasons, payment=payment)


@umpires_bp.route('/partner-payments/<int:id>/mark-paid', methods=['POST'])
@login_required
@payment_edit_required
def mark_payment_paid(id):
    """Mark a payment as paid."""
    payment = PartnerPaymentRecord.query.get_or_404(id)

    if payment.status == PartnerPaymentRecord.STATUS_VOID:
        flash('Cannot mark a voided payment as paid.', 'error')
        return redirect(url_for('umpires.view_partner_payment', id=id))

    paid_amount_str = request.form.get('paid_amount', '').strip()
    payment_date_str = request.form.get('payment_date')
    payment_method = request.form.get('payment_method', '').strip()
    payment_reference = request.form.get('payment_reference', '').strip()

    if paid_amount_str:
        try:
            payment.paid_amount = Decimal(paid_amount_str)
        except (ValueError, TypeError):
            flash('Invalid payment amount.', 'error')
            return redirect(url_for('umpires.view_partner_payment', id=id))
    else:
        # Default to invoice amount
        payment.paid_amount = payment.invoice_amount

    if payment_date_str:
        try:
            payment.payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except ValueError:
            payment.payment_date = date.today()
    else:
        payment.payment_date = date.today()

    payment.payment_method = payment_method or None
    payment.payment_reference = payment_reference or None
    payment.status = PartnerPaymentRecord.STATUS_PAID
    payment.paid_by_user_id = current_user.ID

    db.session.commit()

    logger.info(f'Marked payment #{payment.id} as paid: ${payment.paid_amount}')
    flash(f'Payment marked as paid: ${payment.paid_amount:.2f}', 'success')
    return redirect(url_for('umpires.view_partner_payment', id=id))


# Credit Management Routes

@umpires_bp.route('/partner-credits')
@login_required
@payment_view_required
def partner_credits():
    """List all partner credits."""
    partner_id = request.args.get('partner_id', type=int)
    status = request.args.get('status')

    # Get all active external partners (exclude league-managed like SDL)
    partners = UmpirePartner.query.filter(
        UmpirePartner.active == True,
        UmpirePartner.short_code != 'SDL'  # Exclude league-managed
    ).order_by(UmpirePartner.name).all()

    # Build query
    query = PartnerCredit.query

    external_partner_ids = [p.id for p in partners]
    if external_partner_ids:
        query = query.filter(PartnerCredit.partner_id.in_(external_partner_ids))

    if partner_id:
        query = query.filter_by(partner_id=partner_id)
    if status:
        query = query.filter_by(status=status)

    credits = query.order_by(PartnerCredit.created_at.desc()).all()

    # Calculate totals by partner
    partner_totals = {}
    for partner in partners:
        available = PartnerCredit.get_total_available(partner.id)
        partner_totals[partner.id] = {'available': available}

    return render_template(
        'umpires/partner_credits.html',
        credits=credits,
        partners=partners,
        partner_totals=partner_totals,
        selected_partner_id=partner_id,
        selected_status=status,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/partner-credits/new', methods=['GET', 'POST'])
@login_required
@payment_edit_required
def new_partner_credit():
    """Create a manual credit adjustment."""
    # Get all active external partners (exclude league-managed like SDL)
    partners = UmpirePartner.query.filter(
        UmpirePartner.active == True,
        UmpirePartner.short_code != 'SDL'  # Exclude league-managed
    ).order_by(UmpirePartner.name).all()

    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    # Get current season for default selection
    current_season = OrgSeason.query.filter_by(org_id=1, is_current=1).first()

    if request.method == 'POST':
        partner_id = request.form.get('partner_id', type=int)
        source_type = request.form.get('source_type', PartnerCredit.SOURCE_ADJUSTMENT)
        amount_str = request.form.get('amount', '').strip()
        umpire_games_str = request.form.get('umpire_games', '').strip()
        org_season_id = request.form.get('org_season_id', type=int)
        description = request.form.get('description', '').strip()

        if not partner_id or not amount_str:
            flash('Partner and amount are required.', 'error')
            return render_template('umpires/partner_credit_form.html',
                                   partners=partners, seasons=seasons,
                                   current_season=current_season)

        try:
            amount = Decimal(amount_str)
        except (ValueError, TypeError):
            flash('Invalid amount.', 'error')
            return render_template('umpires/partner_credit_form.html',
                                   partners=partners, seasons=seasons,
                                   current_season=current_season)

        umpire_games = None
        if umpire_games_str:
            try:
                umpire_games = int(umpire_games_str)
            except ValueError:
                pass

        credit = PartnerCredit(
            partner_id=partner_id,
            source_type=source_type,
            amount=amount,
            umpire_games=umpire_games,
            org_season_id=org_season_id or None,
            description=description or None,
            created_by_user_id=current_user.ID
        )

        db.session.add(credit)
        db.session.commit()

        partner = UmpirePartner.query.get(partner_id)
        logger.info(f'Created credit #{credit.id} for {partner.name}: ${amount}')
        flash(f'Created credit for {partner.name}: ${amount:.2f}', 'success')
        return redirect(url_for('umpires.partner_credits'))

    return render_template('umpires/partner_credit_form.html',
                           partners=partners, seasons=seasons,
                           current_season=current_season)


@umpires_bp.route('/partner-credits/<int:id>/apply', methods=['POST'])
@login_required
@payment_edit_required
def apply_partner_credit(id):
    """Apply a credit to a payment."""
    credit = PartnerCredit.query.get_or_404(id)
    payment_id = request.form.get('payment_id', type=int)

    if not payment_id:
        flash('Please select a payment to apply the credit to.', 'error')
        return redirect(url_for('umpires.partner_credits'))

    payment = PartnerPaymentRecord.query.get_or_404(payment_id)

    if not credit.is_available:
        flash(f'Credit is not available (status: {credit.status}).', 'error')
        return redirect(url_for('umpires.partner_credits'))

    if credit.partner_id != payment.partner_id:
        flash('Credit and payment must be for the same partner.', 'error')
        return redirect(url_for('umpires.partner_credits'))

    # Apply credit
    credit.apply_to_payment(payment)
    db.session.commit()

    logger.info(f'Applied credit #{credit.id} (${credit.amount}) to payment #{payment.id}')
    flash(f'Applied credit of ${credit.amount:.2f} to payment #{payment.id}.', 'success')
    return redirect(url_for('umpires.view_partner_payment', id=payment.id))


@umpires_bp.route('/partner-credits/<int:id>/void', methods=['POST'])
@login_required
@payment_edit_required
def void_partner_credit(id):
    """Void a credit."""
    credit = PartnerCredit.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()

    if credit.status == PartnerCredit.STATUS_APPLIED:
        flash('Cannot void a credit that has been applied.', 'error')
        return redirect(url_for('umpires.partner_credits'))

    credit.void(reason)
    db.session.commit()

    logger.info(f'Voided credit #{credit.id}')
    flash('Credit voided.', 'success')
    return redirect(url_for('umpires.partner_credits'))


# =============================================================================
# Umpire Payment Events - Standalone payment tracking (rainouts, bonuses, etc.)
# =============================================================================

@umpires_bp.route('/payment-events')
@login_required
@payment_view_required
def payment_events():
    """List all umpire payment events."""
    # Get filter parameters
    status = request.args.get('status')
    event_type = request.args.get('event_type')
    payee_type = request.args.get('payee_type')
    org_season_id = request.args.get('org_season_id', type=int)

    # Build query
    query = UmpirePaymentEvent.query

    if status:
        query = query.filter_by(status=status)
    if event_type:
        query = query.filter_by(event_type=event_type)
    if payee_type == 'umpire':
        query = query.filter(UmpirePaymentEvent.umpire_profile_id.isnot(None))
    elif payee_type == 'partner':
        query = query.filter(UmpirePaymentEvent.partner_id.isnot(None))
    if org_season_id:
        query = query.filter_by(org_season_id=org_season_id)

    events = query.order_by(UmpirePaymentEvent.original_date.desc()).all()

    # Get seasons and partners for filters
    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    # Calculate summary stats
    pending_count = sum(1 for e in events if e.is_pending)
    pending_amount = sum(e.amount for e in events if e.is_pending)
    approved_count = sum(1 for e in events if e.is_approved)
    approved_amount = sum(e.amount for e in events if e.is_approved)

    return render_template(
        'umpires/payment_events.html',
        events=events,
        seasons=seasons,
        event_types=UmpirePaymentEvent.EVENT_TYPES,
        event_type_labels=UmpirePaymentEvent.EVENT_TYPE_LABELS,
        statuses=UmpirePaymentEvent.STATUSES,
        status_labels=UmpirePaymentEvent.STATUS_LABELS,
        selected_status=status,
        selected_event_type=event_type,
        selected_payee_type=payee_type,
        selected_org_season_id=org_season_id,
        pending_count=pending_count,
        pending_amount=pending_amount,
        approved_count=approved_count,
        approved_amount=approved_amount,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/payment-events/new', methods=['GET', 'POST'])
@login_required
@payment_edit_required
def new_payment_event():
    """Create a new payment event manually."""
    # Get partners (for partner payments)
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    # Get managed partner (SDL Academy) for getting umpires
    managed_partner = UmpirePartner.query.filter_by(is_managed_by_org=True).first()

    # Get umpires (for individual umpire payments)
    umpires = []
    if managed_partner:
        umpires = UmpireProfile.query.filter_by(
            partner_id=managed_partner.id,
            status='active'
        ).order_by(UmpireProfile.last_name, UmpireProfile.first_name).all()

    # Get seasons
    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()
    current_season = OrgSeason.query.filter_by(org_id=1, is_current=1).first()

    # Get leagues for rate lookup
    leagues = League.get_all_active()

    if request.method == 'POST':
        event_type = request.form.get('event_type')
        payee_type = request.form.get('payee_type')

        # Get payee
        umpire_profile_id = None
        partner_id = None
        if payee_type == 'umpire':
            umpire_profile_id = request.form.get('umpire_profile_id', type=int)
        else:
            partner_id = request.form.get('partner_id', type=int)

        # Get game info
        original_date_str = request.form.get('original_date')
        original_time_str = request.form.get('original_time')
        original_league = request.form.get('original_league', '').strip()
        original_field_name = request.form.get('original_field_name', '').strip()

        # Parse date/time
        original_date = None
        original_time = None
        if original_date_str:
            try:
                original_date = datetime.strptime(original_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'error')
                return redirect(url_for('umpires.new_payment_event'))

        if original_time_str:
            try:
                original_time = datetime.strptime(original_time_str, '%H:%M').time()
            except ValueError:
                pass

        # Get payment details
        amount_str = request.form.get('amount', '').strip()
        reason = request.form.get('reason', '').strip()
        notes = request.form.get('notes', '').strip()
        org_season_id = request.form.get('org_season_id', type=int)

        if not original_date or not amount_str:
            flash('Date and amount are required.', 'error')
            return redirect(url_for('umpires.new_payment_event'))

        try:
            amount = Decimal(amount_str)
        except (ValueError, TypeError):
            flash('Invalid amount.', 'error')
            return redirect(url_for('umpires.new_payment_event'))

        # Create event
        event = UmpirePaymentEvent(
            event_type=event_type,
            original_date=original_date,
            original_time=original_time,
            original_league=original_league or None,
            original_field_name=original_field_name or None,
            umpire_profile_id=umpire_profile_id,
            partner_id=partner_id,
            amount=amount,
            reason=reason or None,
            notes=notes or None,
            org_season_id=org_season_id or None,
            created_by_user_id=current_user.ID,
            status=UmpirePaymentEvent.STATUS_PENDING
        )

        db.session.add(event)
        db.session.commit()

        logger.info(f'Created payment event #{event.id}: {event.event_type_label} ${amount}')
        flash(f'Created payment event: {event.event_type_label} ${amount:.2f}', 'success')
        return redirect(url_for('umpires.view_payment_event', id=event.id))

    return render_template(
        'umpires/payment_event_form.html',
        partners=partners,
        umpires=umpires,
        seasons=seasons,
        leagues=leagues,
        current_season=current_season,
        event_types=UmpirePaymentEvent.EVENT_TYPES,
        event_type_labels=UmpirePaymentEvent.EVENT_TYPE_LABELS,
        event=None
    )


@umpires_bp.route('/payment-events/<int:id>')
@login_required
@payment_view_required
def view_payment_event(id):
    """View a payment event."""
    event = UmpirePaymentEvent.query.get_or_404(id)

    return render_template(
        'umpires/payment_event_detail.html',
        event=event,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/payment-events/<int:id>/approve', methods=['POST'])
@login_required
@payment_edit_required
def approve_payment_event(id):
    """Approve a pending payment event."""
    event = UmpirePaymentEvent.query.get_or_404(id)

    if not event.is_pending:
        flash(f'Cannot approve event in status {event.status_label}.', 'error')
        return redirect(url_for('umpires.view_payment_event', id=id))

    event.approve(current_user.ID)
    db.session.commit()

    logger.info(f'Approved payment event #{event.id}')
    flash('Payment event approved.', 'success')
    return redirect(url_for('umpires.view_payment_event', id=id))


@umpires_bp.route('/payment-events/<int:id>/mark-paid', methods=['POST'])
@login_required
@payment_edit_required
def mark_payment_event_paid(id):
    """Mark a payment event as paid."""
    event = UmpirePaymentEvent.query.get_or_404(id)

    if event.is_voided:
        flash('Cannot mark a voided event as paid.', 'error')
        return redirect(url_for('umpires.view_payment_event', id=id))

    if event.is_paid:
        flash('Event is already marked as paid.', 'info')
        return redirect(url_for('umpires.view_payment_event', id=id))

    event.mark_paid(current_user.ID)
    db.session.commit()

    logger.info(f'Marked payment event #{event.id} as paid')
    flash('Payment event marked as paid.', 'success')
    return redirect(url_for('umpires.view_payment_event', id=id))


@umpires_bp.route('/payment-events/<int:id>/void', methods=['POST'])
@login_required
@payment_edit_required
def void_payment_event(id):
    """Void a payment event."""
    event = UmpirePaymentEvent.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()

    if event.is_voided:
        flash('Event is already voided.', 'info')
        return redirect(url_for('umpires.view_payment_event', id=id))

    event.void(current_user.ID, reason)
    db.session.commit()

    logger.info(f'Voided payment event #{event.id}')
    flash('Payment event voided.', 'success')
    return redirect(url_for('umpires.payment_events'))


# =============================================================================
# Managed Umpire Invoice Report
# =============================================================================

@umpires_bp.route('/managed-invoice')
@login_required
@payment_view_required
def managed_umpire_invoice():
    """Invoice report for SDL umpires - what's owed to each managed umpire."""
    # Get season filter
    org_season_id = request.args.get('org_season_id', type=int)
    status_filter = request.args.get('status', 'pending')  # pending, all

    # Get current season if not specified
    if not org_season_id:
        current_season = OrgSeason.query.filter_by(org_id=1, is_current=1).first()
        if current_season:
            org_season_id = current_season.ID

    # Get managed partner (SDL Academy)
    managed_partner = UmpirePartner.query.filter_by(is_managed_by_org=True).first()
    if not managed_partner:
        flash('No managed umpire partner configured.', 'error')
        return redirect(url_for('umpires.partner_payments'))

    # Get all active umpires for this partner
    umpires = UmpireProfile.query.filter_by(
        partner_id=managed_partner.id,
        status='active'
    ).order_by(UmpireProfile.last_name, UmpireProfile.first_name).all()

    # Build invoice data per umpire
    invoice_data = []
    for umpire in umpires:
        # Get payment events for this umpire
        query = UmpirePaymentEvent.query.filter_by(umpire_profile_id=umpire.id)

        if org_season_id:
            query = query.filter_by(org_season_id=org_season_id)

        if status_filter == 'pending':
            query = query.filter(UmpirePaymentEvent.status.in_([
                UmpirePaymentEvent.STATUS_PENDING,
                UmpirePaymentEvent.STATUS_APPROVED
            ]))
        else:
            query = query.filter(UmpirePaymentEvent.status != UmpirePaymentEvent.STATUS_VOIDED)

        events = query.order_by(UmpirePaymentEvent.original_date.desc()).all()

        if events:
            total_amount = sum(e.amount for e in events)
            pending_amount = sum(e.amount for e in events if e.is_pending)
            approved_amount = sum(e.amount for e in events if e.is_approved)
            paid_amount = sum(e.amount for e in events if e.is_paid)

            invoice_data.append({
                'umpire': umpire,
                'events': events,
                'event_count': len(events),
                'total_amount': total_amount,
                'pending_amount': pending_amount,
                'approved_amount': approved_amount,
                'paid_amount': paid_amount,
                'unpaid_amount': pending_amount + approved_amount,
            })

    # Calculate grand totals
    grand_total = sum(d['total_amount'] for d in invoice_data)
    grand_pending = sum(d['pending_amount'] for d in invoice_data)
    grand_approved = sum(d['approved_amount'] for d in invoice_data)
    grand_paid = sum(d['paid_amount'] for d in invoice_data)

    # Get seasons for filter
    seasons = OrgSeason.query.filter_by(org_id=1).order_by(
        OrgSeason.year.desc(), OrgSeason.is_spring.desc()
    ).all()

    return render_template(
        'umpires/managed_umpire_invoice.html',
        invoice_data=invoice_data,
        seasons=seasons,
        selected_org_season_id=org_season_id,
        selected_status=status_filter,
        grand_total=grand_total,
        grand_pending=grand_pending,
        grand_approved=grand_approved,
        grand_paid=grand_paid,
        managed_partner=managed_partner,
        can_edit=can_record_payments()
    )
