"""Authentication utilities and decorators."""

import os
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


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

        allowed = os.environ.get('PRODUCT_ADMIN_EMAILS', '').split(',')
        allowed_emails = [e.strip().lower() for e in allowed if e.strip()]

        user_email = current_user.email.lower() if current_user.email else ''

        if user_email not in allowed_emails:
            flash('Product admin access required.', 'error')
            return redirect(url_for('main.dashboard'))

        return f(*args, **kwargs)
    return decorated
