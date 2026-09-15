"""Authentication utilities and decorators."""

import os
from functools import wraps
from flask import redirect, url_for, flash, request, g
from flask_login import current_user


def is_product_admin():
    """Check if current user is a product admin.

    Product admins are defined by the PRODUCT_ADMIN_EMAILS environment variable.
    """
    if not current_user.is_authenticated:
        return False

    allowed = os.environ.get('PRODUCT_ADMIN_EMAILS', '').split(',')
    allowed_emails = [e.strip().lower() for e in allowed if e.strip()]

    user_email = current_user.email.lower() if current_user.email else ''
    return user_email in allowed_emails


def get_view_as_role():
    """Get the role being simulated via ?view_as= parameter.

    Only works for product admins. Returns None if not simulating.
    """
    return getattr(g, '_view_as_role', None)


def setup_view_as():
    """Set up view-as role simulation for this request.

    Call this in before_request. Only product admins can use this feature.
    """
    view_as = request.args.get('view_as')
    if view_as and is_product_admin():
        from app.models.user import User
        if view_as in User.ROLES:
            g._view_as_role = view_as


def has_role_with_override(user, *check_roles):
    """Check if user has role, considering view_as override.

    When a product admin is using ?view_as=Role, this returns True
    only if the simulated role matches.
    """
    view_as = get_view_as_role()
    if view_as:
        # When simulating, only return True if the simulated role matches
        return view_as in check_roles

    # Normal role check
    return user._original_has_role(*check_roles)


def product_admin_required(f):
    """Decorator to require product admin access.

    Product admins are defined by the PRODUCT_ADMIN_EMAILS environment variable,
    which is a comma-separated list of email addresses.

    Usage:
        @product_admin_required
        def analytics_dashboard():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not is_product_admin():
            flash('Product admin access required.', 'error')
            return redirect(url_for('main.dashboard'))

        return f(*args, **kwargs)
    return decorated
