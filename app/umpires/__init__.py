"""Umpires blueprint - umpire management for coordinators.

Provides admin interfaces for:
- Managing umpire profiles
- Managing umpire partners (Diamond, Dynamic)
- Configuring delegation rules
- Viewing assignment status
- Weekly digests
- Delegation proposals
"""

from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user
from functools import wraps

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


# Import all routes to register them with the blueprint
from . import management, partners, delegation, assignments, digests, proposals
