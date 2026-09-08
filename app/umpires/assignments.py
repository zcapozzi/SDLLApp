"""Umpire assignment routes - calendar, day view, and API endpoints.

Handles:
- Schedule view
- Missing umpire lookup
- Calendar week view
- Day view
- API endpoints for AJAX assignments
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.field import Field
from app.models.team import TeamSeason
from app.models.umpire_partner import UmpirePartner
from app.models.game_umpire import GameUmpire
from app.models.league import League
from app.models.game import Game

from . import umpires_bp, umpire_coordinator_required, logger


@umpires_bp.route('/schedule')
@login_required
@umpire_coordinator_required
def schedule():
    """View upcoming games with umpire assignments."""
    # Get filter params
    view_type = request.args.get('view', 'upcoming')  # upcoming, unassigned, partner

    # Base query for upcoming games with eager loading
    base_query = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).filter(
        Game.game_date > datetime.utcnow(),
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff'])
    )

    if view_type == 'unassigned':
        # Games with no umpire assignment
        games = base_query.filter(
            ~Game.ID.in_(
                db.session.query(GameUmpire.game_id).filter(
                    GameUmpire.status != 'cancelled'
                )
            )
        ).order_by(Game.game_date).limit(50).all()
    elif view_type == 'partner':
        # Games assigned to partners
        partner_games = GameUmpire.query.filter(
            GameUmpire.partner_id.isnot(None),
            GameUmpire.status != 'cancelled'
        ).join(Game).filter(
            Game.game_date > datetime.utcnow()
        ).order_by(Game.game_date).limit(50).all()
        games = [a.game for a in partner_games]
    else:
        # All upcoming games
        games = base_query.order_by(Game.game_date).limit(50).all()

    # Get ALL assignments for these games in ONE query (not N queries)
    game_ids = [g.ID for g in games]
    game_assignments = {gid: [] for gid in game_ids}

    if game_ids:
        all_assignments = GameUmpire.query.filter(
            GameUmpire.game_id.in_(game_ids),
            GameUmpire.status != 'cancelled'
        ).all()
        for a in all_assignments:
            game_assignments[a.game_id].append(a)

    return render_template(
        'umpires/schedule.html',
        games=games,
        game_assignments=game_assignments,
        view_type=view_type
    )


@umpires_bp.route('/missing-umpire')
@umpires_bp.route('/missing-umpire/<date_str>')
@login_required
@umpire_coordinator_required
def missing_umpire(date_str=None):
    """Quick lookup page for when a field reports a missing umpire.

    Shows all games for a given day with umpire source info and
    quick copy-to-clipboard for contacting the responsible organization.
    """
    from app.models.partner_contact import PartnerContact

    # Parse date (default to today)
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # Get all games for this date (excluding practices)
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.game_date >= start_of_day,
        Game.game_date <= end_of_day,
        Game.active == 1,
        Game.status != 'cancelled',
        Game.game_type != 'practice'  # Exclude practices
    ).order_by(Game.game_date).all()

    # Get all partners for lookup
    partners = {p.short_code: p for p in UmpirePartner.query.filter_by(active=True).all()}

    # Get primary contacts for each partner
    partner_contacts = {}
    for code, partner in partners.items():
        primary = PartnerContact.query.filter_by(
            partner_id=partner.id,
            active=True,
            is_primary=True
        ).first()
        if not primary:
            # Fall back to any active contact
            primary = PartnerContact.query.filter_by(
                partner_id=partner.id,
                active=True
            ).first()
        partner_contacts[code] = primary

    # Get unique values for filters
    fields = sorted(set(g.field_rel.name for g in games if g.field_rel))
    leagues_list = sorted(set(g.league for g in games if g.league))

    # Get league umpire requirements
    league_lookup = {l.display_name: l for l in League.query.all()}

    # For each game, determine if it needs an umpire alert
    # (needs umpire based on league, but doesn't have one assigned and count_override != 0)
    for game in games:
        league_obj = league_lookup.get(game.league)
        needs_umpire = False
        if league_obj and league_obj.needs_umpires:
            # Check if umpire count override is 0 (explicitly no umpire needed)
            if game.umpire_count_override == 0:
                needs_umpire = False
            else:
                needs_umpire = True
        game._needs_umpire = needs_umpire

    return render_template(
        'umpires/missing_umpire.html',
        games=games,
        target_date=target_date,
        partners=partners,
        partner_contacts=partner_contacts,
        fields=fields,
        leagues=leagues_list
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/calendar')
@login_required
@umpire_coordinator_required
def umpire_calendar(year, is_spring):
    """Calendar view for umpire coordination - assign umpire sources to games."""
    from app.models.league_season import LeagueSeason

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Check for date param - redirect to day view if present
    date_param = request.args.get('date')
    if date_param:
        return redirect(url_for('umpires.umpire_day_view', year=year, is_spring=is_spring, date=date_param))

    # Get week parameter (ISO week number) or default to current week
    week_param = request.args.get('week')

    # Get league filter
    league = request.args.get('league')

    # Determine the date range for this season
    configs = LeagueSeason.get_by_season(year, is_spring)

    # Find earliest opening day across all leagues
    opening_dates = [c.opening_day_date for c in configs if c.opening_day_date]
    if opening_dates:
        season_start = min(opening_dates)
    else:
        # Default to a reasonable start date
        season_start = date(year, 3 if is_spring else 9, 1)

    # Calculate current week
    today = date.today()
    if week_param:
        # Parse week parameter (format: YYYY-WW)
        try:
            week_year, week_num = week_param.split('-')
            # Get Monday of that week
            week_start = datetime.strptime(f'{week_year}-W{week_num}-1', '%G-W%V-%u').date()
        except (ValueError, AttributeError):
            week_start = today - timedelta(days=today.weekday())
    else:
        # Default to current week if in season, otherwise opening week
        if season_start <= today:
            week_start = today - timedelta(days=today.weekday())
        else:
            week_start = season_start - timedelta(days=season_start.weekday())

    week_end = week_start + timedelta(days=6)

    # Query all games for the week in ONE query with eager loading
    week_query = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        db.func.date(Game.game_date) >= week_start,
        db.func.date(Game.game_date) <= week_end,
        Game.game_type.in_(['regular', 'playoff'])
    )
    if league:
        week_query = week_query.filter(Game.league == league)

    all_week_games = week_query.order_by(Game.game_date, Game.field_id).all()

    # Pre-load all leagues to avoid N+1 queries for umpire_count
    all_leagues = {lg.display_name: lg for lg in League.get_all_active()}
    # Also add fall names
    for lg in League.get_all_active():
        if lg.fall_display_name:
            all_leagues[lg.fall_display_name] = lg

    # Pre-compute umpire counts and field names to avoid N+1 queries in template
    for game in all_week_games:
        # Cache umpire count
        if game.umpire_count_override is not None:
            game._cached_umpire_count = game.umpire_count_override
        else:
            league_obj = all_leagues.get(game.league)
            if league_obj:
                is_playoff = game.game_type == 'playoff'
                game._cached_umpire_count = league_obj.get_umpire_count(is_playoff=is_playoff)
            else:
                game._cached_umpire_count = 1

        # Cache field name
        game._cached_field_name = game.field_name

    # Group games by date
    games_by_date = {}
    for game in all_week_games:
        if game.game_date:
            game_date = game.game_date.date()
            if game_date not in games_by_date:
                games_by_date[game_date] = []
            games_by_date[game_date].append(game)

    # Build week days with games
    week_days = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        week_days.append({
            'date': day_date,
            'is_today': day_date == today,
            'games': games_by_date.get(day_date, [])
        })

    # Calculate prev/next week
    prev_week = (week_start - timedelta(days=7)).strftime('%G-%V')
    next_week = (week_start + timedelta(days=7)).strftime('%G-%V')

    # Get leagues for filter
    leagues = db.session.query(Game.league).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league.isnot(None),
        Game.game_type.in_(['regular', 'playoff'])
    ).distinct().all()
    leagues = [l[0] for l in leagues if l[0]]
    leagues.sort()

    # Get teams and fields for reference
    teams = TeamSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1
    ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    # Get umpire partners for legend
    partners = UmpirePartner.get_active()

    # Get available seasons (those with games)
    available_seasons = db.session.query(
        Game.year,
        Game.is_spring
    ).filter(
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff'])
    ).distinct().order_by(Game.year.desc(), Game.is_spring.desc()).all()

    seasons = [
        {'year': y, 'is_spring': s, 'name': f'{"Spring" if s else "Fall"} {y}'}
        for y, s in available_seasons
    ]

    return render_template(
        'umpires/calendar.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        week_start=week_start,
        week_end=week_end,
        week_days=week_days,
        prev_week=prev_week,
        next_week=next_week,
        leagues=leagues,
        teams=teams,
        fields=fields,
        current_league=league,
        today=today,
        partners=partners,
        seasons=seasons
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/day')
@umpires_bp.route('/<int:year>/<int:is_spring>/day/<date>')
@login_required
@umpire_coordinator_required
def umpire_day_view(year, is_spring, date=None):
    """Day view for umpire coordination - single day focus for game assignments."""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Parse date parameter or use today
    if date:
        try:
            if isinstance(date, str):
                view_date = datetime.strptime(date, '%Y-%m-%d').date()
            else:
                view_date = date
        except ValueError:
            view_date = datetime.today().date()
    else:
        # Check URL query param
        date_param = request.args.get('date')
        if date_param:
            try:
                view_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                view_date = datetime.today().date()
        else:
            view_date = datetime.today().date()

    # Get league filter
    league = request.args.get('league')

    # Query all games for the day with eager loading
    day_query = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team),
        joinedload(Game.field_rel)
    ).filter(
        Game.active == 1,
        Game.year == year,
        Game.is_spring == is_spring,
        db.func.date(Game.game_date) == view_date,
        Game.game_type.in_(['regular', 'playoff'])
    )
    if league:
        day_query = day_query.filter(Game.league == league)

    games = day_query.order_by(Game.game_date, Game.field_id).all()

    # Pre-load all leagues to avoid N+1 queries for umpire_count
    all_leagues = {lg.display_name: lg for lg in League.get_all_active()}
    for lg in League.get_all_active():
        if lg.fall_display_name:
            all_leagues[lg.fall_display_name] = lg

    # Pre-compute umpire counts and field names
    for game in games:
        if game.umpire_count_override is not None:
            game._cached_umpire_count = game.umpire_count_override
        else:
            league_obj = all_leagues.get(game.league)
            if league_obj:
                is_playoff = game.game_type == 'playoff'
                game._cached_umpire_count = league_obj.get_umpire_count(is_playoff=is_playoff)
            else:
                game._cached_umpire_count = 1
        game._cached_field_name = game.field_name

    # Group games by time slot for easier viewing
    games_by_time = {}
    for game in games:
        if game.game_date:
            time_key = game.game_date.strftime('%I:%M %p')
            if time_key not in games_by_time:
                games_by_time[time_key] = []
            games_by_time[time_key].append(game)

    # Calculate prev/next day
    prev_date = view_date - timedelta(days=1)
    next_date = view_date + timedelta(days=1)

    # Get leagues for filter
    leagues = db.session.query(Game.league).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.league.isnot(None),
        Game.game_type.in_(['regular', 'playoff'])
    ).distinct().all()
    leagues = [l[0] for l in leagues if l[0]]
    leagues.sort()

    # Get umpire partners for legend
    partners = UmpirePartner.get_active()

    # Get available seasons
    available_seasons = db.session.query(
        Game.year,
        Game.is_spring
    ).filter(
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff'])
    ).distinct().order_by(Game.year.desc(), Game.is_spring.desc()).all()

    seasons = [
        {'year': y, 'is_spring': s, 'name': f'{"Spring" if s else "Fall"} {y}'}
        for y, s in available_seasons
    ]

    return render_template(
        'umpires/day_view.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        view_date=view_date,
        games=games,
        games_by_time=games_by_time,
        prev_date=prev_date,
        next_date=next_date,
        leagues=leagues,
        current_league=league,
        today=datetime.today().date(),
        partners=partners,
        seasons=seasons
    )


# =============================================================================
# API Endpoints for AJAX
# =============================================================================

@umpires_bp.route('/api/assign', methods=['POST'])
@login_required
@umpire_coordinator_required
def api_assign():
    """Assign umpire to a game (AJAX)."""
    data = request.get_json()
    game_id = data.get('game_id')
    umpire_profile_id = data.get('umpire_profile_id')
    partner_id = data.get('partner_id')
    role = data.get('role', 'umpire')

    if not game_id:
        return jsonify({'error': 'Game ID required'}), 400

    if not umpire_profile_id and not partner_id:
        return jsonify({'error': 'Umpire or partner required'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    try:
        if umpire_profile_id:
            assignment = GameUmpire.assign_umpire(
                game_id=game_id,
                umpire_profile_id=umpire_profile_id,
                role=role,
                assigned_by=current_user.ID
            )
        else:
            assignment = GameUmpire.assign_partner(
                game_id=game_id,
                partner_id=partner_id,
                role=role,
                assigned_by=current_user.ID
            )

        db.session.commit()
        return jsonify({
            'success': True,
            'assignment_id': assignment.id,
            'message': 'Umpire assigned successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@umpires_bp.route('/api/unassign', methods=['POST'])
@login_required
@umpire_coordinator_required
def api_unassign():
    """Remove umpire assignment (AJAX)."""
    data = request.get_json()
    assignment_id = data.get('assignment_id')

    if not assignment_id:
        return jsonify({'error': 'Assignment ID required'}), 400

    assignment = GameUmpire.query.get(assignment_id)
    if not assignment:
        return jsonify({'error': 'Assignment not found'}), 404

    try:
        assignment.cancel(current_user.ID)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Assignment cancelled'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@umpires_bp.route('/api/set-umpire-source', methods=['POST'])
@login_required
@umpire_coordinator_required
def api_set_umpire_source():
    """Set the umpire source for a game via right-click menu.

    When changing from one partner to another, this queues notifications
    to BOTH partners:
    - The old partner receives "game removed from your assignment"
    - The new partner receives "game assigned to you"
    """
    from app.services.game_changes import GameChangeService
    from app.models.notification_queue import NotificationQueue
    from app.models.partner_contact import PartnerContact
    from app.services.notification_templates import render_umpire_reassignment_notification

    data = request.get_json()
    game_id = data.get('game_id')
    source = data.get('source')  # Short codes: 'SDL', 'DIA', 'DYN' or None to clear

    # Valid short codes (stored in DB) - get from active partners plus SDL
    valid_sources = ['SDL']  # SDLL Academy is always valid
    partners = UmpirePartner.get_active()
    partner_lookup = {p.short_code.upper(): p for p in partners}
    for p in partners:
        valid_sources.append(p.short_code.upper())

    # Allow None/empty to clear the override
    if source == '' or source is None:
        source = None
    else:
        # Normalize to uppercase
        source = source.upper()
        if source not in valid_sources:
            return jsonify({'error': f'Invalid source. Valid: {", ".join(valid_sources)}'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    # Track if this is a change (not initial assignment)
    old_source = game.umpire_override
    is_change = old_source is not None and old_source != source
    is_new_assignment = old_source is None and source is not None

    game.umpire_override = source
    db.session.commit()

    notifications_queued = 0

    # Queue notifications when changing from one partner to another
    if is_change:
        try:
            # Log the change
            change = GameChangeService.log_change(
                game_id=game_id,
                user_id=current_user.ID,
                change_type='update',
                changes_dict={'umpire_source': {'old': old_source, 'new': source}},
                reason=f'Umpire source changed from {old_source or "none"} to {source or "none"}'
            )

            # Notify OLD partner (game removed from their assignment)
            old_partner = partner_lookup.get(old_source.upper()) if old_source else None
            if old_partner:
                contacts = old_partner.get_contacts_for_message_type(PartnerContact.MSG_RECENT_CHANGES)
                for contact in contacts:
                    try:
                        subject, body_text, body_html = render_umpire_reassignment_notification(
                            game=game,
                            action='removed',
                            partner_name=old_partner.name,
                            new_partner_name=partner_lookup.get(source.upper()).name if source and partner_lookup.get(source.upper()) else (source or 'Unassigned')
                        )
                        notification = NotificationQueue(
                            change_id=change.id if change else None,
                            game_id=game.ID,
                            recipient_type='partner',
                            recipient_id=contact.user_id,
                            recipient_email=contact.display_email,
                            recipient_name=contact.display_name or old_partner.name,
                            subject=subject,
                            body_text=body_text,
                            body_html=body_html,
                            status='pending'
                        )
                        db.session.add(notification)
                        notifications_queued += 1
                    except Exception as e:
                        logger.warning(f'Failed to queue notification to old partner: {e}')

            # Notify NEW partner (game assigned to them)
            new_partner = partner_lookup.get(source.upper()) if source else None
            if new_partner:
                contacts = new_partner.get_contacts_for_message_type(PartnerContact.MSG_RECENT_CHANGES)
                for contact in contacts:
                    try:
                        subject, body_text, body_html = render_umpire_reassignment_notification(
                            game=game,
                            action='assigned',
                            partner_name=new_partner.name,
                            old_partner_name=old_partner.name if old_partner else (old_source or 'Unassigned')
                        )
                        notification = NotificationQueue(
                            change_id=change.id if change else None,
                            game_id=game.ID,
                            recipient_type='partner',
                            recipient_id=contact.user_id,
                            recipient_email=contact.display_email,
                            recipient_name=contact.display_name or new_partner.name,
                            subject=subject,
                            body_text=body_text,
                            body_html=body_html,
                            status='pending'
                        )
                        db.session.add(notification)
                        notifications_queued += 1
                    except Exception as e:
                        logger.warning(f'Failed to queue notification to new partner: {e}')

            db.session.commit()
        except Exception as e:
            logger.warning(f'Failed to log umpire source change: {e}')

    # Handle Assignr publish/unpublish based on SDL assignment
    assignr_unpublished = False
    assignr_published = False
    assignr_error = None

    if game.assignr_id:
        try:
            from app.services.assignr_service import get_assignr_service
            assignr_service = get_assignr_service()
            if assignr_service.is_configured():
                # If removing from SDL (Academy), unpublish in Assignr
                if old_source and old_source.upper() == 'SDL' and (source is None or source.upper() != 'SDL'):
                    success, error = assignr_service.unpublish_game(int(game.assignr_id))
                    if success:
                        assignr_unpublished = True
                        logger.info(f'Unpublished game {game_id} (assignr_id={game.assignr_id}) from Assignr')
                    else:
                        assignr_error = error
                        logger.warning(f'Failed to unpublish game in Assignr: {error}')
                # If assigning TO SDL (Academy), publish in Assignr
                elif source and source.upper() == 'SDL' and (old_source is None or old_source.upper() != 'SDL'):
                    success, error = assignr_service.publish_game(int(game.assignr_id))
                    if success:
                        assignr_published = True
                        logger.info(f'Published game {game_id} (assignr_id={game.assignr_id}) in Assignr')
                    else:
                        assignr_error = error
                        logger.warning(f'Failed to publish game in Assignr: {error}')
        except Exception as e:
            assignr_error = str(e)
            logger.warning(f'Failed to update game in Assignr: {e}')

    logger.info(f'Set umpire source for game {game_id} to {source} (notifications queued: {notifications_queued})')
    return jsonify({
        'success': True,
        'source': source,
        'notifications_queued': notifications_queued,
        'assignr_unpublished': assignr_unpublished,
        'assignr_published': assignr_published,
        'assignr_error': assignr_error
    })


@umpires_bp.route('/api/set-umpire-count', methods=['POST'])
@login_required
@umpire_coordinator_required
def api_set_umpire_count():
    """Set the umpire count override for a game via right-click menu."""
    data = request.get_json()
    game_id = data.get('game_id')
    count = data.get('count')  # Integer or None to reset to league default

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    # Allow None to reset to league default, or 0-3 for specific count
    if count is not None:
        try:
            count = int(count)
            if count < 0 or count > 3:
                return jsonify({'error': 'Count must be 0-3'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid count value'}), 400

    old_count = game.umpire_count_override
    game.umpire_count_override = count

    # If changing from 0 umpires to 1+ umpires, reset umpire_was_unassigned
    if old_count == 0 and count is not None and count > 0:
        game.umpire_was_unassigned = 0

    db.session.commit()

    # Return the effective count (for display)
    effective_count = game.umpire_count

    logger.info(f'Set umpire count for game {game_id} to {count} (effective: {effective_count})')
    return jsonify({
        'success': True,
        'count_override': count,
        'effective_count': effective_count
    })


@umpires_bp.route('/api/mark-no-umpire-required', methods=['POST'])
@login_required
@umpire_coordinator_required
def api_mark_no_umpire_required():
    """Mark a game as not requiring umpires (was assigned in error).

    Sets umpire_was_unassigned=1. The game will:
    - Still show on partner schedule with "NO UMPIRE" indicator
    - Be excluded from delegation report counts
    - Trigger a notification to the partner
    """
    data = request.get_json()
    game_id = data.get('game_id')

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    if not game.umpire_override:
        return jsonify({'error': 'Game has no umpire assignment to unassign'}), 400

    # Mark as unassigned
    game.umpire_was_unassigned = 1
    db.session.commit()

    # TODO: Queue notification to partner about the unassignment

    logger.info(f'Marked game {game_id} as no umpire required (was assigned to {game.umpire_override})')
    return jsonify({
        'success': True,
        'message': f'Game marked as no umpire required'
    })
