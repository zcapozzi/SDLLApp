"""Treasurer routes - financial reports for umpire payments."""

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from datetime import date
from collections import defaultdict
from decimal import Decimal

from app.extensions import db
from app.models.umpire_partner import UmpirePartner
from app.models.league_season import LeagueSeason
from app.models.org_season import OrgSeason
from app.models.umpire_game_payment import UmpireGamePayment
from app.models.game import Game
from app.services.assignr_service import get_assignr_service

from . import treasurer_bp, treasurer_required, logger


@treasurer_bp.route('/managed-umpires')
@treasurer_bp.route('/managed-umpires/<int:year>/<int:is_spring>')
def managed_umpires(year=None, is_spring=None):
    """Report showing Academy umpire game counts and payments from Assignr.

    Access control:
    - Not logged in: Landing page with login link
    - Logged in without permission: Redirect with error
    - Logged in with permission: Full report

    Shows:
    - List of managed (Academy) umpires
    - Regular game count per umpire
    - NTL game count per umpire
    - Base pay calculations
    - Multiplier adjustments
    - Total owed per umpire
    """
    # Check authentication - show landing page if not logged in
    if not current_user.is_authenticated:
        login_url = url_for('auth.login', next=request.url)
        return render_template(
            'treasurer/landing.html',
            page_title='Managed Umpires',
            description='Please log in to view the Managed Umpires report. This page shows Academy umpire game counts and payment calculations.',
            login_url=login_url
        )

    # Check authorization
    if not current_user.is_treasurer():
        flash('You do not have permission to access treasurer functions.', 'error')
        return redirect(url_for('main.dashboard'))

    # Default to current season
    if year is None:
        current = OrgSeason.get_current_season()
        if current:
            year = current.year
            is_spring = 1 if current.is_spring else 0
        else:
            # Fall back to LeagueSeason query
            fallback = db.session.query(
                LeagueSeason.year, LeagueSeason.is_spring
            ).filter_by(active=1).order_by(
                LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
            ).first()
            if fallback:
                year = fallback.year
                is_spring = 1 if fallback.is_spring else 0
            else:
                year = date.today().year
                is_spring = 1 if date.today().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get season date range from LeagueSeason
    league_seasons = LeagueSeason.query.filter_by(
        year=year,
        is_spring=(is_spring == 1),
        active=1
    ).all()

    if not league_seasons:
        flash(f'No league configurations found for {season_name}.', 'warning')
        return render_template(
            'treasurer/managed_umpires.html',
            year=year,
            is_spring=is_spring,
            season_name=season_name,
            seasons=[],
            umpire_data=[],
            rates={'normal': 0, 'ntl': 0},
            grand_total={'games': 0, 'ntl_games': 0, 'base_pay': 0, 'adjustments': 0, 'total': 0}
        )

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
        flash(f'Season dates not configured for {season_name}.', 'warning')
        return render_template(
            'treasurer/managed_umpires.html',
            year=year,
            is_spring=is_spring,
            season_name=season_name,
            seasons=[],
            umpire_data=[],
            rates={'normal': 0, 'ntl': 0},
            grand_total={'games': 0, 'ntl_games': 0, 'base_pay': 0, 'adjustments': 0, 'total': 0}
        )

    # Get SDL partner rates
    sdl_partner = UmpirePartner.query.filter_by(short_code='SDL', active=True).first()
    if sdl_partner:
        rate_normal = float(sdl_partner.rate_normal) if sdl_partner.rate_normal else 35.00
        rate_ntl = float(sdl_partner.rate_ntl) if sdl_partner.rate_ntl else 50.00
    else:
        rate_normal = 35.00
        rate_ntl = 50.00

    rates = {'normal': rate_normal, 'ntl': rate_ntl}

    # Fetch games from Assignr
    assignr = get_assignr_service()
    if not assignr.is_configured():
        flash('Assignr API not configured.', 'error')
        return render_template(
            'treasurer/managed_umpires.html',
            year=year,
            is_spring=is_spring,
            season_name=season_name,
            seasons=[],
            umpire_data=[],
            rates=rates,
            grand_total={'games': 0, 'ntl_games': 0, 'base_pay': 0, 'adjustments': 0, 'total': 0}
        )

    from datetime import datetime
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    assignr_games = assignr.get_all_games(start_dt, end_dt)
    assignr_games = assignr.enrich_games_with_local_data(assignr_games)

    # Get local game statuses for filtering
    assignr_ids = [str(g.get('id')) for g in assignr_games if g.get('id')]
    local_games = {}
    if assignr_ids:
        games_query = Game.query.filter(
            Game.assignr_id.in_(assignr_ids),
            Game.active == 1
        ).all()
        local_games = {g.assignr_id: g for g in games_query}

    # Filter out cancelled/rainout games
    valid_games = []
    for game in assignr_games:
        # Skip if cancelled in Assignr
        if game.get('is_cancelled'):
            continue

        # Skip if local game is cancelled or rainout
        assignr_id = str(game.get('id', ''))
        local_game = local_games.get(assignr_id)
        if local_game and local_game.status in ('cancelled', 'rainout'):
            continue

        # Only include completed games (game date has passed)
        game_date = game.get('_game_date')
        if game_date and game_date.date() <= date.today():
            valid_games.append(game)

    # Build map of official_id -> games
    games_by_official = defaultdict(list)
    official_info = {}  # Store official details

    for game in valid_games:
        assignments = game.get('_embedded', {}).get('assignments', []) or []
        for assignment in assignments:
            # Only count accepted assignments
            if assignment.get('accepted') not in [True, 'True']:
                continue

            embedded = assignment.get('_embedded', {}) or {}
            official = embedded.get('official', {}) or {}
            official_id = official.get('id')

            if official_id:
                # Store official info
                if official_id not in official_info:
                    official_info[official_id] = {
                        'first_name': official.get('first_name', ''),
                        'last_name': official.get('last_name', ''),
                        'email': '',
                        'assignr_id': official_id
                    }
                    # Try to get email
                    email_addresses = official.get('email_addresses', [])
                    if email_addresses:
                        official_info[official_id]['email'] = email_addresses[0].get('email', '')

                # Track game info
                local_data = game.get('_local', {}) or {}
                games_by_official[official_id].append({
                    'game_id': local_data.get('game_id') if local_data else None,
                    'assignr_id': game.get('id'),
                    'game_date': game.get('_game_date'),
                    'league': local_data.get('league') if local_data else game.get('league_name', 'Unknown'),
                    'is_ntl': game.get('no_time_limit', False) or (local_data.get('status') == 'ntl' if local_data else False)
                })

    # Get all local game IDs for multiplier lookup
    all_game_ids = []
    for official_id, games in games_by_official.items():
        for g in games:
            if g['game_id']:
                all_game_ids.append(g['game_id'])

    # Get multipliers
    multipliers = UmpireGamePayment.get_multipliers_for_games(all_game_ids)

    # Calculate pay per umpire
    umpire_data = []
    grand_total = {
        'games': 0,
        'ntl_games': 0,
        'base_pay': Decimal('0'),
        'adjustments': Decimal('0'),
        'total': Decimal('0')
    }

    for official_id, games in sorted(games_by_official.items(), key=lambda x: official_info.get(x[0], {}).get('last_name', '')):
        info = official_info.get(official_id, {})
        normal_games = 0
        ntl_games = 0
        adjustment_total = Decimal('0')

        for g in games:
            # Check for multiplier
            multiplier = Decimal('1.0')
            if g['game_id']:
                key = (g['game_id'], official_id)
                if key in multipliers:
                    multiplier = Decimal(str(multipliers[key]))

            if g.get('is_ntl'):
                ntl_games += 1
                if multiplier != Decimal('1.0'):
                    adjustment_total += (Decimal(str(rate_ntl)) * (multiplier - Decimal('1.0')))
            else:
                normal_games += 1
                if multiplier != Decimal('1.0'):
                    adjustment_total += (Decimal(str(rate_normal)) * (multiplier - Decimal('1.0')))

        base_pay = (Decimal(normal_games) * Decimal(str(rate_normal))) + (Decimal(ntl_games) * Decimal(str(rate_ntl)))
        total_pay = base_pay + adjustment_total

        umpire_data.append({
            'official_id': official_id,
            'first_name': info.get('first_name', ''),
            'last_name': info.get('last_name', ''),
            'full_name': f"{info.get('first_name', '')} {info.get('last_name', '')}".strip(),
            'email': info.get('email', ''),
            'normal_games': normal_games,
            'ntl_games': ntl_games,
            'total_games': normal_games + ntl_games,
            'base_pay': float(base_pay),
            'adjustments': float(adjustment_total),
            'total_pay': float(total_pay)
        })

        grand_total['games'] += normal_games
        grand_total['ntl_games'] += ntl_games
        grand_total['base_pay'] += base_pay
        grand_total['adjustments'] += adjustment_total
        grand_total['total'] += total_pay

    # Convert grand_total decimals to floats for template
    grand_total['base_pay'] = float(grand_total['base_pay'])
    grand_total['adjustments'] = float(grand_total['adjustments'])
    grand_total['total'] = float(grand_total['total'])

    # Get available seasons for picker
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()

    return render_template(
        'treasurer/managed_umpires.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        seasons=seasons,
        umpire_data=umpire_data,
        rates=rates,
        grand_total=grand_total,
        start_date=start_date,
        end_date=end_date
    )
