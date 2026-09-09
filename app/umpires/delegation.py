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

    # Calculate costs
    # Default rates if not set (you can change these defaults)
    default_rate_normal = 35.00
    default_rate_ntl = 50.00

    # Get rates from partners
    rates = {'SDL': {'normal': default_rate_normal, 'ntl': default_rate_ntl}}
    for p in partners:
        rates[p.short_code] = {
            'normal': float(p.rate_normal) if p.rate_normal else default_rate_normal,
            'ntl': float(p.rate_ntl) if p.rate_ntl else default_rate_ntl
        }

    # Calculate totals and costs
    report_data = []
    grand_totals = {
        'games': 0, 'ntl_games': 0, 'umpires': 0, 'ntl_umpires': 0,
        'cost_normal': 0, 'cost_ntl': 0, 'cost_total': 0
    }

    for partner_code in partner_codes:
        if partner_code not in summary:
            continue

        partner_rates = rates.get(partner_code, {'normal': default_rate_normal, 'ntl': default_rate_ntl})
        partner_name = partner_lookup.get(partner_code)
        partner_name = partner_name.name if partner_name else ('SDLL Academy' if partner_code == 'SDL' else partner_code)

        partner_totals = {
            'games': 0, 'ntl_games': 0, 'umpires': 0, 'ntl_umpires': 0,
            'cost_normal': 0, 'cost_ntl': 0, 'cost_total': 0
        }

        league_rows = []
        for league_name, data in sorted(summary[partner_code].items()):
            cost_normal = data['umpires'] * partner_rates['normal']
            cost_ntl = data['ntl_umpires'] * partner_rates['ntl']
            cost_total = cost_normal + cost_ntl

            league_rows.append({
                'league': league_name,
                'games': data['games'],
                'ntl_games': data['ntl_games'],
                'umpires': data['umpires'],
                'ntl_umpires': data['ntl_umpires'],
                'cost_normal': cost_normal,
                'cost_ntl': cost_ntl,
                'cost_total': cost_total
            })

            partner_totals['games'] += data['games']
            partner_totals['ntl_games'] += data['ntl_games']
            partner_totals['umpires'] += data['umpires']
            partner_totals['ntl_umpires'] += data['ntl_umpires']
            partner_totals['cost_normal'] += cost_normal
            partner_totals['cost_ntl'] += cost_ntl
            partner_totals['cost_total'] += cost_total

        # Calculate blended rate (total cost / total umpires)
        total_umpires = partner_totals['umpires'] + partner_totals['ntl_umpires']
        blended_rate = partner_totals['cost_total'] / total_umpires if total_umpires > 0 else 0

        report_data.append({
            'code': partner_code,
            'name': partner_name,
            'rate_normal': partner_rates['normal'],
            'rate_ntl': partner_rates['ntl'],
            'leagues': league_rows,
            'totals': partner_totals,
            'blended_rate': blended_rate
        })

        grand_totals['games'] += partner_totals['games']
        grand_totals['ntl_games'] += partner_totals['ntl_games']
        grand_totals['umpires'] += partner_totals['umpires']
        grand_totals['ntl_umpires'] += partner_totals['ntl_umpires']
        grand_totals['cost_normal'] += partner_totals['cost_normal']
        grand_totals['cost_ntl'] += partner_totals['cost_ntl']
        grand_totals['cost_total'] += partner_totals['cost_total']

    # Get available seasons for picker
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    return render_template(
        'umpires/delegation_report.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        seasons=seasons,
        report_data=report_data,
        grand_totals=grand_totals,
        partners=partners
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

    # Get partner rates
    default_rate_normal = 35.00
    default_rate_ntl = 50.00
    partner_rates = {}
    for p in partners:
        partner_rates[p.short_code] = {
            'normal': float(p.rate_normal) if p.rate_normal else default_rate_normal,
            'ntl': float(p.rate_ntl) if p.rate_ntl else default_rate_ntl
        }
    # Add SDL rates
    sdl_partner = next((p for p in partners if p.short_code == 'SDL'), None)
    if sdl_partner:
        partner_rates['SDL'] = {
            'normal': float(sdl_partner.rate_normal) if sdl_partner.rate_normal else default_rate_normal,
            'ntl': float(sdl_partner.rate_ntl) if sdl_partner.rate_ntl else default_rate_ntl
        }
    else:
        partner_rates['SDL'] = {'normal': default_rate_normal, 'ntl': default_rate_ntl}

    # Build game details and per-partner summaries
    game_rows = []
    partner_summaries = {}  # {partner_code: {name, games, ntl_games, umpires, ntl_umpires, cost_normal, cost_ntl, cost_total}}
    totals = {
        'games': 0,
        'ntl_games': 0,
        'umpires': 0,
        'ntl_umpires': 0,
        'cost_normal': 0,
        'cost_ntl': 0,
        'cost_total': 0
    }

    # Build partner name lookup
    partner_names = {p.short_code: p.name for p in partners}
    partner_names['SDL'] = 'SDLL Academy'

    for game in games:
        # Skip games without an umpire partner assigned
        if not game.umpire_override:
            continue

        # Skip games that were unassigned
        if game.umpire_was_unassigned:
            continue

        game_partner = game.umpire_override.upper()
        league_name = game.league or 'Unknown'

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

        # Get rates for this partner
        rates = partner_rates.get(game_partner, {'normal': default_rate_normal, 'ntl': default_rate_ntl})

        # Calculate cost
        is_ntl = game.no_time_limit
        if is_ntl:
            cost = umpire_count * rates['ntl']
        else:
            cost = umpire_count * rates['normal']

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
            'rate': rates['ntl'] if is_ntl else rates['normal'],
            'cost': cost,
            'game_type': game.game_type,
            'status': game.status
        })

        # Update totals
        totals['games'] += 0 if is_ntl else 1
        totals['ntl_games'] += 1 if is_ntl else 0
        totals['umpires'] += 0 if is_ntl else umpire_count
        totals['ntl_umpires'] += umpire_count if is_ntl else 0
        totals['cost_normal'] += 0 if is_ntl else cost
        totals['cost_ntl'] += cost if is_ntl else 0
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
                'cost_normal': 0,
                'cost_ntl': 0,
                'cost_total': 0
            }
        ps = partner_summaries[game_partner]
        ps['games'] += 0 if is_ntl else 1
        ps['ntl_games'] += 1 if is_ntl else 0
        ps['umpires'] += 0 if is_ntl else umpire_count
        ps['ntl_umpires'] += umpire_count if is_ntl else 0
        ps['cost_normal'] += 0 if is_ntl else cost
        ps['cost_ntl'] += cost if is_ntl else 0
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
        partner_rates=partner_rates,
        quick_ranges=quick_ranges,
        partner_summaries=partner_summaries_list
    )


@umpires_bp.route('/delegation/rates', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def delegation_rates():
    """Manage per-game rates for each umpire partner."""
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    if request.method == 'POST':
        for partner in partners:
            rate_normal = request.form.get(f'rate_normal_{partner.id}')
            rate_ntl = request.form.get(f'rate_ntl_{partner.id}')

            if rate_normal:
                try:
                    partner.rate_normal = float(rate_normal)
                except ValueError:
                    pass

            if rate_ntl:
                try:
                    partner.rate_ntl = float(rate_ntl)
                except ValueError:
                    pass

        db.session.commit()
        flash('Rates updated successfully.', 'success')
        return redirect(url_for('umpires.delegation_rates'))

    return render_template(
        'umpires/delegation_rates.html',
        partners=partners
    )
