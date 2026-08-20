"""Error handling utilities with Tier I/II reporting.

Tier I: Critical errors requiring immediate attention
    - Sent immediately via Telegram
    - Examples: Database connection failures, authentication system errors

Tier II: Non-critical errors for periodic digest
    - Collected and emailed daily/weekly
    - Examples: Analytics tracking failures, minor validation errors

CRITICAL: Error handling must NEVER crash the user's request.
Analytics and tracking should fail silently. User-facing pages must always load.
"""

import sys
import os
import traceback
import subprocess
from datetime import datetime
from functools import wraps


# Tier definitions
TIER_CRITICAL = 1
TIER_DIGEST = 2

# Contexts that should trigger Tier I (critical) alerts
TIER1_CONTEXTS = {
    'database_connection',
    'authentication_failure',
    'payment_processing',
    'schedule_corruption',
    'data_integrity',
    'security_violation',
}


def _get_traceback_str():
    """Get abbreviated traceback string (last 5 frames)."""
    try:
        tb_lines = traceback.format_exc().strip().split('\n')
        if len(tb_lines) > 10:
            return '\n'.join(tb_lines[-10:])
        return '\n'.join(tb_lines)
    except Exception:
        return ''


def _determine_tier(context):
    """Determine error tier based on context."""
    if context in TIER1_CONTEXTS:
        return TIER_CRITICAL
    return TIER_DIGEST


def _send_tier1_alert(context, error, request=None):
    """
    Send immediate Telegram alert for Tier I errors.

    Uses the external send_message.py script for Telegram alerts.
    Fails silently if the script doesn't exist or fails.
    """
    try:
        script_path = r"C:\Users\zcapo\Documents\workspace\send_message.py"

        # Only try to send if script exists
        if not os.path.exists(script_path):
            return False

        error_type = type(error).__name__
        request_info = ""
        if request:
            request_info = f" | {request.method} {request.path}"

        message = f"🚨 TIER I ERROR<BR><BR>"
        message += f"Context: {context}<BR>"
        message += f"Error: {error_type}: {str(error)[:200]}<BR>"
        if request_info:
            message += f"Request: {request_info}<BR>"
        message += f"Time: {datetime.utcnow().isoformat()}"

        # Run the send_message script asynchronously (don't block)
        subprocess.Popen(
            ['python', script_path, '-msg', message, '--telegram-alert'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True

    except Exception:
        # Never let alerting crash
        return False


def log_error(context, error, request=None, user_id=None, tier=None):
    """Log an error without raising or crashing.

    This logs to stderr (captured by Railway) and stores in the database
    for Tier I/II reporting.

    Args:
        context: String describing what was happening (e.g., "page_view_tracking")
        error: The exception that occurred
        request: Optional Flask request object for additional context
        user_id: Optional user ID if logged in
        tier: Override tier (1 or 2). If None, determined automatically.

    Returns:
        AppError instance or None
    """
    app_error = None

    # Always log to stderr (Railway captures this)
    try:
        timestamp = datetime.utcnow().isoformat()
        request_info = ""
        if request:
            request_info = f" | {request.method} {request.path}"

        actual_tier = tier if tier is not None else _determine_tier(context)
        tier_label = "TIER-I CRITICAL" if actual_tier == 1 else "TIER-II"

        print(f"[{tier_label}] {timestamp} | {context}{request_info}", file=sys.stderr, flush=True)
        print(f"  Exception: {type(error).__name__}: {error}", file=sys.stderr, flush=True)

        # Print abbreviated traceback (last 3 frames)
        tb_lines = traceback.format_exc().strip().split('\n')
        if len(tb_lines) > 6:
            print("  Traceback (last 3 frames):", file=sys.stderr, flush=True)
            for line in tb_lines[-6:]:
                print(f"    {line}", file=sys.stderr, flush=True)
        else:
            for line in tb_lines:
                print(f"    {line}", file=sys.stderr, flush=True)

        sys.stderr.flush()
    except Exception:
        # Even error logging shouldn't crash
        pass

    # Try to store in database
    try:
        from app.models.app_error import AppError

        actual_tier = tier if tier is not None else _determine_tier(context)
        tb_str = _get_traceback_str()

        app_error = AppError.log(
            tier=actual_tier,
            context=context,
            error=error,
            request=request,
            user_id=user_id,
            traceback_str=tb_str
        )

        # Send immediate alert for Tier I
        if actual_tier == TIER_CRITICAL:
            _send_tier1_alert(context, error, request)

    except Exception:
        # Database might be unavailable - don't crash
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass

    return app_error


def log_tier1(context, error, request=None, user_id=None):
    """Force-log as Tier I (critical) error with immediate alert."""
    return log_error(context, error, request, user_id, tier=TIER_CRITICAL)


def log_tier2(context, error, request=None, user_id=None):
    """Force-log as Tier II (digest) error."""
    return log_error(context, error, request, user_id, tier=TIER_DIGEST)


def safe_tracking(func):
    """Decorator for tracking functions that must never crash.

    Usage:
        @safe_tracking
        def log_page_view(...):
            # If this fails, returns None instead of crashing
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_error(f"tracking.{func.__name__}", e)
            # Try to rollback if there's a DB session issue
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass
            return None
    return wrapper


def safe_operation(context):
    """Decorator factory for operations that should fail silently.

    Usage:
        @safe_operation("import_teams")
        def import_team_data(...):
            # If this fails, logs error and returns None

    Args:
        context: String describing the operation for error logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_error(f"{context}.{func.__name__}", e)
                try:
                    from app.extensions import db
                    db.session.rollback()
                except Exception:
                    pass
                return None
        return wrapper
    return decorator


class safe_db_operation:
    """Context manager for database operations that should fail silently.

    Usage:
        with safe_db_operation("log_page_view") as ctx:
            page_view = PageView.log_view(...)
            db.session.commit()
            ctx.result = page_view

        if ctx.success:
            # Operation completed
            use(ctx.result)

    If anything fails, the session is rolled back and execution continues.
    """

    def __init__(self, name):
        self.name = name
        self.result = None
        self.success = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            log_error(f"db.{self.name}", exc_val)
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass
            # Suppress the exception - don't crash
            return True
        self.success = True
        return False


def register_global_handler(app):
    """Register global error handlers for the Flask app.

    This catches unhandled exceptions and logs them appropriately,
    while still returning a user-friendly error page.

    Call this from app/__init__.py create_app()
    """
    @app.errorhandler(500)
    def handle_500(error):
        from flask import render_template, request
        from flask_login import current_user

        user_id = current_user.id if current_user.is_authenticated else None

        # Log as Tier I since 500 errors are serious
        log_tier1('unhandled_500', error, request, user_id)

        try:
            return render_template('errors/500.html'), 500
        except Exception:
            # If even the error template fails, return plain text
            return "An error occurred. We've been notified.", 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        from flask import render_template, request
        from flask_login import current_user

        # Don't log HTTP exceptions (404, 403, etc.) as Tier I
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return error

        user_id = current_user.id if current_user.is_authenticated else None

        # Log as Tier I - unhandled exceptions are serious
        log_tier1('unhandled_exception', error, request, user_id)

        try:
            return render_template('errors/500.html'), 500
        except Exception:
            return "An error occurred. We've been notified.", 500


def get_error_digest_html(since_hours=24):
    """Generate HTML digest of recent Tier II errors for email.

    Args:
        since_hours: Look back this many hours

    Returns:
        HTML string suitable for email body
    """
    try:
        from app.models.app_error import AppError

        summary = AppError.get_digest_summary(since_hours)

        if summary['total_count'] == 0:
            return None  # No errors to report

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #333;">SDLL Error Digest</h2>
        <p>Errors in the last {since_hours} hours: <strong>{summary['total_count']}</strong></p>

        <h3>By Context</h3>
        <ul>
        """
        for ctx, count in sorted(summary['by_context'].items(), key=lambda x: -x[1]):
            html += f"<li><strong>{ctx}</strong>: {count}</li>"
        html += "</ul>"

        html += """
        <h3>By Error Type</h3>
        <ul>
        """
        for etype, count in sorted(summary['by_type'].items(), key=lambda x: -x[1]):
            html += f"<li><strong>{etype}</strong>: {count}</li>"
        html += "</ul>"

        if summary['sample_errors']:
            html += """
            <h3>Sample Errors</h3>
            <table style="border-collapse: collapse; width: 100%;">
            <tr style="background: #f5f5f5;">
                <th style="padding: 8px; border: 1px solid #ddd;">Time</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Context</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Error</th>
            </tr>
            """
            for err in summary['sample_errors']:
                time_str = err.created_at.strftime('%Y-%m-%d %H:%M')
                html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{time_str}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{err.context}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{err.error_type}: {err.error_message[:100]}</td>
                </tr>
                """
            html += "</table>"

        html += """
        <p style="margin-top: 20px; color: #666;">
        <a href="https://www.southdurhamlittleleague.org/admin/errors">View all errors</a>
        </p>
        </body>
        </html>
        """

        return html

    except Exception:
        return None
