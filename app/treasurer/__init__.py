"""Treasurer blueprint - financial views for umpire payments.

Provides treasurer-specific interfaces for:
- Viewing umpire delegation costs (via delegation report)
- Viewing managed umpire game counts and payments from Assignr
"""

from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user
from functools import wraps

from app.utils.logging import SDLLLogger

treasurer_bp = Blueprint('treasurer', __name__)
logger = SDLLLogger('treasurer')


def treasurer_required(f):
    """Decorator to require treasurer or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_treasurer():
            flash('You do not have permission to access treasurer functions.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# Import routes to register them with the blueprint
from . import routes
