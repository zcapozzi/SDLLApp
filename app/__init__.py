"""SDLL Web Application - Flask App Factory"""

import os
import sys
import json
import traceback
from flask import Flask, jsonify, request, redirect, url_for, flash
from flask_wtf.csrf import CSRFError

from .extensions import db, login_manager, limiter, csrf, sess
from .config import config


def load_logging_config(app):
    """Load logging configuration from JSON file"""
    config_path = os.path.join(os.path.dirname(app.root_path), 'logging_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {'default': 'ON'}


def create_app(config_name=None):
    """Application factory for Flask app"""
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    sess.init_app(app)  # Server-side sessions for larger data (like schedule proposals)

    # Load logging config
    app.logging_config = load_logging_config(app)

    # Register blueprints
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .seasons.routes import seasons_bp
    from .games.routes import games_bp
    from .fields.routes import fields_bp
    from .leagues.routes import leagues_bp
    from .scheduler.routes import scheduler_bp
    from .notifications import notifications_bp
    from .reports import reports_bp
    from .public import public_bp
    from .umpires import umpires_bp
    from .umpire_portal import umpire_portal_bp
    from .admin import admin_bp
    from .facilities import facilities_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(seasons_bp, url_prefix='/seasons')
    app.register_blueprint(games_bp, url_prefix='/games')
    app.register_blueprint(fields_bp, url_prefix='/fields')
    app.register_blueprint(leagues_bp, url_prefix='/leagues')
    app.register_blueprint(scheduler_bp, url_prefix='/scheduler')
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(public_bp)  # Public team schedules (no auth required)
    app.register_blueprint(umpires_bp, url_prefix='/umpires')  # Umpire coordinator management
    app.register_blueprint(umpire_portal_bp, url_prefix='/umpire-portal')  # Umpire self-service
    app.register_blueprint(admin_bp, url_prefix='/admin')  # Admin user management
    app.register_blueprint(facilities_bp, url_prefix='/facilities')  # Facilities management

    # User loader for Flask-Login
    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Context processor for current season (used in navbar)
    @app.context_processor
    def inject_current_season():
        """Make current season available to all templates.

        Uses OrgSeason to determine the current season:
        1. First looks for a season explicitly marked as is_current=1
        2. Falls back to the season with the latest season_started_at
        3. If no OrgSeason data, falls back to LeagueSeason query
        """
        from .models.org_season import OrgSeason
        from .models.league_season import LeagueSeason

        try:
            current_season = OrgSeason.get_current_season()

            if current_season:
                return {
                    'current_season_year': current_season.year,
                    'current_season_is_spring': current_season.is_spring,
                    'current_season_name': current_season.season_name
                }
        except Exception:
            pass  # Fall through to LeagueSeason fallback

        # Fallback: query LeagueSeason directly (for when OrgSeason table is empty)
        fallback = db.session.query(
            LeagueSeason.year,
            LeagueSeason.is_spring
        ).filter_by(active=1).order_by(
            LeagueSeason.year.desc(),
            LeagueSeason.is_spring.desc()
        ).first()

        if fallback:
            return {
                'current_season_year': fallback.year,
                'current_season_is_spring': fallback.is_spring,
                'current_season_name': f'{"Spring" if fallback.is_spring else "Fall"} {fallback.year}'
            }

        return {
            'current_season_year': None,
            'current_season_is_spring': None,
            'current_season_name': None
        }

    # Custom Jinja filters for date formatting
    @app.template_filter('format_date_with_day')
    def format_date_with_day(date_str):
        """Format a date string (YYYY-MM-DD or ISO datetime) with day of week.

        Examples:
            '2026-04-15' -> 'Wed, Apr 15, 2026'
            '2026-04-15T17:30:00' -> 'Wed, Apr 15, 2026'
        """
        from datetime import datetime
        if not date_str:
            return ''
        try:
            # Handle both date-only and datetime strings
            if 'T' in date_str:
                date_obj = datetime.fromisoformat(date_str[:10])
            else:
                date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d')
            return date_obj.strftime('%a, %b %d, %Y')
        except (ValueError, TypeError):
            return date_str

    @app.template_filter('format_datetime_with_day')
    def format_datetime_with_day(dt_str):
        """Format a datetime string with day of week and time.

        Examples:
            '2026-04-15T17:30:00' -> 'Wed, Apr 15 at 5:30 PM'
        """
        from datetime import datetime
        if not dt_str:
            return ''
        try:
            dt_obj = datetime.fromisoformat(dt_str)
            return dt_obj.strftime('%a, %b %d at %I:%M %p').replace(' 0', ' ')
        except (ValueError, TypeError):
            return dt_str

    @app.template_filter('format_time')
    def format_time(dt_str):
        """Format a datetime string to 12-hour time only.

        Examples:
            '2026-04-15T17:30:00' -> '5:30 PM'
            '2026-04-15T09:00:00' -> '9:00 AM'
        """
        from datetime import datetime
        if not dt_str:
            return ''
        try:
            dt_obj = datetime.fromisoformat(dt_str)
            return dt_obj.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            # Try parsing just time portion
            try:
                if 'T' in dt_str and len(dt_str) >= 16:
                    time_part = dt_str[11:16]  # HH:MM
                    hour, minute = int(time_part[:2]), int(time_part[3:5])
                    period = 'AM' if hour < 12 else 'PM'
                    if hour == 0:
                        hour = 12
                    elif hour > 12:
                        hour -= 12
                    return f'{hour}:{minute:02d} {period}'
            except:
                pass
            return dt_str

    @app.template_filter('local_datetime')
    def local_datetime_filter(utc_dt, fmt='%m/%d/%Y %I:%M %p'):
        """Convert UTC datetime to local time and format.

        Uses the home organization's timezone setting.

        Examples:
            {{ change.changed_at | local_datetime }}  -> '08/25/2026 02:30 PM'
            {{ game.game_date | local_datetime('%a, %b %d at %I:%M %p') }}  -> 'Mon, Aug 25 at 2:30 PM'
        """
        if utc_dt is None:
            return ''
        from app.models.organization import Organization
        return Organization.format_local_datetime(utc_dt, fmt)

    # CSRF error handler - session expired or token missing
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF token errors gracefully.

        This typically happens when:
        - The user's session expired
        - The user opened a form in multiple tabs
        - The page was cached with a stale token
        """
        # Log it but don't treat as critical error
        print(f"CSRF Error at {request.method} {request.path}: {e.description}", file=sys.stderr, flush=True)

        # For API requests, return JSON
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({
                'error': 'Session expired',
                'message': 'Your session has expired. Please refresh the page and try again.'
            }), 400

        # For regular requests, flash a message and redirect
        flash('Your session expired. Please try your action again.', 'warning')

        # Try to redirect back to where they were, or home
        referrer = request.referrer
        if referrer and referrer.startswith(request.host_url):
            return redirect(referrer)
        return redirect(url_for('main.dashboard'))

    # Global error handler - uses Tier I/II error reporting
    @app.errorhandler(Exception)
    def handle_exception(e):
        from flask import render_template
        from flask_login import current_user
        from werkzeug.exceptions import HTTPException
        from app.utils.errors import log_tier1

        # Don't log HTTP exceptions (404, 403, etc.) as Tier I
        if isinstance(e, HTTPException):
            return e

        # Get user ID if logged in
        user_id = None
        try:
            if current_user.is_authenticated:
                user_id = current_user.id
        except Exception:
            pass

        # Log as Tier I - unhandled exceptions are serious
        log_tier1('unhandled_exception', e, request, user_id)

        # Return JSON for API-like requests
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': 'Internal server error', 'message': 'An unexpected error occurred.'}), 500

        # Return user-friendly error page
        try:
            return render_template('errors/500.html'), 500
        except Exception:
            # If even the error template fails, return plain text
            return "An error occurred. We've been notified.", 500

    return app
