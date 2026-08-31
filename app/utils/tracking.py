"""Page view tracking utilities for authenticated routes."""

import hashlib
import secrets
from flask import request
from flask_login import current_user


def log_authenticated_view(page_type, page_context=None):
    """Log a page view for an authenticated user.

    This is a helper for tracking authenticated routes. It fails silently
    to avoid disrupting the user experience if tracking fails.

    Args:
        page_type: Type of page (e.g., 'dashboard', 'scheduler', 'umpire_calendar')
        page_context: Optional context (e.g., season info, team token)

    Example:
        @app.route('/dashboard')
        @login_required
        def dashboard():
            log_authenticated_view('dashboard')
            # ... rest of route
    """
    if not current_user.is_authenticated:
        return

    try:
        from app.models.analytics import PageView
        from app.extensions import db

        # Get or create session ID from cookie
        session_id = request.cookies.get('sdll_session')
        if not session_id:
            session_id = secrets.token_urlsafe(32)

        # Get user agent
        user_agent = request.headers.get('User-Agent', '')[:500]

        # Hash IP address for privacy
        ip_hash = None
        if request.remote_addr:
            ip_hash = hashlib.sha256(request.remote_addr.encode()).hexdigest()

        # Create page view
        view = PageView(
            page_type=page_type,
            page_context=page_context,
            session_id=session_id,
            user_id=current_user.ID,
            ip_hash=ip_hash,
            user_agent=user_agent,
            device_type=PageView._detect_device_type(user_agent),
            referrer=request.headers.get('Referer', '')[:500]
        )
        db.session.add(view)
        db.session.commit()
    except Exception:
        # Fail silently - tracking should never break the app
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
