"""Knowledge blueprint - institutional knowledge and onboarding."""

from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user
from functools import wraps

from app.utils.logging import SDLLLogger

knowledge_bp = Blueprint('knowledge', __name__)
logger = SDLLLogger('knowledge')


def board_member_required(f):
    """Decorator to require any board role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Check if user has any board-level role
        board_roles = [
            'admin', 'BoardExec', 'BB_VP', 'SB_VP',
            'scheduler', 'umpire_coordinator', 'treasurer',
            'BBPlayerAgent', 'SBPlayerAgent', 'coaching_coordinator',
            'DataManager', 'facilities', 'fieldCaptain'
        ]

        if not current_user.has_role(*board_roles):
            flash('You do not have permission to access the knowledge base.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# Import routes to register them
from . import routes
