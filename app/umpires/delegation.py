"""Umpire delegation rules and reporting routes.

Handles:
- Viewing delegation rules by league
- Editing delegation percentages
- Managing override keywords
- Delegation cost reports
- Partner rate management
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.umpire_partner import UmpirePartner
from app.models.umpire_delegation import UmpireDelegationRule, UmpireDelegationOverride
from app.models.league import League
from app.models.game import Game

from . import umpires_bp, umpire_coordinator_required, logger


@umpires_bp.route('/delegation')
@login_required
@umpire_coordinator_required
def delegation():
    """View delegation rules for all leagues."""
    all_leagues = League.get_all_active()
    rules = {}

    # Separate leagues with umpires from those without
    leagues_with_umpires = []
    leagues_no_umpires = []

    for league in all_leagues:
        rule = UmpireDelegationRule.get_for_league(league.ID)
        if rule:
            rules[league.ID] = rule

        if league.needs_umpires:
            leagues_with_umpires.append(league)
        else:
            leagues_no_umpires.append(league)

    # Get partners for reference
    partners = UmpirePartner.get_active()

    return render_template(
        'umpires/delegation.html',
        leagues=leagues_with_umpires,
        leagues_no_umpires=leagues_no_umpires,
        rules=rules,
        partners=partners
    )


@umpires_bp.route('/delegation/<int:league_id>', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def edit_delegation(league_id):
    """Edit delegation percentages for a league."""
    league = League.query.get_or_404(league_id)
    rule = UmpireDelegationRule.get_for_league(league_id)
    partners = UmpirePartner.get_active()

    if request.method == 'POST':
        # Get each partner's percentage dynamically
        partner_pcts = {}
        for partner in partners:
            pct = int(request.form.get(f'partner_{partner.id}_pct', 0))
            partner_pcts[partner.id] = pct

        # Validate percentages sum to 100
        total = sum(partner_pcts.values())
        if total != 100:
            flash(f'Percentages must sum to 100 (currently {total})', 'error')
            return render_template('umpires/edit_delegation.html',
                                   league=league, rule=rule, partners=partners)

        # Create rule if it doesn't exist
        if not rule:
            rule = UmpireDelegationRule(
                org_id=1,
                league_id=league_id,
                active=True
            )
            db.session.add(rule)
            db.session.flush()  # Get rule.id

        # Update allocations for each partner
        for partner_id, pct in partner_pcts.items():
            rule.set_allocation(partner_id, pct)

        # Clean up zero allocations
        rule.remove_zero_allocations()

        db.session.commit()

        # Log allocation summary
        alloc_summary = '/'.join(f'{p.short_code}:{partner_pcts[p.id]}'
                                 for p in partners if partner_pcts.get(p.id, 0) > 0)
        logger.info(f'Updated delegation for {league.display_name}: {alloc_summary}')
        flash(f'Updated delegation rules for {league.display_name}', 'success')
        return redirect(url_for('umpires.delegation'))

    return render_template('umpires/edit_delegation.html',
                           league=league, rule=rule, partners=partners)


@umpires_bp.route('/delegation/overrides')
@login_required
@umpire_coordinator_required
def overrides():
    """View delegation override keywords."""
    overrides = UmpireDelegationOverride.get_active()
    partners = UmpirePartner.get_active()
    return render_template('umpires/overrides.html', overrides=overrides, partners=partners)


@umpires_bp.route('/delegation/overrides/add', methods=['POST'])
@login_required
@umpire_coordinator_required
def add_override():
    """Add a new override keyword."""
    keyword = request.form.get('keyword', '').strip()
    target_type = request.form.get('target_type', 'academy')
    partner_id = request.form.get('partner_id')
    description = request.form.get('description', '').strip()

    if not keyword:
        flash('Keyword is required.', 'error')
        return redirect(url_for('umpires.overrides'))

    # Check for duplicate
    existing = UmpireDelegationOverride.query.filter_by(org_id=1, keyword=keyword).first()
    if existing:
        flash(f'Override for "{keyword}" already exists.', 'error')
        return redirect(url_for('umpires.overrides'))

    override = UmpireDelegationOverride(
        org_id=1,
        keyword=keyword,
        target_type=target_type,
        partner_id=int(partner_id) if partner_id and target_type == 'partner' else None,
        description=description or None,
        active=True
    )

    db.session.add(override)
    db.session.commit()

    logger.info(f'Added override: {keyword} -> {target_type}')
    flash(f'Added override: {keyword}', 'success')
    return redirect(url_for('umpires.overrides'))


@umpires_bp.route('/delegation/overrides/<int:id>/delete', methods=['POST'])
@login_required
@umpire_coordinator_required
def delete_override(id):
    """Delete an override keyword."""
    override = UmpireDelegationOverride.query.get_or_404(id)
    keyword = override.keyword

    override.active = False
    db.session.commit()

    logger.info(f'Deleted override: {keyword}')
    flash(f'Deleted override: {keyword}', 'success')
    return redirect(url_for('umpires.overrides'))


@umpires_bp.route('/delegation/report')
@umpires_bp.route('/delegation/report/<int:year>/<int:is_spring>')
@login_required
def delegation_report(year=None, is_spring=None):
    """
    Report showing game counts and costs by umpire partner and league.

    Access: Umpire coordinators, admins, and treasurers can view this report.

    Shows:
    - Game counts by league and partner (SDL, DIA, DYN, etc.)
    - Cost calculations based on per-game rates
    - Blended rates per league
    - Accounts for 1-umpire vs 2-umpire games
    """
    from flask_login import current_user
    if not (current_user.can_manage_umpires() or current_user.is_treasurer()):
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('main.dashboard'))

    from app.models.league_season import LeagueSeason

    # Default to current season
    if year is None:
        current = LeagueSeason.query.filter_by(active=1).order_by(
            LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
        ).first()
        if current:
            year = current.year
            is_spring = 1 if current.is_spring else 0
        else:
            year = date.today().year
            is_spring = 1 if date.today().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get all partners including SDL
    partners = UmpirePartner.query.filter_by(active=True).all()
    partner_lookup = {p.short_code: p for p in partners}

    # Get all leagues with umpire counts
    # Build lookup by both display_name and fall_display_name (case-insensitive)
    leagues = League.get_all_active()
    league_lookup = {}
    for l in leagues:
        league_lookup[l.display_name.lower().strip()] = l
        if l.fall_display_name:
            league_lookup[l.fall_display_name.lower().strip()] = l

    # Get games for this season (include scrimmages - we pay for those umpires too)
    # Exclude cancelled and postponed games - we don't pay for those
    # Postponed games will show up again with their rescheduled date
    games = Game.query.filter(
        Game.year == year,
        Game.is_spring == (is_spring == 1),
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage']),
        ~Game.status.in_(['cancelled', 'postponed'])
    ).all()

    # Build summary data structure
    # {partner_code: {league: {games: N, ntl_games: N, umpires: N, ntl_umpires: N}}}
    summary = {}

    # Initialize with all partners + SDL
    partner_codes = ['SDL'] + [p.short_code for p in partners if p.short_code != 'SDL']
    for code in partner_codes:
        summary[code] = {}

    for game in games:
        league_name = game.league or 'Unknown'

        # Skip games without an umpire partner assigned (we're not paying anyone)
        if not game.umpire_override:
            continue

        # Skip games that were unassigned (assigned in error, no umpire needed)
        if game.umpire_was_unassigned:
            continue

        # Get umpire count for this game (case-insensitive lookup)
        league_obj = league_lookup.get(league_name.lower().strip())
        if game.umpire_count_override is not None:
            umpire_count = game.umpire_count_override
        elif league_obj:
            is_playoff = game.game_type == 'playoff'
            umpire_count = league_obj.get_umpire_count(is_playoff=is_playoff)
        else:
            umpire_count = 1

        # If umpire_override is set, we're paying for at least 1 umpire
        if umpire_count == 0:
            umpire_count = 1

        partner_code = game.umpire_override.upper() if game.umpire_override else None
        if not partner_code:
            continue
        if partner_code not in summary:
            summary[partner_code] = {}

        if league_name not in summary[partner_code]:
            summary[partner_code][league_name] = {
                'games': 0,
                'ntl_games': 0,
                'umpires': 0,
                'ntl_umpires': 0
            }

        # Tally
        if game.no_time_limit:
            summary[partner_code][league_name]['ntl_games'] += 1
            summary[partner_code][league_name]['ntl_umpires'] += umpire_count
        else:
            summary[partner_code][league_name]['games'] += 1
            summary[partner_code][league_name]['umpires'] += umpire_count

    # Calculate costs using new rate structure
    # Partners can have:
    # - Per-umpire rates (is_flat_rate=False): cost = umpires * rate + games * booking_fee
    # - Flat rates (is_flat_rate=True): cost = games * rate + games * booking_fee
    # Plus optional per-season booking fee

    # Default rates for SDL (internal umpires)
    default_rate_normal = 35.00
    default_rate_ntl = 50.00

    # Calculate totals and costs
    report_data = []
    grand_totals = {
        'games': 0, 'ntl_games': 0, 'umpires': 0, 'ntl_umpires': 0,
        'cost_umpires': 0, 'cost_booking': 0, 'cost_season': 0, 'cost_total': 0
    }

    for partner_code in partner_codes:
        if partner_code not in summary:
            continue

        partner_obj = partner_lookup.get(partner_code)
        partner_name = partner_obj.name if partner_obj else ('SDLL Academy' if partner_code == 'SDL' else partner_code)

        # Get rate info from partner object
        if partner_obj:
            rate_normal = float(partner_obj.rate_normal or default_rate_normal)
            rate_ntl = float(partner_obj.rate_ntl or rate_normal)
            is_flat_rate = partner_obj.is_flat_rate
            booking_fee_per_game = float(partner_obj.booking_fee_per_game or 0)
            booking_fee_per_season = float(partner_obj.booking_fee_per_season or 0)
            rate_description = partner_obj.get_rate_description()
        else:
            # SDL defaults
            rate_normal = default_rate_normal
            rate_ntl = default_rate_ntl
            is_flat_rate = False
            booking_fee_per_game = 0
            booking_fee_per_season = 0
            rate_description = f"${rate_normal}/umpire"

        partner_totals = {
            'games': 0, 'ntl_games': 0, 'umpires': 0, 'ntl_umpires': 0,
            'cost_umpires': 0, 'cost_booking': 0, 'cost_total': 0
        }

        league_rows = []
        for league_name, data in sorted(summary[partner_code].items()):
            # Calculate umpire/game costs based on rate type
            if is_flat_rate:
                # Flat rate: cost per game regardless of umpire count
                cost_normal_umpires = data['games'] * rate_normal
                cost_ntl_umpires = data['ntl_games'] * rate_ntl
            else:
                # Per-umpire rate
                cost_normal_umpires = data['umpires'] * rate_normal
                cost_ntl_umpires = data['ntl_umpires'] * rate_ntl

            cost_umpires = cost_normal_umpires + cost_ntl_umpires

            # Per-game booking fee applies to all games
            total_games = data['games'] + data['ntl_games']
            cost_booking = total_games * booking_fee_per_game

            cost_total = cost_umpires + cost_booking

            league_rows.append({
                'league': league_name,
                'games': data['games'],
                'ntl_games': data['ntl_games'],
                'umpires': data['umpires'],
                'ntl_umpires': data['ntl_umpires'],
                'cost_umpires': cost_umpires,
                'cost_booking': cost_booking,
                'cost_total': cost_total
            })

            partner_totals['games'] += data['games']
            partner_totals['ntl_games'] += data['ntl_games']
            partner_totals['umpires'] += data['umpires']
            partner_totals['ntl_umpires'] += data['ntl_umpires']
            partner_totals['cost_umpires'] += cost_umpires
            partner_totals['cost_booking'] += cost_booking
            partner_totals['cost_total'] += cost_total

        # Add per-season booking fee to partner total
        partner_totals['cost_season'] = booking_fee_per_season
        partner_totals['cost_total'] += booking_fee_per_season

        # Calculate blended rate (total cost / total games)
        total_games = partner_totals['games'] + partner_totals['ntl_games']
        blended_rate = partner_totals['cost_total'] / total_games if total_games > 0 else 0

        report_data.append({
            'code': partner_code,
            'name': partner_name,
            'rate_normal': rate_normal,
            'rate_ntl': rate_ntl,
            'is_flat_rate': is_flat_rate,
            'booking_fee_per_game': booking_fee_per_game,
            'booking_fee_per_season': booking_fee_per_season,
            'rate_description': rate_description,
            'leagues': league_rows,
            'totals': partner_totals,
            'blended_rate': blended_rate
        })

        grand_totals['games'] += partner_totals['games']
        grand_totals['ntl_games'] += partner_totals['ntl_games']
        grand_totals['umpires'] += partner_totals['umpires']
        grand_totals['ntl_umpires'] += partner_totals['ntl_umpires']
        grand_totals['cost_umpires'] += partner_totals['cost_umpires']
        grand_totals['cost_booking'] += partner_totals['cost_booking']
        grand_totals['cost_season'] += partner_totals.get('cost_season', 0)
        grand_totals['cost_total'] += partner_totals['cost_total']

    # Get available seasons for picker
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    # Build prepay partner reconciliation data
    # Wrapped in try/except in case the payment tables haven't been migrated yet
    prepay_reconciliation = {}
    try:
        from app.models.partner_payment import PartnerPaymentRecord, PartnerCredit
        from app.models.org_season import OrgSeason

        # Look up the org_season_id for this year/is_spring
        org_season = OrgSeason.query.filter_by(
            year=year,
            is_spring=1 if is_spring else 0
        ).first()
        org_season_id = org_season.ID if org_season else None

        for partner in partners:
            if not partner.prepays_invoices:
                continue

            # Get payment totals for this season
            payment_totals = PartnerPaymentRecord.get_season_totals(
                partner.id, org_season_id
            )

            # Get postponed credits for this season
            postponed_credits = PartnerCredit.get_for_season(
                partner.id, org_season_id
            ) if org_season_id else []
            postponed_amount = sum(c.amount for c in postponed_credits if c.source_type == 'postponed_game')
            postponed_games = sum(c.umpire_games or 0 for c in postponed_credits if c.source_type == 'postponed_game')

            # Get available credits
            available_credits = PartnerCredit.get_total_available(partner.id)

            # Get games used from report_data
            partner_report = next((p for p in report_data if p['code'] == partner.short_code), None)
            games_used = 0
            cost_used = Decimal('0')
            if partner_report:
                games_used = partner_report['totals']['umpires'] + partner_report['totals']['ntl_umpires']
                cost_used = Decimal(str(partner_report['totals']['cost_total']))

            # Ensure all monetary values are Decimal for consistent arithmetic
            prepay_reconciliation[partner.id] = {
                'partner': partner,
                'payments_total': Decimal(str(payment_totals['total_paid'] or 0)),
                'payments_games': payment_totals['total_games'],
                'games_used': games_used,
                'cost_used': cost_used,
                'postponed_amount': Decimal(str(postponed_amount or 0)),
                'postponed_games': postponed_games,
                'available_credits': Decimal(str(available_credits or 0)),
                'payment_count': payment_totals['record_count']
            }
    except Exception as e:
        # Payment tables may not be migrated yet - skip prepay reconciliation
        logger.warning(f'Could not load prepay reconciliation data: {e}')

    return render_template(
        'umpires/delegation_report.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        seasons=seasons,
        report_data=report_data,
        grand_totals=grand_totals,
        partners=partners,
        prepay_reconciliation=prepay_reconciliation
    )


@umpires_bp.route('/delegation/invoice-tieout')
def invoice_tieout():
    """Invoice Tie-Out report for matching partner invoices.

    Access control:
    - Not logged in: Landing page with login link
    - Logged in without permission: Redirect with error
    - Logged in with permission: Full report

    Shows game-level detail for a specific partner and date range.
    Access: Umpire coordinators, admins, and treasurers.
    """
    from flask_login import current_user
    from datetime import datetime, timedelta

    # Check authentication - show landing page if not logged in
    if not current_user.is_authenticated:
        login_url = url_for('auth.login', next=request.url)
        return render_template(
            'treasurer/landing.html',
            page_title='Invoice Tie-Outs',
            description='Please log in to view the Invoice Tie-Outs report. This page helps match partner invoices against game records.',
            login_url=login_url
        )

    # Check authorization
    if not (current_user.can_manage_umpires() or current_user.is_treasurer()):
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get all active partners
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    # Get filter parameters
    partner_code = request.args.get('partner', '')
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')

    # Default to past 7 days if no dates specified
    today = date.today()
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = today
    else:
        end_date = today

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = end_date - timedelta(days=6)
    else:
        start_date = end_date - timedelta(days=6)

    # Build lookup for leagues (for umpire counts)
    leagues = League.get_all_active()
    league_lookup = {}
    for l in leagues:
        league_lookup[l.display_name.lower().strip()] = l
        if l.fall_display_name:
            league_lookup[l.fall_display_name.lower().strip()] = l

    # Query games in date range
    # Exclude cancelled and postponed games - we don't pay for those
    games_query = Game.query.filter(
        Game.game_date >= start_date,
        Game.game_date <= end_date,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage']),
        ~Game.status.in_(['cancelled', 'postponed'])
    )

    # Filter by partner if specified
    if partner_code:
        games_query = games_query.filter(
            db.func.upper(Game.umpire_override) == partner_code.upper()
        )

    games = games_query.order_by(Game.game_date).all()

    # Build partner lookup for rate calculation
    partner_objs = {p.short_code: p for p in partners}
    partner_names = {p.short_code: p.name for p in partners}
    partner_names['SDL'] = 'SDLL Academy'

    # Default rates for SDL
    default_rate_normal = 35.00
    default_rate_ntl = 50.00

    # Build game details and per-partner summaries
    game_rows = []
    partner_summaries = {}
    totals = {
        'games': 0,
        'ntl_games': 0,
        'umpires': 0,
        'ntl_umpires': 0,
        'cost_umpires': 0,
        'cost_booking': 0,
        'cost_total': 0
    }

    for game in games:
        # Skip games without an umpire partner assigned
        if not game.umpire_override:
            continue

        # Skip games that were unassigned
        if game.umpire_was_unassigned:
            continue

        game_partner = game.umpire_override.upper()
        league_name = game.league or 'Unknown'
        partner_obj = partner_objs.get(game_partner)

        # Get umpire count
        league_obj = league_lookup.get(league_name.lower().strip())
        if game.umpire_count_override is not None:
            umpire_count = game.umpire_count_override
        elif league_obj:
            is_playoff = game.game_type == 'playoff'
            umpire_count = league_obj.get_umpire_count(is_playoff=is_playoff)
        else:
            umpire_count = 1

        if umpire_count == 0:
            umpire_count = 1

        is_ntl = game.no_time_limit

        # Calculate cost using partner's rate structure
        if partner_obj:
            cost = float(partner_obj.calculate_game_cost(umpire_count, is_ntl))
            booking_fee = float(partner_obj.booking_fee_per_game or 0)
            is_flat_rate = partner_obj.is_flat_rate
            if is_ntl:
                rate = float(partner_obj.rate_ntl or partner_obj.rate_normal or default_rate_ntl)
            else:
                rate = float(partner_obj.rate_normal or default_rate_normal)
        else:
            # SDL defaults
            rate = default_rate_ntl if is_ntl else default_rate_normal
            cost = umpire_count * rate
            booking_fee = 0
            is_flat_rate = False

        # Calculate umpire cost (cost minus booking fee)
        cost_umpires = cost - booking_fee

        game_rows.append({
            'id': game.ID,
            'date': game.game_date.date() if game.game_date else None,
            'time': game.game_date.time() if game.game_date else None,
            'league': league_name,
            'home_team': game.home_team.computed_display_name if game.home_team else 'TBD',
            'away_team': game.away_team.computed_display_name if game.away_team else 'TBD',
            'field': game.field_name or 'TBD',
            'partner': game_partner,
            'umpire_count': umpire_count,
            'is_ntl': is_ntl,
            'is_flat_rate': is_flat_rate,
            'rate': rate,
            'booking_fee': booking_fee,
            'cost_umpires': cost_umpires,
            'cost': cost,
            'game_type': game.game_type,
            'status': game.status
        })

        # Update totals
        totals['games'] += 0 if is_ntl else 1
        totals['ntl_games'] += 1 if is_ntl else 0
        totals['umpires'] += 0 if is_ntl else umpire_count
        totals['ntl_umpires'] += umpire_count if is_ntl else 0
        totals['cost_umpires'] += cost_umpires
        totals['cost_booking'] += booking_fee
        totals['cost_total'] += cost

        # Update per-partner summary
        if game_partner not in partner_summaries:
            partner_summaries[game_partner] = {
                'code': game_partner,
                'name': partner_names.get(game_partner, game_partner),
                'games': 0,
                'ntl_games': 0,
                'umpires': 0,
                'ntl_umpires': 0,
                'cost_umpires': 0,
                'cost_booking': 0,
                'cost_total': 0,
                'rate_description': partner_obj.get_rate_description() if partner_obj else f"${default_rate_normal}/umpire"
            }
        ps = partner_summaries[game_partner]
        ps['games'] += 0 if is_ntl else 1
        ps['ntl_games'] += 1 if is_ntl else 0
        ps['umpires'] += 0 if is_ntl else umpire_count
        ps['ntl_umpires'] += umpire_count if is_ntl else 0
        ps['cost_umpires'] += cost_umpires
        ps['cost_booking'] += booking_fee
        ps['cost_total'] += cost

    # Sort partner summaries by name
    partner_summaries_list = sorted(partner_summaries.values(), key=lambda x: x['name'])

    # Get selected partner name for display
    selected_partner_name = None
    if partner_code:
        for p in partners:
            if p.short_code == partner_code.upper():
                selected_partner_name = p.name
                break
        if not selected_partner_name and partner_code.upper() == 'SDL':
            selected_partner_name = 'SDLL Academy'

    # Calculate quick date range values for template
    quick_ranges = {
        '7days': {
            'start': (today - timedelta(days=6)).strftime('%Y-%m-%d'),
            'end': today.strftime('%Y-%m-%d')
        },
        '14days': {
            'start': (today - timedelta(days=13)).strftime('%Y-%m-%d'),
            'end': today.strftime('%Y-%m-%d')
        },
        '30days': {
            'start': (today - timedelta(days=29)).strftime('%Y-%m-%d'),
            'end': today.strftime('%Y-%m-%d')
        }
    }

    return render_template(
        'umpires/invoice_tieout.html',
        partners=partners,
        partner_code=partner_code,
        selected_partner_name=selected_partner_name,
        start_date=start_date,
        end_date=end_date,
        game_rows=game_rows,
        totals=totals,
        quick_ranges=quick_ranges,
        partner_summaries=partner_summaries_list
    )


@umpires_bp.route('/delegation/rates', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def delegation_rates():
    """Manage per-game rates for each umpire partner.

    Supports:
    - Per-umpire rates (is_flat_rate=False): cost = umpires * rate + booking_fee
    - Flat rates (is_flat_rate=True): cost = flat_rate + booking_fee
    - Per-game booking fees
    - Per-season booking fees
    """
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    if request.method == 'POST':
        for partner in partners:
            # Rate type (flat vs per-umpire)
            partner.is_flat_rate = request.form.get(f'is_flat_rate_{partner.id}') == 'on'

            # Normal rate
            rate_normal = request.form.get(f'rate_normal_{partner.id}', '').strip()
            if rate_normal:
                try:
                    partner.rate_normal = float(rate_normal)
                except ValueError:
                    pass
            else:
                partner.rate_normal = None

            # NTL rate
            rate_ntl = request.form.get(f'rate_ntl_{partner.id}', '').strip()
            if rate_ntl:
                try:
                    partner.rate_ntl = float(rate_ntl)
                except ValueError:
                    pass
            else:
                partner.rate_ntl = None

            # Per-game booking fee
            booking_game = request.form.get(f'booking_fee_per_game_{partner.id}', '').strip()
            if booking_game:
                try:
                    partner.booking_fee_per_game = float(booking_game)
                except ValueError:
                    pass
            else:
                partner.booking_fee_per_game = 0

            # Per-season booking fee
            booking_season = request.form.get(f'booking_fee_per_season_{partner.id}', '').strip()
            if booking_season:
                try:
                    partner.booking_fee_per_season = float(booking_season)
                except ValueError:
                    pass
            else:
                partner.booking_fee_per_season = 0

        db.session.commit()
        flash('Rates updated successfully.', 'success')
        return redirect(url_for('umpires.delegation_rates'))

    return render_template(
        'umpires/delegation_rates.html',
        partners=partners
    )
