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


def get_view_as_user():
    """Get the user being impersonated via ?view_as=email parameter.

    Only works for product admins. Returns None if not impersonating.
    """
    return getattr(g, '_view_as_user', None)


def get_effective_user():
    """Get the effective user for permission checks.

    Returns the impersonated user if view_as is active, otherwise current_user.
    """
    view_as_user = get_view_as_user()
    if view_as_user:
        return view_as_user
    return current_user


def setup_view_as():
    """Set up view-as role/user simulation for this request.

    Call this in before_request. Only product admins can use this feature.

    Supports:
    - ?view_as=role_name - Simulate having only that role
    - ?view_as=email@example.com - Impersonate a specific user
    """
    view_as = request.args.get('view_as')
    if view_as and is_product_admin():
        from app.models.user import User

        # Check if it's an email address (contains @)
        if '@' in view_as:
            # Impersonate a specific user
            target_user = User.get_by_email(view_as)
            if target_user:
                g._view_as_user = target_user
                # Also set their roles for role checks
                g._view_as_role = None  # Clear role override, use user's actual roles
        elif view_as in User.ROLES:
            # Simulate a specific role
            g._view_as_role = view_as


def has_role_with_override(user, *check_roles):
    """Check if user has role, considering view_as override.

    When a product admin is using ?view_as=Role, this returns True
    only if the simulated role matches.

    When impersonating a user via email, uses that user's actual roles.
    """
    # Check for user impersonation first
    view_as_user = get_view_as_user()
    if view_as_user:
        # Use the impersonated user's actual roles
        return view_as_user._original_has_role(*check_roles)

    # Check for role simulation
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


def role_required(*roles):
    """Decorator to require user to have at least one of the specified roles.

    Usage:
        @role_required('admin')
        def admin_only():
            ...

        @role_required('admin', 'scheduler')  # OR logic - either role works
        def admin_or_scheduler():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if not current_user.has_role(*roles):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
