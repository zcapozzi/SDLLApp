"""Umpire management routes for coordinators.

Provides admin interfaces for:
- Managing umpire profiles
- Managing umpire partners (Diamond, Dynamic)
- Configuring delegation rules
- Viewing assignment status
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date, timedelta

from app.extensions import db
from app.models.user import User
from app.models.field import Field
from app.models.team import TeamSeason
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_partner import UmpirePartner
from app.models.game_umpire import GameUmpire
from app.models.umpire_delegation import UmpireDelegationRule, UmpireDelegationOverride
from app.models.league import League
from app.models.game import Game
from app.utils.logging import SDLLLogger

umpires_bp = Blueprint('umpires', __name__)
logger = SDLLLogger('umpires')


def umpire_coordinator_required(f):
    """Decorator to require umpire coordinator or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.can_manage_umpires():
            flash('You do not have permission to manage umpires.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# Umpire List and Management
# =============================================================================

@umpires_bp.route('/')
@login_required
@umpire_coordinator_required
def index():
    """List all umpires with status filters."""
    status_filter = request.args.get('status', 'active')

    if status_filter == 'all':
        profiles = UmpireProfile.query.join(User).filter(User.active == 1).all()
    else:
        profiles = UmpireProfile.query.filter_by(status=status_filter).join(User).filter(User.active == 1).all()

    # Get partners for quick reference
    partners = UmpirePartner.get_active()

    return render_template(
        'umpires/index.html',
        profiles=profiles,
        partners=partners,
        status_filter=status_filter
    )


@umpires_bp.route('/add', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def add():
    """Add a new umpire."""
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        is_kid_pitch_eligible = request.form.get('is_kid_pitch_eligible') == 'on'
        parent_name = request.form.get('parent_name', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()

        # Validate required fields
        if not name or not email:
            flash('Name and email are required.', 'error')
            return render_template('umpires/add.html')

        # Check for existing user with this email
        existing = User.get_by_email(email)
        if existing:
            flash(f'A user with email {email} already exists.', 'error')
            return render_template('umpires/add.html')

        try:
            # Create user account
            # Generate a temporary password (they'll reset it on first login)
            import secrets
            temp_password = secrets.token_urlsafe(12)

            user = User.create_user(
                email=email,
                password=temp_password,
                name=name,
                phone=phone if phone else None,
                role='umpire'
            )

            # Parse birth date
            birth_date = None
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Create umpire profile
            profile = UmpireProfile(
                user_id=user.ID,
                birth_date=birth_date,
                is_kid_pitch_eligible=is_kid_pitch_eligible,
                status='active'
            )

            # Set parent contacts if provided
            if parent_name:
                profile.parent_name = parent_name
            if parent_email:
                profile.parent_email = parent_email
            if parent_phone:
                profile.parent_phone = parent_phone

            db.session.add(profile)
            db.session.commit()

            logger.info(f'Added umpire: {name} (ID: {profile.id})')
            flash(f'Added umpire: {name}', 'success')

            # TODO: Send welcome email with password reset link

            return redirect(url_for('umpires.view', id=profile.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Error adding umpire: {e}')
            flash(f'Error adding umpire: {str(e)}', 'error')

    return render_template('umpires/add.html')


@umpires_bp.route('/<int:id>')
@login_required
@umpire_coordinator_required
def view(id):
    """View umpire profile details."""
    profile = UmpireProfile.query.get_or_404(id)

    # Get recent and upcoming games
    upcoming_assignments = GameUmpire.get_for_umpire(profile.id, future_only=True)
    past_assignments = GameUmpire.query.filter_by(
        umpire_profile_id=profile.id
    ).join(Game).filter(
        Game.game_date <= datetime.utcnow()
    ).order_by(Game.game_date.desc()).limit(10).all()

    return render_template(
        'umpires/view.html',
        profile=profile,
        upcoming_assignments=upcoming_assignments,
        past_assignments=past_assignments
    )


@umpires_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def edit(id):
    """Edit umpire profile."""
    profile = UmpireProfile.query.get_or_404(id)

    if request.method == 'POST':
        # Update user info
        profile.user.name = request.form.get('name', '').strip()
        profile.user.phone = request.form.get('phone', '').strip() or None

        # Update profile
        birth_date_str = request.form.get('birth_date', '').strip()
        if birth_date_str:
            try:
                profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        else:
            profile.birth_date = None

        profile.is_kid_pitch_eligible = request.form.get('is_kid_pitch_eligible') == 'on'
        profile.status = request.form.get('status', 'active')

        # Eligibility by sport/age_rank
        max_bb = request.form.get('max_baseball_age_rank', '').strip()
        profile.max_baseball_age_rank = int(max_bb) if max_bb else None

        max_sb = request.form.get('max_softball_age_rank', '').strip()
        profile.max_softball_age_rank = int(max_sb) if max_sb else None

        # Excluded leagues
        excluded_ids = request.form.getlist('excluded_leagues')
        profile.excluded_league_ids = [int(x) for x in excluded_ids if x]

        # Parent contacts
        profile.parent_name = request.form.get('parent_name', '').strip() or None
        profile.parent_email = request.form.get('parent_email', '').strip() or None
        profile.parent_phone = request.form.get('parent_phone', '').strip() or None

        try:
            db.session.commit()
            logger.info(f'Updated umpire: {profile.full_name} (ID: {profile.id})')
            flash(f'Updated umpire: {profile.full_name}', 'success')
            return redirect(url_for('umpires.view', id=id))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error updating umpire: {e}')
            flash(f'Error updating umpire: {str(e)}', 'error')

    # Get leagues for eligibility dropdowns
    baseball_leagues = League.get_baseball_leagues()
    softball_leagues = League.get_softball_leagues()
    all_leagues = League.get_all_active()

    return render_template(
        'umpires/edit.html',
        profile=profile,
        baseball_leagues=baseball_leagues,
        softball_leagues=softball_leagues,
        all_leagues=all_leagues
    )


# =============================================================================
# Partner Management
# =============================================================================

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
        contact_name = request.form.get('contact_name', '').strip()
        contact_email = request.form.get('contact_email', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
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
            contact_name=contact_name or None,
            contact_email=contact_email or None,
            contact_phone=contact_phone or None,
            notification_preference=notification_preference,
            active=True
        )

        db.session.add(partner)
        db.session.commit()

        logger.info(f'Added partner: {name} ({short_code})')
        flash(f'Added partner: {name}', 'success')
        return redirect(url_for('umpires.partners'))

    return render_template('umpires/add_partner.html')


@umpires_bp.route('/partners/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def edit_partner(id):
    """Edit umpire partner organization."""
    partner = UmpirePartner.query.get_or_404(id)

    if request.method == 'POST':
        partner.name = request.form.get('name', '').strip()
        partner.short_code = request.form.get('short_code', '').strip().upper()
        partner.contact_name = request.form.get('contact_name', '').strip() or None
        partner.contact_email = request.form.get('contact_email', '').strip() or None
        partner.contact_phone = request.form.get('contact_phone', '').strip() or None
        partner.notification_preference = request.form.get('notification_preference', 'weekly')
        partner.active = request.form.get('active') == 'on'

        db.session.commit()
        logger.info(f'Updated partner: {partner.name}')
        flash(f'Updated partner: {partner.name}', 'success')
        return redirect(url_for('umpires.partners'))

    return render_template('umpires/edit_partner.html', partner=partner)


# =============================================================================
# Delegation Rules
# =============================================================================

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

    if request.method == 'POST':
        academy_pct = int(request.form.get('academy_pct', 0))
        diamond_pct = int(request.form.get('diamond_pct', 0))
        dynamic_pct = int(request.form.get('dynamic_pct', 0))

        # Validate percentages sum to 100
        total = academy_pct + diamond_pct + dynamic_pct
        if total != 100:
            flash(f'Percentages must sum to 100 (currently {total})', 'error')
            return render_template('umpires/edit_delegation.html', league=league, rule=rule)

        if rule:
            rule.academy_pct = academy_pct
            rule.diamond_pct = diamond_pct
            rule.dynamic_pct = dynamic_pct
        else:
            rule = UmpireDelegationRule(
                org_id=1,
                league_id=league_id,
                academy_pct=academy_pct,
                diamond_pct=diamond_pct,
                dynamic_pct=dynamic_pct,
                active=True
            )
            db.session.add(rule)

        db.session.commit()
        logger.info(f'Updated delegation for {league.display_name}: {academy_pct}/{diamond_pct}/{dynamic_pct}')
        flash(f'Updated delegation rules for {league.display_name}', 'success')
        return redirect(url_for('umpires.delegation'))

    return render_template('umpires/edit_delegation.html', league=league, rule=rule)


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


# =============================================================================
# Schedule View
# =============================================================================

@umpires_bp.route('/schedule')
@login_required
@umpire_coordinator_required
def schedule():
    """View upcoming games with umpire assignments."""
    # Get filter params
    view_type = request.args.get('view', 'upcoming')  # upcoming, unassigned, partner

    # Base query for upcoming games
    base_query = Game.query.filter(
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

    # Get assignments for each game
    game_assignments = {}
    for game in games:
        game_assignments[game.ID] = GameUmpire.get_for_game(game.ID)

    return render_template(
        'umpires/schedule.html',
        games=games,
        game_assignments=game_assignments,
        view_type=view_type
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
    """Set the umpire source for a game via right-click menu."""
    data = request.get_json()
    game_id = data.get('game_id')
    source = data.get('source')  # 'academy', 'diamond', 'dynamic'

    if source not in ['academy', 'diamond', 'dynamic']:
        return jsonify({'error': 'Invalid source'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    game.umpire_override = source
    db.session.commit()

    logger.info(f'Set umpire source for game {game_id} to {source}')
    return jsonify({'success': True, 'source': source})


# =============================================================================
# Umpire Calendar View
# =============================================================================

@umpires_bp.route('/<int:year>/<int:is_spring>/calendar')
@login_required
@umpire_coordinator_required
def umpire_calendar(year, is_spring):
    """Calendar view for umpire coordination - assign umpire sources to games."""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get week parameter (ISO week number) or default to current week
    week_param = request.args.get('week')

    # Get league filter
    league = request.args.get('league')

    # Determine the date range for this season
    from app.models.league_season import LeagueSeason
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

    # Build week days with games
    week_days = []

    for i in range(7):
        day_date = week_start + timedelta(days=i)

        # Get games from database - only games that need umpires (regular/playoff)
        query = Game.query.filter(
            Game.active == 1,
            Game.year == year,
            Game.is_spring == is_spring,
            db.func.date(Game.game_date) == day_date,
            Game.game_type.in_(['regular', 'playoff'])
        )
        if league:
            query = query.filter(Game.league == league)

        day_games = query.order_by(Game.game_date, Game.location).all()

        week_days.append({
            'date': day_date,
            'is_today': day_date == today,
            'games': day_games
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
