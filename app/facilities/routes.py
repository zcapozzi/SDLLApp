"""Facilities management routes.

Provides interfaces for:
- Field captain assignments
- Field schedules (placeholder)
- Facilities oversight
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date, timedelta

from app.extensions import db
from app.models.user import User
from app.models.field import Field
from app.models.field_captain import FieldCaptain
from app.models.game import Game
from app.utils.logging import SDLLLogger
from app.services.notification_service import GmailService

from . import facilities_bp

logger = SDLLLogger('facilities')


def facilities_required(f):
    """Decorator to require facilities, fieldCaptain, or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.has_role('admin', 'facilities', 'fieldCaptain'):
            flash('You do not have permission to access facilities management.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def facilities_admin_required(f):
    """Decorator to require facilities or admin role (not just fieldCaptain)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.has_role('admin', 'facilities'):
            flash('You do not have permission to manage field captains.', 'error')
            return redirect(url_for('facilities.index'))
        return f(*args, **kwargs)
    return decorated_function


@facilities_bp.route('/')
@login_required
@facilities_required
def index():
    """Facilities dashboard."""
    # Get fields the current user is captain of (if fieldCaptain)
    my_fields = []
    if current_user.has_role('fieldCaptain'):
        my_fields = FieldCaptain.get_fields_for_user(current_user.ID)

    # For facilities/admin, show overview
    is_admin = current_user.has_role('admin', 'facilities')

    return render_template(
        'facilities/index.html',
        my_fields=my_fields,
        is_admin=is_admin
    )


@facilities_bp.route('/field-schedules')
def field_schedules():
    """Field schedules for field captains and facilities managers."""
    # Check authentication - show landing page if not logged in
    if not current_user.is_authenticated:
        login_url = url_for('auth.login', next=request.url)
        return render_template('facilities/field_schedules_landing.html', login_url=login_url)

    # Check authorization - must have facilities role
    if not current_user.has_role('admin', 'facilities', 'fieldCaptain'):
        flash('You do not have permission to access field schedules.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get date range from query params (default: start=today, no end date)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    today = date.today()
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today
    else:
        start_date = today

    # End date is optional - None means show all future games
    end_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # Determine which fields to show
    is_admin = current_user.has_role('admin', 'facilities')

    if is_admin:
        # Admin/facilities see all active fields
        fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()
    else:
        # Field captains see only their assigned fields
        fields = FieldCaptain.get_fields_for_user(current_user.ID)

    # Get field IDs for query
    field_ids = [f.ID for f in fields]

    # Get games for these fields in the date range
    games = []
    if field_ids:
        query = Game.query.filter(
            Game.field_id.in_(field_ids),
            Game.game_date >= datetime.combine(start_date, datetime.min.time()),
            Game.active == 1
        )
        if end_date:
            query = query.filter(Game.game_date <= datetime.combine(end_date, datetime.max.time()))
        games = query.order_by(Game.game_date).all()

    # Organize games by field
    games_by_field = {f.ID: [] for f in fields}
    for game in games:
        if game.field_id in games_by_field:
            games_by_field[game.field_id].append(game)

    return render_template(
        'facilities/field_schedules.html',
        fields=fields,
        games_by_field=games_by_field,
        start_date=start_date,
        end_date=end_date,
        is_admin=is_admin
    )


@facilities_bp.route('/field-schedules/report-issue', methods=['POST'])
@login_required
@facilities_required
def report_field_issue():
    """Report a field issue to the scheduler."""
    field_id = request.form.get('field_id', type=int)
    issue_description = request.form.get('issue_description', '').strip()

    if not field_id or not issue_description:
        flash('Field and issue description are required.', 'error')
        return redirect(url_for('facilities.field_schedules'))

    # Verify user can report on this field
    is_admin = current_user.has_role('admin', 'facilities')
    if not is_admin and not FieldCaptain.is_captain_of(current_user.ID, field_id):
        flash('You do not have permission to report issues for this field.', 'error')
        return redirect(url_for('facilities.field_schedules'))

    field = Field.query.get(field_id)
    if not field:
        flash('Field not found.', 'error')
        return redirect(url_for('facilities.field_schedules'))

    # Send email to scheduler
    try:
        gmail = GmailService()
        scheduler_email = 'scheduling@sdll.org'

        subject = f'Field Issue Report: {field.name}'
        body_text = f"""A field issue has been reported by {current_user.name or current_user.email}.

Field: {field.name}
Reporter: {current_user.name or 'Unknown'} ({current_user.email})
Date Reported: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

Issue Description:
{issue_description}

---
This report was submitted via the SDLL Field Schedules page.
"""
        body_html = f"""
<h2>Field Issue Report</h2>
<p>A field issue has been reported by <strong>{current_user.name or current_user.email}</strong>.</p>

<table style="border-collapse: collapse; margin: 20px 0;">
    <tr>
        <td style="padding: 8px 15px 8px 0; font-weight: bold;">Field:</td>
        <td style="padding: 8px 0;">{field.name}</td>
    </tr>
    <tr>
        <td style="padding: 8px 15px 8px 0; font-weight: bold;">Reporter:</td>
        <td style="padding: 8px 0;">{current_user.name or 'Unknown'} ({current_user.email})</td>
    </tr>
    <tr>
        <td style="padding: 8px 15px 8px 0; font-weight: bold;">Date Reported:</td>
        <td style="padding: 8px 0;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
    </tr>
</table>

<h3>Issue Description:</h3>
<p style="background: #f5f5f5; padding: 15px; border-radius: 4px; white-space: pre-wrap;">{issue_description}</p>

<hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
<p style="color: #666; font-size: 13px;">This report was submitted via the SDLL Field Schedules page.</p>
"""
        gmail.send_email(scheduler_email, subject, body_text, body_html, reply_to=current_user.email)

        logger.info(f'Field issue reported for {field.name} by {current_user.email}')
        flash(f'Issue reported for {field.name}. The scheduler has been notified.', 'success')

    except Exception as e:
        logger.error(f'Failed to send field issue report: {e}')
        flash('Failed to send issue report. Please try again or contact scheduling@sdll.org directly.', 'error')

    return redirect(url_for('facilities.field_schedules') + f'#field-{field_id}')


@facilities_bp.route('/captains')
@login_required
@facilities_admin_required
def captains():
    """Manage field captain assignments."""
    # Get all active fields with their captains
    fields = Field.query.filter_by(active=1).order_by(Field.location_title).all()

    # Get fields without captains
    fields_without_captains = FieldCaptain.get_fields_without_captains()

    # Get all users with fieldCaptain role for the dropdown
    field_captains = User.query.filter(
        User.active == 1,
        User.role.like('%fieldCaptain%')
    ).order_by(User._name).all()

    return render_template(
        'facilities/captains.html',
        fields=fields,
        fields_without_captains=fields_without_captains,
        field_captains=field_captains
    )


@facilities_bp.route('/captains/assign', methods=['POST'])
@login_required
@facilities_admin_required
def assign_captain():
    """Assign a captain to a field."""
    field_id = request.form.get('field_id', type=int)
    user_id = request.form.get('user_id', type=int)

    if not field_id or not user_id:
        flash('Field and user are required.', 'error')
        return redirect(url_for('facilities.captains'))

    field = Field.query.get(field_id)
    user = User.query.get(user_id)

    if not field or not user:
        flash('Invalid field or user.', 'error')
        return redirect(url_for('facilities.captains'))

    # Ensure user has fieldCaptain role
    if not user.has_role('fieldCaptain'):
        user.add_role('fieldCaptain')
        db.session.commit()

    # Create assignment
    assignment = FieldCaptain.assign_captain(user_id, field_id, current_user.ID)

    if assignment:
        logger.info(f'Assigned {user.name} as captain of {field.name}')
        flash(f'Assigned {user.name or user.email} as captain of {field.name}', 'success')
    else:
        flash(f'{user.name or user.email} is already a captain of {field.name}', 'warning')

    return redirect(url_for('facilities.captains') + f'#field-{field_id}')


@facilities_bp.route('/captains/remove', methods=['POST'])
@login_required
@facilities_admin_required
def remove_captain():
    """Remove a captain from a field."""
    field_id = request.form.get('field_id', type=int)
    user_id = request.form.get('user_id', type=int)

    if not field_id or not user_id:
        flash('Field and user are required.', 'error')
        return redirect(url_for('facilities.captains'))

    field = Field.query.get(field_id)
    user = User.query.get(user_id)

    if FieldCaptain.remove_captain(user_id, field_id):
        logger.info(f'Removed {user.name if user else user_id} as captain of {field.name if field else field_id}')
        flash(f'Removed captain from {field.name if field else "field"}', 'success')
    else:
        flash('Assignment not found.', 'error')

    return redirect(url_for('facilities.captains') + f'#field-{field_id}')


@facilities_bp.route('/captains/add-role', methods=['POST'])
@login_required
@facilities_admin_required
def add_field_captain_role():
    """Add fieldCaptain role to a user."""
    user_id = request.form.get('user_id', type=int)

    if not user_id:
        return jsonify({'success': False, 'error': 'User ID required'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if user.has_role('fieldCaptain'):
        return jsonify({'success': True, 'message': 'User already has fieldCaptain role'})

    user.add_role('fieldCaptain')
    db.session.commit()

    logger.info(f'Added fieldCaptain role to {user.name or user.email}')

    return jsonify({
        'success': True,
        'user': {
            'id': user.ID,
            'name': user.name or user.email,
            'email': user.email
        }
    })


@facilities_bp.route('/api/search-users')
@login_required
@facilities_admin_required
def search_users():
    """Search for users to add as field captains."""
    query = request.args.get('q', '').strip().lower()

    if len(query) < 2:
        return jsonify([])

    # Search active users
    users = User.query.filter(User.active == 1).all()

    results = []
    for user in users:
        name = user.name or ''
        email = user.email or ''
        if query in name.lower() or query in email.lower():
            results.append({
                'id': user.ID,
                'name': name,
                'email': email,
                'has_role': user.has_role('fieldCaptain')
            })
            if len(results) >= 10:
                break

    return jsonify(results)
