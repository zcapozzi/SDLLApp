"""SDLL Web Application - Flask App Factory"""

import os
import sys
import json
import traceback
from flask import Flask, jsonify, request

from .extensions import db, login_manager, limiter, csrf
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

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(seasons_bp, url_prefix='/seasons')
    app.register_blueprint(games_bp, url_prefix='/games')
    app.register_blueprint(fields_bp, url_prefix='/fields')
    app.register_blueprint(leagues_bp, url_prefix='/leagues')
    app.register_blueprint(scheduler_bp, url_prefix='/scheduler')

    # User loader for Flask-Login
    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Global error handler - logs full traceback to stdout for Railway
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log the full traceback to stdout (Railway captures this)
        print("=" * 60, file=sys.stderr, flush=True)
        print(f"UNHANDLED EXCEPTION at {request.method} {request.path}", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        print("=" * 60, file=sys.stderr, flush=True)
        sys.stderr.flush()

        # Return JSON for API-like requests, otherwise a simple error page
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

        return f"""
        <html>
        <head><title>500 Error</title></head>
        <body style="font-family: sans-serif; padding: 2rem;">
            <h1>500 - Internal Server Error</h1>
            <p>Something went wrong. The error has been logged.</p>
            <pre style="background: #f5f5f5; padding: 1rem; overflow: auto;">{str(e)}</pre>
            <a href="/">Return to Home</a>
        </body>
        </html>
        """, 500

    return app
