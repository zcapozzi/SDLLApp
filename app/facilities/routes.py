"""Facilities management routes.

Provides interfaces for:
- Field captain assignments
- Field schedules (placeholder)
- Facilities oversight
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps

from app.extensions import db
from app.models.user import User
from app.models.field import Field
from app.models.field_captain import FieldCaptain
from app.utils.logging import SDLLLogger

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
@login_required
@facilities_required
def field_schedules():
    """Field schedules - placeholder."""
    return render_template('facilities/field_schedules.html')


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
