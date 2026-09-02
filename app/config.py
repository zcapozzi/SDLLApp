import os
import sys
import json
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.dirname(basedir)


def is_running_on_railway():
    """Detect if we're running on Railway production environment.

    Railway sets specific environment variables that won't be present locally.
    """
    # Railway always sets RAILWAY_ENVIRONMENT in production
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        return True
    # Also check for Railway's internal variables
    if os.environ.get('RAILWAY_PROJECT_ID'):
        return True
    # Check if MYSQL_URL points to Railway's proxy
    mysql_url = os.environ.get('MYSQL_URL', '')
    if 'rlwy.net' in mysql_url or 'railway' in mysql_url.lower():
        return True
    return False


def load_secrets():
    """Load secrets from client_secrets.json"""
    secrets_path = os.path.join(project_root, 'client_secrets.json')
    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            return json.load(f)
    return {}


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(days=90)  # 3 months

    # Disable CSRF - low-risk internal admin tool, not worth the UX cost
    WTF_CSRF_ENABLED = False

    # Rate limiting
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = '200 per hour'

    # Encryption key for PII
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    # Load client secrets
    _secrets = load_secrets()

    @classmethod
    def get_secret(cls, section, key, default=None):
        """Get a secret from client_secrets.json"""
        if section in cls._secrets and key in cls._secrets[section]:
            return cls._secrets[section][key]
        return default


def _get_local_database_uri():
    """Build local database URI, ignoring any Railway env vars.

    Reads from .env file values only (MYSQL_HOST, MYSQL_USER, etc.)
    and explicitly ignores MYSQL_URL to prevent accidentally
    connecting to production.
    """
    # Load from .env - these should be local values
    from dotenv import dotenv_values
    env_path = os.path.join(project_root, '.env')
    env_values = dotenv_values(env_path) if os.path.exists(env_path) else {}

    # Use .env values, fall back to safe local defaults
    host = env_values.get('MYSQL_HOST', 'localhost')
    user = env_values.get('MYSQL_USER', 'root')
    password = env_values.get('MYSQL_PASSWORD', '')
    database = env_values.get('MYSQL_DB', 'railway_replica')

    # Safety check: never connect to Railway in development
    if 'rlwy.net' in host or 'railway' in host.lower():
        print(f"WARNING: .env MYSQL_HOST points to Railway ({host}). Using localhost instead.", file=sys.stderr)
        host = 'localhost'

    uri = f"mysql+pymysql://{user}:{password}@{host}/{database}"
    print(f"[DEV CONFIG] Database: {user}@{host}/{database}", file=sys.stderr)
    return uri


class DevelopmentConfig(Config):
    """Development configuration - always uses local database."""
    DEBUG = True

    # Server-side session file directory
    SESSION_FILE_DIR = os.path.join(project_root, 'flask_session')

    # Use local database URI (reads directly from .env, ignores system env vars)
    SQLALCHEMY_DATABASE_URI = _get_local_database_uri()


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True

    # Use same credentials as development, but different database
    # This reads from .env file (loaded by python-dotenv in conftest.py)
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'lrp_master')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = 'sdll_test'  # Always use test database, never production

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    )

    # Disable rate limiting in tests
    RATELIMIT_ENABLED = False


def _get_production_database_url():
    """Get database URL, converting Railway's format if needed.

    Railway provides MYSQL_URL as: mysql://user:pass@host:port/db
    PyMySQL needs: mysql+pymysql://user:pass@host:port/db
    """
    # Try MYSQL_URL first (Railway MySQL plugin)
    url = os.environ.get('MYSQL_URL') or os.environ.get('DATABASE_URL')

    if url:
        # Convert mysql:// to mysql+pymysql://
        if url.startswith('mysql://'):
            url = url.replace('mysql://', 'mysql+pymysql://', 1)
        return url

    # Fallback to individual env vars
    host = os.environ.get('MYSQL_HOST', 'localhost')
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    database = os.environ.get('MYSQL_DB', 'sdll')
    port = os.environ.get('MYSQL_PORT', '3306')

    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    # Must set these in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    # Session configuration for production
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_session'

    # Database URL (handles Railway's MYSQL_URL format)
    SQLALCHEMY_DATABASE_URI = _get_production_database_url()


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
