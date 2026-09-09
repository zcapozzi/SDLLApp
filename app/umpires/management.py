"""Umpire profile management routes.

Handles:
- Listing umpire profiles
- Adding new umpires (with user accounts)
- Adding managed umpires (youth without email)
- Editing profiles
- Hiving off managed umpires to their own accounts
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime

from app.extensions import db
from app.models.user import User
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_partner import UmpirePartner
from app.models.game_umpire import GameUmpire
from app.models.league import League
from app.models.game import Game

from . import umpires_bp, umpire_coordinator_required, logger


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

    # Find users with umpire role who don't have profiles yet
    profile_user_ids = [p.user_id for p in profiles if p.user_id]
    users_without_profiles = User.query.filter(
        User.active == 1,
        User.role.like('%umpire%'),
        ~User.ID.in_(profile_user_ids) if profile_user_ids else True
    ).all()

    return render_template(
        'umpires/index.html',
        profiles=profiles,
        partners=partners,
        status_filter=status_filter,
        users_without_profiles=users_without_profiles
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

            # Set payment IDs if provided
            venmo_id = request.form.get('venmo_id', '').strip()
            paypal_id = request.form.get('paypal_id', '').strip()
            zelle_id = request.form.get('zelle_id', '').strip()
            if venmo_id:
                profile.venmo_id = venmo_id
            if paypal_id:
                profile.paypal_id = paypal_id
            if zelle_id:
                profile.zelle_id = zelle_id

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


@umpires_bp.route('/create-profile/<int:user_id>', methods=['POST'])
@login_required
@umpire_coordinator_required
def create_profile_for_user(user_id):
    """Create an umpire profile for an existing user with umpire role."""
    user = User.query.get_or_404(user_id)

    # Check if profile already exists
    existing = UmpireProfile.get_by_user_id(user_id)
    if existing:
        flash(f'{user.name or user.email} already has an umpire profile.', 'warning')
        return redirect(url_for('umpires.view', id=existing.id))

    try:
        profile = UmpireProfile(
            user_id=user_id,
            status=UmpireProfile.STATUS_ACTIVE
        )
        db.session.add(profile)
        db.session.commit()

        logger.info(f'Created umpire profile for user {user_id}: {user.name or user.email}')
        flash(f'Created umpire profile for {user.name or user.email}', 'success')
        return redirect(url_for('umpires.edit', id=profile.id))

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creating profile for user {user_id}: {e}')
        flash(f'Error creating profile: {str(e)}', 'error')
        return redirect(url_for('umpires.index'))


@umpires_bp.route('/add-managed', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def add_managed():
    """Add a managed umpire (youth without their own email, managed by a parent)."""
    # Get leagues for eligibility dropdowns
    baseball_leagues = League.get_baseball_leagues()
    softball_leagues = League.get_softball_leagues()

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        guardian_email = request.form.get('guardian_email', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        relationship = request.form.get('relationship', 'parent')

        # Get eligibility settings
        max_bb = request.form.get('max_baseball_age_rank')
        max_sb = request.form.get('max_softball_age_rank')

        if not first_name or not last_name or not guardian_email:
            flash('First name, last name, and guardian email are required.', 'error')
            return render_template('umpires/add_managed.html',
                                   baseball_leagues=baseball_leagues,
                                   softball_leagues=softball_leagues)

        # Find or create guardian user
        guardian = User.get_by_email(guardian_email)
        if not guardian:
            flash(f'No user found with email {guardian_email}. Please create the parent/guardian account first.', 'error')
            return render_template('umpires/add_managed.html',
                                   baseball_leagues=baseball_leagues,
                                   softball_leagues=softball_leagues)

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
                first_name=first_name,
                last_name=last_name,
                guardian_user_id=guardian.ID,
                birth_date=birth_date,
                max_baseball_age_rank=int(max_bb) if max_bb else None,
                max_softball_age_rank=int(max_sb) if max_sb else None,
                relationship=relationship
            )

            full_name = f"{first_name} {last_name}"
            logger.info(f'Added managed umpire: {full_name} (ID: {profile.id}), guardian: {guardian.email}')
            flash(f'Added managed umpire: {full_name} (managed by {guardian.name or guardian.email})', 'success')

            return redirect(url_for('umpires.view', id=profile.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Error adding managed umpire: {e}')
            flash(f'Error adding managed umpire: {str(e)}', 'error')

    return render_template('umpires/add_managed.html',
                           baseball_leagues=baseball_leagues,
                           softball_leagues=softball_leagues)


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
        # Update name - store first/last on profile for all umpires
        profile.first_name = request.form.get('first_name', '').strip()
        profile.last_name = request.form.get('last_name', '').strip()

        # For regular umpires, also sync to user.name and handle phone
        if not profile.is_managed and profile.user:
            profile.user.name = f"{profile.first_name} {profile.last_name}".strip()
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

        # Parent contacts (only for regular umpires - managed use guardians)
        if not profile.is_managed:
            profile.parent_name = request.form.get('parent_name', '').strip() or None
            profile.parent_email = request.form.get('parent_email', '').strip() or None
            profile.parent_phone = request.form.get('parent_phone', '').strip() or None

        # Payment IDs
        profile.venmo_id = request.form.get('venmo_id', '').strip() or None
        profile.paypal_id = request.form.get('paypal_id', '').strip() or None
        profile.zelle_id = request.form.get('zelle_id', '').strip() or None

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
