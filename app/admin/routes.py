"""Admin routes for user management and system settings"""

import secrets
import json
from datetime import date
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.coach import CoachUser
from app.models.org_season import OrgSeason
from app.services.notification_service import GmailService
from app.utils.logging import SDLLLogger

admin_bp = Blueprint('admin', __name__)
logger = SDLLLogger('admin')


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    """List and manage users"""
    if request.method == 'POST':
        action = request.form.get('action')
        anchor = None

        if action == 'add':
            return handle_add_user()
        elif action == 'edit':
            user_id = request.form.get('user_id')
            anchor = f'user-{user_id}'
            result = handle_edit_user()
            if result:
                return result
        elif action == 'send_reset':
            user_id = request.form.get('user_id')
            anchor = f'user-{user_id}'
            handle_send_reset()
        elif action == 'toggle_active':
            user_id = request.form.get('user_id')
            anchor = f'user-{user_id}'
            handle_toggle_active()
        elif action == 'add_coach':
            user_id = request.form.get('user_id')
            anchor = f'user-{user_id}'
            handle_add_coach()

        redirect_url = url_for('admin.users')
        if anchor:
            redirect_url += f'#{anchor}'
        return redirect(redirect_url)

    # GET: Display user list (filtering done client-side via JS)
    users_list = User.query.order_by(User.role, User.ID).all()

    # Build lookup of user IDs that are already coaches
    coach_records = CoachUser.query.all()
    coach_by_user = {c.user_id: c for c in coach_records}

    return render_template(
        'admin/users.html',
        users=users_list,
        roles=User.ROLES,
        coach_by_user=coach_by_user
    )


def handle_add_user():
    """Handle adding a new user"""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', 'viewer')
    send_welcome = request.form.get('send_welcome') == 'on'

    if not first_name or not last_name or not email:
        flash('First name, last name, and email are required.', 'error')
        return redirect(url_for('admin.add_user'))

    # Check if email already exists
    existing = User.get_by_email(email)
    if existing:
        flash('A user with that email already exists.', 'error')
        return redirect(url_for('admin.add_user'))

    if role not in User.ROLES:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('admin.add_user'))

    # Create user with a random temporary password
    temp_password = secrets.token_urlsafe(16)
    try:
        user = User.create_user(
            email=email,
            password=temp_password,
            name=f'{first_name} {last_name}',
            phone=phone if phone else None,
            role=role
        )
        logger.info(f'Admin {current_user.ID} created user {user.ID} with role {role}')

        if send_welcome:
            # Generate reset token and send welcome email
            token = user.generate_reset_token()
            send_welcome_email(user, token)
            flash(f'User {first_name} {last_name} created and welcome email sent.', 'success')
        else:
            flash(f'User {first_name} {last_name} created successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to create user: {str(e)}')
        flash(f'Failed to create user: {str(e)}', 'error')
        return redirect(url_for('admin.add_user'))

    return redirect(url_for('admin.users'))


def handle_edit_user():
    """Handle editing a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID is required.', 'error')
        return None

    user = db.session.get(User, int(user_id))
    if not user:
        flash('User not found.', 'error')
        return None

    is_editing_self = (user.ID == current_user.ID)

    new_email = request.form.get('email', '').strip()
    new_role = request.form.get('role')
    new_name = request.form.get('name', '').strip()
    new_phone = request.form.get('phone', '').strip()

    # Update email if provided
    if new_email and new_email != user.email:
        # Check if email is already taken by another user
        existing = User.query.filter(User.email == new_email, User.ID != user.ID).first()
        if existing:
            flash('That email is already in use by another account.', 'error')
            return None
        old_email = user.email
        user.email = new_email
        logger.info(f'Admin {current_user.ID} changed user {user.ID} email from {old_email} to {new_email}')

    # Only allow role changes for other users (not yourself)
    if not is_editing_self:
        new_roles = request.form.getlist('roles')  # Multiple checkboxes
        # Filter to valid roles only
        valid_roles = [r for r in new_roles if r in User.ROLES]
        if valid_roles:
            new_role_str = '|'.join(valid_roles)
            old_role = user.role
            if old_role != new_role_str:
                user.role = new_role_str
                logger.info(f'Admin {current_user.ID} changed user {user.ID} role from {old_role} to {new_role_str}')

    if new_name:
        user.name = new_name

    if new_phone is not None:
        user.phone = new_phone if new_phone else None

    db.session.commit()
    flash('User updated successfully.', 'success')
    return None


def handle_send_reset():
    """Handle sending password reset email"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID is required.', 'error')
        return

    user = db.session.get(User, int(user_id))
    if not user:
        flash('User not found.', 'error')
        return

    token = user.generate_reset_token()
    success = send_password_reset_email(user, token)

    if success:
        logger.info(f'Admin {current_user.ID} sent password reset to user {user.ID}')
        flash(f'Password reset link sent to {user.email}.', 'success')
    else:
        flash('Failed to send email. Email service may not be configured.', 'error')


def handle_toggle_active():
    """Handle activating/deactivating a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID is required.', 'error')
        return

    user = db.session.get(User, int(user_id))
    if not user:
        flash('User not found.', 'error')
        return

    # Prevent deactivating yourself
    if user.ID == current_user.ID:
        flash('You cannot deactivate your own account.', 'error')
        return

    user.active = 0 if user.active else 1
    db.session.commit()

    status = 'activated' if user.active else 'deactivated'
    logger.info(f'Admin {current_user.ID} {status} user {user.ID}')
    flash(f'User {status} successfully.', 'success')


def handle_add_coach():
    """Handle adding a user to the coaches table"""
    user_id = request.form.get('user_id')
    sport = request.form.get('sport')

    if not user_id:
        flash('User ID is required.', 'error')
        return

    if sport not in ['baseball', 'softball', 'both']:
        flash('Invalid sport selection.', 'error')
        return

    user = db.session.get(User, int(user_id))
    if not user:
        flash('User not found.', 'error')
        return

    # Check if user already has a coach record
    existing = CoachUser.get_by_user(user.ID)
    if existing:
        flash(f'User is already a coach ({existing.sport}).', 'warning')
        return

    # Create coach record
    coach = CoachUser(
        user_id=user.ID,
        sport=sport,
        status=CoachUser.STATUS_ACTIVE
    )
    db.session.add(coach)
    db.session.commit()

    logger.info(f'Admin {current_user.ID} added user {user.ID} as coach ({sport})')
    flash(f'{user.name} added as coach ({sport}).', 'success')


@admin_bp.route('/users/add', methods=['GET'])
@login_required
@admin_required
def add_user():
    """Display add user form"""
    return render_template('admin/add_user.html', roles=User.ROLES)


def send_welcome_email(user, token):
    """Send welcome email with password creation link"""
    gmail = GmailService()
    if not gmail.is_configured:
        logger.warning('Gmail service not configured - welcome email not sent')
        return False

    reset_url = url_for('auth.reset_password', token=token, _external=True)
    first_name = user.name.split()[0] if user.name else 'there'

    subject = "Welcome to SDLL - Set Your Password"

    body_text = f"""Hi {first_name},

An account has been created for you at South Durham Little League.

Click the link below to set your password:
{reset_url}

This link expires in 1 hour.

If you didn't expect this email, please ignore it.

- South Durham Little League
"""

    body_html = f"""<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Welcome to South Durham Little League</h2>
    <p>Hi {first_name},</p>
    <p>An account has been created for you at South Durham Little League.</p>
    <p>
        <a href="{reset_url}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Set Your Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{reset_url}">{reset_url}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
    <p style="color: #666; font-size: 14px;">
        If you didn't expect this email, please ignore it.
    </p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>"""

    try:
        gmail.send_email(user.email, subject, body_text, body_html)
        return True
    except Exception as e:
        logger.error(f'Failed to send welcome email: {str(e)}')
        return False


def send_password_reset_email(user, token):
    """Send password reset email"""
    gmail = GmailService()
    if not gmail.is_configured:
        logger.warning('Gmail service not configured - reset email not sent')
        return False

    reset_url = url_for('auth.reset_password', token=token, _external=True)
    first_name = user.name.split()[0] if user.name else 'there'

    subject = "SDLL - Password Reset"

    body_text = f"""Hi {first_name},

A password reset was requested for your South Durham Little League account.

Click the link below to reset your password:
{reset_url}

This link expires in 1 hour.

If you didn't request this, please ignore it.

- South Durham Little League
"""

    body_html = f"""<!DOCTYPE html>
<html>
<head></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #228B22;">Password Reset</h2>
    <p>Hi {first_name},</p>
    <p>A password reset was requested for your South Durham Little League account.</p>
    <p>
        <a href="{reset_url}"
           style="display: inline-block; padding: 12px 24px; background-color: #228B22; color: white;
                  text-decoration: none; border-radius: 4px; font-weight: bold;">
            Reset Password
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{reset_url}">{reset_url}</a>
    </p>
    <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
    <p style="color: #666; font-size: 14px;">
        If you didn't request this, please ignore it.
    </p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>"""

    try:
        gmail.send_email(user.email, subject, body_text, body_html)
        return True
    except Exception as e:
        logger.error(f'Failed to send reset email: {str(e)}')
        return False


@admin_bp.route('/users/import', methods=['GET'])
@login_required
@admin_required
def import_users():
    """Display bulk user import page"""
    return render_template('admin/import_users.html', roles=User.ROLES)


@admin_bp.route('/users/import/parse', methods=['POST'])
@login_required
@admin_required
def parse_import_data():
    """Parse pasted spreadsheet data and return preview"""
    data = request.json
    raw_text = data.get('text', '')
    default_role = data.get('default_role', 'viewer')

    if not raw_text.strip():
        return jsonify({'success': False, 'message': 'No data provided'})

    rows = []
    errors = []
    lines = raw_text.strip().split('\n')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Try tab-separated first, then comma
        if '\t' in line:
            parts = line.split('\t')
        else:
            parts = line.split(',')

        # Clean up parts
        parts = [p.strip().strip('"').strip("'") for p in parts]

        # Expected format: First Name, Last Name, Email, [Phone], [Role]
        # Or: Name, Email, [Phone], [Role]
        if len(parts) < 2:
            errors.append(f'Row {i+1}: Not enough columns (need at least name and email)')
            continue

        # Detect format based on whether there's an @ in the second or third column
        first_name = ''
        last_name = ''
        email = ''
        phone = ''
        role = default_role

        if len(parts) >= 3 and '@' in parts[2]:
            # Format: First, Last, Email, [Phone], [Role]
            first_name = parts[0]
            last_name = parts[1]
            email = parts[2].lower()
            if len(parts) >= 4:
                # Could be phone or role
                if parts[3] in User.ROLES:
                    role = parts[3]
                else:
                    phone = parts[3]
            if len(parts) >= 5 and parts[4] in User.ROLES:
                role = parts[4]
        elif len(parts) >= 2 and '@' in parts[1]:
            # Format: Full Name, Email, [Phone], [Role]
            name_parts = parts[0].split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
            else:
                first_name = parts[0]
                last_name = ''
            email = parts[1].lower()
            if len(parts) >= 3:
                if parts[2] in User.ROLES:
                    role = parts[2]
                else:
                    phone = parts[2]
            if len(parts) >= 4 and parts[3] in User.ROLES:
                role = parts[3]
        else:
            errors.append(f'Row {i+1}: Could not find email address')
            continue

        # Validate email format
        if '@' not in email or '.' not in email:
            errors.append(f'Row {i+1}: Invalid email format: {email}')
            continue

        # Check for duplicates in the import data
        existing_emails = [r['email'] for r in rows]
        if email in existing_emails:
            errors.append(f'Row {i+1}: Duplicate email in import: {email}')
            continue

        # Check if user already exists
        existing_user = User.get_by_email(email)
        if existing_user:
            errors.append(f'Row {i+1}: User already exists: {email}')
            continue

        rows.append({
            'row': i + 1,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'role': role
        })

    return jsonify({
        'success': True,
        'rows': rows,
        'errors': errors,
        'count': len(rows)
    })


@admin_bp.route('/users/import/confirm', methods=['POST'])
@login_required
@admin_required
def confirm_import():
    """Create users from confirmed import data"""
    data = request.json
    users_data = data.get('users', [])
    send_welcome = data.get('send_welcome', False)

    if not users_data:
        return jsonify({'success': False, 'message': 'No users to import'})

    created = []
    errors = []

    for user_data in users_data:
        email = user_data.get('email', '').lower().strip()
        first_name = user_data.get('first_name', '').strip()
        last_name = user_data.get('last_name', '').strip()
        phone = user_data.get('phone', '').strip()
        role = user_data.get('role', 'viewer')

        # Double-check user doesn't exist
        if User.get_by_email(email):
            errors.append(f'{email}: User already exists')
            continue

        if role not in User.ROLES:
            role = 'viewer'

        # Create user with random temp password
        temp_password = secrets.token_urlsafe(16)
        try:
            user = User.create_user(
                email=email,
                password=temp_password,
                name=f'{first_name} {last_name}'.strip(),
                phone=phone if phone else None,
                role=role
            )
            logger.info(f'Bulk import: Admin {current_user.ID} created user {user.ID} ({email}) with role {role}')

            if send_welcome:
                token = user.generate_reset_token()
                send_welcome_email(user, token)

            created.append({
                'email': email,
                'name': f'{first_name} {last_name}'.strip(),
                'role': role
            })

        except Exception as e:
            db.session.rollback()
            errors.append(f'{email}: {str(e)}')
            logger.error(f'Bulk import failed for {email}: {str(e)}')

    return jsonify({
        'success': True,
        'created': created,
        'created_count': len(created),
        'errors': errors,
        'error_count': len(errors)
    })


@admin_bp.route('/seasons', methods=['GET', 'POST'])
@login_required
@admin_required
def seasons():
    """Manage organization seasons"""
    from datetime import datetime

    if request.method == 'POST':
        action = request.form.get('action')
        anchor = None

        if action == 'create':
            # Create a new season
            year = int(request.form.get('year'))
            season_label = request.form.get('season_label', '').strip()
            custom_label = request.form.get('custom_label', '').strip()
            set_as_current = request.form.get('set_as_current') == 'on'
            setup_mode = request.form.get('setup_mode') == 'on'

            # Use custom label if provided, otherwise use selected label
            label = custom_label if custom_label else season_label
            if not label:
                flash('Season label is required.', 'error')
            else:
                # Build season_desc
                season_desc = f'{label} {year}'

                # Derive is_spring from label (spring-like = 1, otherwise = 0)
                spring_keywords = ['spring', 'spr', 'spring/summer', 'ss']
                is_spring = 1 if label.lower() in spring_keywords else 0

                # Check if season already exists by description
                existing = OrgSeason.query.filter_by(
                    org_id=OrgSeason.DEFAULT_ORG_ID,
                    season_desc=season_desc
                ).first()

                if existing:
                    flash(f'Season "{season_desc}" already exists.', 'error')
                else:
                    season = OrgSeason.create_season(
                        year=year,
                        is_spring=is_spring,
                        season_desc=season_desc,
                        org_id=OrgSeason.DEFAULT_ORG_ID,
                        set_as_current=set_as_current
                    )
                    if setup_mode and not set_as_current:
                        season.setup_mode = 1
                        db.session.commit()
                    logger.info(f'Admin {current_user.ID} created season {season.season_name}')
                    flash(f'Season "{season_desc}" created successfully.', 'success')
                    anchor = f'season-{season.ID}'

        elif action == 'set_current':
            season_id = int(request.form.get('season_id'))
            season = db.session.get(OrgSeason, season_id)
            if season:
                OrgSeason.set_current_season(season.year, season.is_spring, season.org_id)
                logger.info(f'Admin {current_user.ID} set {season.season_name} as current')
                flash(f'{season.season_name} is now the current season.', 'success')
                anchor = f'season-{season_id}'

        elif action == 'toggle_setup_mode':
            season_id = int(request.form.get('season_id'))
            season = db.session.get(OrgSeason, season_id)
            if season:
                season.setup_mode = 0 if season.setup_mode else 1
                db.session.commit()
                mode_str = 'enabled' if season.setup_mode else 'disabled'
                logger.info(f'Admin {current_user.ID} {mode_str} setup mode for {season.season_name}')
                flash(f'Setup mode {mode_str} for {season.season_name}.', 'success')
                anchor = f'season-{season_id}'

        elif action == 'update_dates':
            season_id = int(request.form.get('season_id'))
            season = db.session.get(OrgSeason, season_id)
            if season:
                # Parse all date fields
                date_fields = [
                    'first_practice_date', 'opening_day_date', 'training_date',
                    'season_end_date', 'registration_opens_date', 'evaluations_date', 'draft_date'
                ]
                for field in date_fields:
                    date_str = request.form.get(field, '').strip()
                    if date_str:
                        setattr(season, field, datetime.strptime(date_str, '%Y-%m-%d').date())
                    else:
                        setattr(season, field, None)

                db.session.commit()

                # Regenerate campaigns if dates changed
                season.ensure_campaigns()

                logger.info(f'Admin {current_user.ID} updated dates for {season.season_name}')
                flash(f'Dates updated for {season.season_name}.', 'success')
                anchor = f'season-{season_id}'

        elif action == 'update_training_date':
            # Legacy - redirect to update_dates
            season_id = int(request.form.get('season_id'))
            training_date_str = request.form.get('training_date', '').strip()
            season = db.session.get(OrgSeason, season_id)
            if season:
                if training_date_str:
                    season.training_date = datetime.strptime(training_date_str, '%Y-%m-%d').date()
                else:
                    season.training_date = None
                db.session.commit()
                logger.info(f'Admin {current_user.ID} updated training date for {season.season_name}')
                flash(f'Training date updated for {season.season_name}.', 'success')
                anchor = f'season-{season_id}'

        redirect_url = url_for('admin.seasons')
        if anchor:
            redirect_url += f'#{anchor}'
        return redirect(redirect_url)

    # GET: List all seasons
    all_seasons = OrgSeason.query.filter_by(
        org_id=OrgSeason.DEFAULT_ORG_ID
    ).order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).all()

    current_season = OrgSeason.get_current_season()

    # Get unique season descriptions used historically (for suggestions)
    existing_descs = db.session.query(OrgSeason.season_desc).filter_by(
        org_id=OrgSeason.DEFAULT_ORG_ID
    ).distinct().all()
    # Extract just the season type part (remove year) for suggestions
    season_labels = set()
    for (desc,) in existing_descs:
        # Try to extract label by removing year (e.g., "Spring 2026" -> "Spring")
        parts = desc.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            season_labels.add(parts[0])
        else:
            season_labels.add(desc)
    # Add defaults if not present
    season_labels.add('Spring')
    season_labels.add('Fall')
    season_labels = sorted(season_labels)

    # Suggest next season
    current_year = date.today().year
    current_month = date.today().month
    # If we're in fall (Aug-Dec), suggest next Spring; otherwise suggest next Fall
    if current_month >= 8:
        suggested_year = current_year + 1
        suggested_label = 'Spring'
    else:
        suggested_year = current_year
        suggested_label = 'Fall'

    return render_template(
        'admin/seasons.html',
        seasons=all_seasons,
        current_season=current_season,
        suggested_year=suggested_year,
        suggested_label=suggested_label,
        season_labels=season_labels
    )


# =============================================================================
# ACCESS REQUESTS - Review and approve/reject user access requests
# =============================================================================

@admin_bp.route('/access-requests', methods=['GET', 'POST'])
@login_required
@admin_required
def access_requests():
    """Review and process access requests from prospective users."""
    from app.models.access_request import AccessRequest
    from app.models.team import TeamSeason
    from app.models.org_season import OrgSeason
    from app.services.access_request_service import AccessRequestService

    service = AccessRequestService()

    if request.method == 'POST':
        action = request.form.get('action')
        request_id = request.form.get('request_id', type=int)

        if not request_id:
            flash('Request ID is required.', 'error')
            return redirect(url_for('admin.access_requests'))

        access_request = db.session.get(AccessRequest, request_id)
        if not access_request:
            flash('Request not found.', 'error')
            return redirect(url_for('admin.access_requests'))

        if action == 'approve_coach':
            # Approve coach request
            team_id = request.form.get('team_id', type=int)
            success, message, user = service.approve_coach_request(
                request_id, current_user.ID, team_id
            )
            flash(message, 'success' if success else 'error')

        elif action == 'approve_admin':
            # Approve admin request with selected roles
            roles = request.form.getlist('roles')
            if not roles:
                flash('Please select at least one role.', 'error')
                return redirect(url_for('admin.access_requests'))

            success, message, user = service.approve_admin_request(
                request_id, current_user.ID, roles
            )
            flash(message, 'success' if success else 'error')

        elif action == 'reject':
            # Reject request
            reason = request.form.get('rejection_reason', '').strip()
            send_email = request.form.get('send_rejection_email') == 'on'
            success, message = service.reject_request(
                request_id, current_user.ID, reason, send_email
            )
            flash(message, 'success' if success else 'error')

        return redirect(url_for('admin.access_requests'))

    # GET: Display pending requests
    pending_requests = AccessRequest.get_pending_requests()

    # Group by type for easier display
    coach_requests = [r for r in pending_requests if r.request_type == AccessRequest.TYPE_COACH]
    admin_requests = [r for r in pending_requests if r.request_type == AccessRequest.TYPE_ADMIN]

    # Get teams for coach assignment dropdown
    current_season = OrgSeason.get_current_season()
    teams = []
    if current_season:
        teams = TeamSeason.query.filter_by(
            year=current_season.year,
            is_spring=current_season.is_spring,
            active=1,
            is_placeholder=0
        ).order_by(TeamSeason.league, TeamSeason.display_name).all()

    # Get available roles for admin assignment
    available_roles = User.ROLES

    # Get recent processed requests for reference
    recent_processed = AccessRequest.query.filter(
        AccessRequest.status.in_([AccessRequest.STATUS_APPROVED, AccessRequest.STATUS_REJECTED])
    ).order_by(AccessRequest.processed_at.desc()).limit(20).all()

    return render_template(
        'admin/access_requests.html',
        coach_requests=coach_requests,
        admin_requests=admin_requests,
        pending_count=len(pending_requests),
        teams=teams,
        available_roles=available_roles,
        recent_processed=recent_processed
    )
