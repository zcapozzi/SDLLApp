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
from app.models.umpire_guardian import UmpireGuardian
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
        # Include both profiles with users and managed profiles (no user)
        profiles = UmpireProfile.query.outerjoin(User).filter(
            db.or_(User.active == 1, UmpireProfile.user_id.is_(None))
        ).all()
    else:
        profiles = UmpireProfile.query.filter_by(status=status_filter).outerjoin(User).filter(
            db.or_(User.active == 1, UmpireProfile.user_id.is_(None))
        ).all()

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


@umpires_bp.route('/add-managed', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def add_managed():
    """Add a managed umpire (youth without their own email, managed by a parent)."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        guardian_email = request.form.get('guardian_email', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        relationship = request.form.get('relationship', 'parent')

        # Get eligibility settings
        max_bb = request.form.get('max_baseball_age_rank')
        max_sb = request.form.get('max_softball_age_rank')

        if not name or not guardian_email:
            flash('Umpire name and guardian email are required.', 'error')
            return render_template('umpires/add_managed.html')

        # Find or create guardian user
        guardian = User.get_by_email(guardian_email)
        if not guardian:
            flash(f'No user found with email {guardian_email}. Please create the parent/guardian account first.', 'error')
            return render_template('umpires/add_managed.html')

        try:
            # Parse birth date
            birth_date = None
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Create managed profile
            profile = UmpireProfile.create_managed_profile(
                name=name,
                guardian_user_id=guardian.ID,
                birth_date=birth_date,
                max_baseball_age_rank=int(max_bb) if max_bb else None,
                max_softball_age_rank=int(max_sb) if max_sb else None,
                relationship=relationship
            )

            logger.info(f'Added managed umpire: {name} (ID: {profile.id}), guardian: {guardian.email}')
            flash(f'Added managed umpire: {name} (managed by {guardian.name or guardian.email})', 'success')

            return redirect(url_for('umpires.view', id=profile.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Error adding managed umpire: {e}')
            flash(f'Error adding managed umpire: {str(e)}', 'error')

    return render_template('umpires/add_managed.html')


@umpires_bp.route('/<int:id>/hive-off', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def hive_off(id):
    """Convert a managed umpire to their own independent account."""
    profile = UmpireProfile.query.get_or_404(id)

    if not profile.is_managed:
        flash('This umpire already has their own account.', 'error')
        return redirect(url_for('umpires.view', id=id))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        send_welcome = request.form.get('send_welcome') == 'on'

        if not email:
            flash('Email is required.', 'error')
            return render_template('umpires/hive_off.html', profile=profile)

        # Check if email already exists
        existing = User.get_by_email(email)
        if existing:
            flash(f'A user with email {email} already exists.', 'error')
            return render_template('umpires/hive_off.html', profile=profile)

        try:
            import secrets
            temp_password = secrets.token_urlsafe(12)

            # Create user account
            user = User.create_user(
                email=email,
                password=temp_password,
                name=profile.full_name,
                role='umpire'
            )

            # Link profile to new user
            profile.hive_off_to_user(user)

            logger.info(f'Hived off umpire {profile.id} to user {user.ID}')
            flash(f'{profile.full_name} now has their own account: {email}', 'success')

            if send_welcome:
                # Import here to avoid circular import
                from app.admin.routes import send_welcome_email
                token = user.generate_reset_token()
                send_welcome_email(user, token)
                flash('Welcome email sent.', 'success')

            return redirect(url_for('umpires.view', id=id))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Error hiving off umpire: {e}')
            flash(f'Error: {str(e)}', 'error')

    return render_template('umpires/hive_off.html', profile=profile)


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
    from app.models.partner_contact import PartnerContact

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


# =============================================================================
# Schedule View
# =============================================================================

@umpires_bp.route('/schedule')
@login_required
@umpire_coordinator_required
def schedule():
    """View upcoming games with umpire assignments."""
    from sqlalchemy.orm import joinedload

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


# =============================================================================
# Delegation Report - Costs by Partner and League
# =============================================================================

@umpires_bp.route('/delegation/report')
@umpires_bp.route('/delegation/report/<int:year>/<int:is_spring>')
@login_required
@umpire_coordinator_required
def delegation_report(year=None, is_spring=None):
    """
    Report showing game counts and costs by umpire partner and league.

    Shows:
    - Game counts by league and partner (SDL, DIA, DYN, etc.)
    - Cost calculations based on per-game rates
    - Blended rates per league
    - Accounts for 1-umpire vs 2-umpire games
    """
    from sqlalchemy import func, case
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
    games = Game.query.filter(
        Game.year == year,
        Game.is_spring == (is_spring == 1),
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage'])
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

    logger.info(f'Set umpire source for game {game_id} to {source} (notifications queued: {notifications_queued})')
    return jsonify({'success': True, 'source': source, 'notifications_queued': notifications_queued})


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

    game.umpire_count_override = count
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


# =============================================================================
# Umpire Calendar View
# =============================================================================

@umpires_bp.route('/<int:year>/<int:is_spring>/calendar')
@login_required
@umpire_coordinator_required
def umpire_calendar(year, is_spring):
    """Calendar view for umpire coordination - assign umpire sources to games."""
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

    # Query all games for the week in ONE query with eager loading
    from sqlalchemy.orm import joinedload
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
    from app.models.league import League
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


# =============================================================================
# Umpire Day View
# =============================================================================

@umpires_bp.route('/<int:year>/<int:is_spring>/day')
@umpires_bp.route('/<int:year>/<int:is_spring>/day/<date>')
@login_required
@umpire_coordinator_required
def umpire_day_view(year, is_spring, date=None):
    """Day view for umpire coordination - single day focus for game assignments."""
    from sqlalchemy.orm import joinedload

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
# Weekly Digests - Partner Email Notifications
# =============================================================================

@umpires_bp.route('/<int:year>/<int:is_spring>/digests')
@login_required
@umpire_coordinator_required
def weekly_digests(year, is_spring):
    """List weekly digests for the season."""
    from collections import defaultdict
    from app.models.weekly_digest import WeeklyDigest
    from app.models.league_season import LeagueSeason

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get all digests for this season
    digests = WeeklyDigest.get_for_season(year, is_spring, limit=100)

    # Group by week
    digests_by_week = defaultdict(list)
    for digest in digests:
        digests_by_week[digest.week_start].append(digest)

    # Sort weeks descending
    weeks = sorted(digests_by_week.keys(), reverse=True)

    # Get available seasons
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()
    seasons = [
        {'year': y, 'is_spring': s, 'name': f'{"Spring" if s else "Fall"} {y}'}
        for y, s in seasons
    ]

    return render_template(
        'umpires/weekly_digests.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        weeks=weeks,
        digests_by_week=digests_by_week,
        seasons=seasons
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/<int:id>')
@login_required
@umpire_coordinator_required
def digest_preview(year, is_spring, id):
    """Preview a specific digest."""
    from app.models.weekly_digest import WeeklyDigest

    digest = WeeklyDigest.query.get_or_404(id)
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    return render_template(
        'umpires/digest_preview.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        digest=digest
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/<int:id>', methods=['POST'])
@login_required
@umpire_coordinator_required
def digest_action(year, is_spring, id):
    """Handle digest actions: approve, send, skip, regenerate."""
    from app.models.weekly_digest import WeeklyDigest
    from app.services.weekly_digest_service import WeeklyDigestService

    digest = WeeklyDigest.query.get_or_404(id)
    action = request.form.get('action')

    service = WeeklyDigestService()

    if action == 'approve':
        digest.approve(current_user.ID)
        flash(f'Digest approved for {digest.partner_name}', 'success')

    elif action == 'send':
        if service.send_digest(digest, current_user.ID):
            flash(f'Digest sent to {digest.partner_name}', 'success')
        else:
            flash(f'Failed to send digest. Check email configuration.', 'error')

    elif action == 'skip':
        digest.mark_skipped(current_user.ID)
        flash(f'Digest skipped for {digest.partner_name}', 'success')

    elif action == 'regenerate':
        service.generate_digest_for_partner(
            digest.partner_code,
            digest.week_start,
            digest.year,
            digest.is_spring
        )
        flash(f'Digest regenerated for {digest.partner_name}', 'success')

    elif action == 'revert':
        digest.revert_to_draft()
        flash(f'Digest reverted to draft', 'success')

    return redirect(url_for('umpires.digest_preview', year=year, is_spring=is_spring, id=id))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_digests(year, is_spring):
    """Manually generate digests for the upcoming week."""
    from app.services.weekly_digest_service import WeeklyDigestService

    service = WeeklyDigestService()

    # Get target week from form or default to next week
    week_str = request.form.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            week_start = service.get_next_week_monday()
    else:
        week_start = service.get_next_week_monday()

    digests = service.generate_all_digests(week_start, year, is_spring)

    sent_count = sum(1 for d in digests if d.status == 'sent')
    draft_count = sum(1 for d in digests if d.status == 'draft')
    skipped_count = sum(1 for d in digests if d.status == 'skipped')

    msg_parts = []
    if draft_count:
        msg_parts.append(f'{draft_count} draft(s)')
    if sent_count:
        msg_parts.append(f'{sent_count} auto-sent')
    if skipped_count:
        msg_parts.append(f'{skipped_count} skipped (no games)')

    flash(f'Generated digests for week of {week_start.strftime("%B %d")}: {", ".join(msg_parts)}', 'success')

    return redirect(url_for('umpires.weekly_digests', year=year, is_spring=is_spring))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/settings', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def digest_settings(year, is_spring):
    """Configure digest settings (auto-send per partner)."""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    if request.method == 'POST':
        for partner in partners:
            auto_send = request.form.get(f'auto_send_{partner.id}') == 'on'
            partner.auto_send_digest = auto_send

        db.session.commit()
        flash('Digest settings updated', 'success')
        return redirect(url_for('umpires.digest_settings', year=year, is_spring=is_spring))

    return render_template(
        'umpires/digest_settings.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        partners=partners
    )


# =============================================================================
# Delegation Proposals
# =============================================================================

@umpires_bp.route('/delegation/proposals')
@umpires_bp.route('/delegation/proposals/<int:year>/<int:is_spring>')
@login_required
@umpire_coordinator_required
def delegation_proposals(year=None, is_spring=None):
    """List delegation proposals for a season."""
    from app.models.delegation_proposal import DelegationProposal
    from app.services.delegation_proposal_service import get_undelegated_games

    if year is None:
        year = datetime.now().year
    if is_spring is None:
        is_spring = 1 if datetime.now().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get all proposals for this season
    proposals = DelegationProposal.get_for_season(year, is_spring)

    # Get undelegated games count
    undelegated_games = get_undelegated_games(year, is_spring)
    undelegated_count = len(undelegated_games)

    # Check if there's a pending proposal
    pending_proposal = DelegationProposal.get_pending_for_season(year, is_spring)

    return render_template(
        'umpires/delegation_proposals.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        proposals=proposals,
        undelegated_count=undelegated_count,
        pending_proposal=pending_proposal
    )


@umpires_bp.route('/delegation/proposals/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_delegation_proposal():
    """Generate a new delegation proposal."""
    from app.services.delegation_proposal_service import generate_proposal

    year = int(request.form.get('year', datetime.now().year))
    is_spring = int(request.form.get('is_spring', 0))

    proposal, message = generate_proposal(year, is_spring, created_by=current_user.ID)

    if proposal:
        flash(f'Generated proposal with {proposal.game_count} games', 'success')
        return redirect(url_for('umpires.delegation_proposal_review', id=proposal.id))
    else:
        flash(message, 'error')
        return redirect(url_for('umpires.delegation_proposals', year=year, is_spring=is_spring))


@umpires_bp.route('/delegation/proposals/<int:id>')
@login_required
@umpire_coordinator_required
def delegation_proposal_review(id):
    """Review a delegation proposal with ability to modify assignments."""
    from app.models.delegation_proposal import DelegationProposal
    from app.services.delegation_proposal_service import validate_tier1, validate_tier2
    from app.models.umpire_delegation import UmpireDelegationRule
    from collections import defaultdict

    proposal = DelegationProposal.query.get_or_404(id)
    season_name = f'{"Spring" if proposal.is_spring else "Fall"} {proposal.year}'

    # Get active partners for reassignment dropdown
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()
    partner_lookup = {p.id: p for p in partners}

    # Group games by partner
    games_by_partner = proposal.get_games_by_partner()

    # Get sequences for Tier I display
    sequences = proposal.get_sequences()

    # Re-validate to show current status
    tier1_valid, tier1_violations = validate_tier1(proposal)
    tier2_valid, tier2_violations = validate_tier2(proposal)

    # Build allocation data for dynamic preview
    # 1. Get all leagues in this proposal
    leagues_in_proposal = set()
    for pg in proposal.games:
        if pg.game and pg.game.league:
            leagues_in_proposal.add(pg.game.league)

    # 2. Get current season allocation stats (existing delegated games)
    # This counts ALL games with umpire_override set (not in this proposal)
    current_stats = defaultdict(lambda: defaultdict(int))  # {league: {partner_code: count}}
    existing_games = Game.query.filter(
        Game.year == proposal.year,
        Game.is_spring == proposal.is_spring,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage']),
        Game.umpire_override.isnot(None),
        Game.umpire_override != ''
    ).all()

    for game in existing_games:
        if game.league:
            code = game.umpire_override.lower()
            current_stats[game.league][code] += 1

    # 3. Get delegation rules for each league
    allocation_rules = {}  # {league: {partner_code: target_pct}}
    for league_name in leagues_in_proposal:
        league_obj = League.get_by_name(league_name)
        if league_obj:
            rule = UmpireDelegationRule.get_for_league(league_obj.ID, proposal.year, proposal.is_spring)
            if rule and rule.allocations:
                allocation_rules[league_name] = {
                    alloc.partner.short_code.lower(): alloc.percentage
                    for alloc in rule.allocations if alloc.percentage > 0
                }

    # 4. Build proposal counts by league/partner (current assignments in proposal)
    proposal_counts = defaultdict(lambda: defaultdict(int))  # {league: {partner_code: count}}
    for pg in proposal.games:
        if pg.game and pg.game.league and pg.assigned_partner:
            code = pg.assigned_partner.short_code.lower()
            proposal_counts[pg.game.league][code] += 1

    # Convert to regular dicts for JSON serialization
    current_stats = {k: dict(v) for k, v in current_stats.items()}
    proposal_counts = {k: dict(v) for k, v in proposal_counts.items()}

    # Build partner info for JS
    partners_json = [{'id': p.id, 'code': p.short_code.lower(), 'name': p.name} for p in partners]

    return render_template(
        'umpires/delegation_proposal_review.html',
        proposal=proposal,
        season_name=season_name,
        partners=partners,
        partners_json=partners_json,
        games_by_partner=games_by_partner,
        sequences=sequences,
        tier1_valid=tier1_valid,
        tier1_violations=tier1_violations,
        tier2_valid=tier2_valid,
        tier2_violations=tier2_violations,
        current_stats=current_stats,
        proposal_counts=proposal_counts,
        allocation_rules=allocation_rules,
        leagues_in_proposal=sorted(leagues_in_proposal)
    )


@umpires_bp.route('/delegation/proposals/<int:id>/accept', methods=['POST'])
@login_required
@umpire_coordinator_required
def accept_delegation_proposal(id):
    """Accept a delegation proposal and apply all assignments."""
    from app.services.delegation_proposal_service import accept_proposal

    success, message, notifications = accept_proposal(id, user_id=current_user.ID)

    if success:
        flash(f'Proposal accepted. {message}', 'success')
        # Could trigger email notifications here if notifications returned
        return redirect(url_for('umpires.delegation_proposals'))
    else:
        flash(f'Failed to accept proposal: {message}', 'error')
        return redirect(url_for('umpires.delegation_proposal_review', id=id))


@umpires_bp.route('/delegation/proposals/<int:id>/reject', methods=['POST'])
@login_required
@umpire_coordinator_required
def reject_delegation_proposal(id):
    """Reject a delegation proposal."""
    from app.services.delegation_proposal_service import reject_proposal

    success, message = reject_proposal(id, user_id=current_user.ID)

    if success:
        flash('Proposal rejected', 'success')
    else:
        flash(f'Failed to reject proposal: {message}', 'error')

    return redirect(url_for('umpires.delegation_proposals'))


@umpires_bp.route('/api/delegation-proposals/<int:id>/update-game', methods=['POST'])
@login_required
@umpire_coordinator_required
def update_proposal_game_assignment(id):
    """Update a game's partner assignment in a proposal.

    If the game is part of a back-to-back sequence, all games in the
    sequence will be updated to maintain Tier I compliance.

    Special case: partner_id=0 means "No Umpire" - sets umpire_count_override=0
    and removes the game from the proposal.
    """
    from app.services.delegation_proposal_service import update_game_assignment, mark_game_no_umpire

    data = request.get_json()
    game_id = data.get('game_id')
    new_partner_id = data.get('partner_id')

    if not game_id:
        return jsonify({'success': False, 'error': 'Missing game_id'}), 400

    if new_partner_id is None:
        return jsonify({'success': False, 'error': 'Missing partner_id'}), 400

    # Handle "No Umpire" case (partner_id = 0)
    if new_partner_id == 0:
        success, message, removed_games = mark_game_no_umpire(id, game_id)
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'removed_games': removed_games,
                'action': 'removed'
            })
        else:
            return jsonify({'success': False, 'error': message}), 400

    # Normal partner assignment
    success, message, updated_games = update_game_assignment(id, game_id, new_partner_id)

    if success:
        return jsonify({
            'success': True,
            'message': message,
            'updated_games': updated_games
        })
    else:
        return jsonify({'success': False, 'error': message}), 400
