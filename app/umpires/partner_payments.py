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
from app.models.partner_payment import PartnerPaymentRecord, PartnerCredit
from app.models.league_season import LeagueSeason

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
    year = request.args.get('year', type=int)
    is_spring = request.args.get('is_spring', type=int)
    status = request.args.get('status')

    # Get prepay partners only
    partners = UmpirePartner.query.filter_by(
        active=True, prepays_invoices=True
    ).order_by(UmpirePartner.name).all()

    # Build query
    query = PartnerPaymentRecord.query

    # Filter to prepay partners only
    prepay_partner_ids = [p.id for p in partners]
    if prepay_partner_ids:
        query = query.filter(PartnerPaymentRecord.partner_id.in_(prepay_partner_ids))

    if partner_id:
        query = query.filter_by(partner_id=partner_id)
    if year:
        query = query.filter_by(year=year)
    if is_spring is not None:
        query = query.filter_by(is_spring=is_spring)
    if status:
        query = query.filter_by(status=status)

    payments = query.order_by(
        PartnerPaymentRecord.invoice_date.desc().nullsfirst(),
        PartnerPaymentRecord.created_at.desc()
    ).all()

    # Get available seasons for filter
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
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
        selected_year=year,
        selected_is_spring=is_spring,
        selected_status=status,
        can_edit=can_record_payments()
    )


@umpires_bp.route('/partner-payments/new', methods=['GET', 'POST'])
@login_required
@payment_edit_required
def new_partner_payment():
    """Create a new partner payment record."""
    partners = UmpirePartner.query.filter_by(
        active=True, prepays_invoices=True
    ).order_by(UmpirePartner.name).all()

    # Get available seasons
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    if request.method == 'POST':
        partner_id = request.form.get('partner_id', type=int)
        year = request.form.get('year', type=int)
        is_spring_str = request.form.get('is_spring')
        is_spring = is_spring_str == '1' if is_spring_str else None

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
                                   partners=partners, seasons=seasons, payment=None)

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
            year=year,
            is_spring=is_spring,
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
                           partners=partners, seasons=seasons, payment=None)


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
    partners = UmpirePartner.query.filter_by(
        active=True, prepays_invoices=True
    ).order_by(UmpirePartner.name).all()

    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            payment.partner_id = request.form.get('partner_id', type=int)
            payment.year = request.form.get('year', type=int)
            is_spring_str = request.form.get('is_spring')
            payment.is_spring = is_spring_str == '1' if is_spring_str else None

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

    # Get prepay partners
    partners = UmpirePartner.query.filter_by(
        active=True, prepays_invoices=True
    ).order_by(UmpirePartner.name).all()

    # Build query
    query = PartnerCredit.query

    prepay_partner_ids = [p.id for p in partners]
    if prepay_partner_ids:
        query = query.filter(PartnerCredit.partner_id.in_(prepay_partner_ids))

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
    partners = UmpirePartner.query.filter_by(
        active=True, prepays_invoices=True
    ).order_by(UmpirePartner.name).all()

    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    if request.method == 'POST':
        partner_id = request.form.get('partner_id', type=int)
        source_type = request.form.get('source_type', PartnerCredit.SOURCE_ADJUSTMENT)
        amount_str = request.form.get('amount', '').strip()
        umpire_games_str = request.form.get('umpire_games', '').strip()
        year = request.form.get('year', type=int)
        is_spring_str = request.form.get('is_spring')
        is_spring = is_spring_str == '1' if is_spring_str else None
        description = request.form.get('description', '').strip()

        if not partner_id or not amount_str:
            flash('Partner and amount are required.', 'error')
            return render_template('umpires/partner_credit_form.html',
                                   partners=partners, seasons=seasons)

        try:
            amount = Decimal(amount_str)
        except (ValueError, TypeError):
            flash('Invalid amount.', 'error')
            return render_template('umpires/partner_credit_form.html',
                                   partners=partners, seasons=seasons)

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
            season_year=year,
            season_is_spring=is_spring,
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
                           partners=partners, seasons=seasons)


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
