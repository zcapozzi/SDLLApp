import os
import json
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.dirname(basedir)


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


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

    # MySQL connection - local development
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'sdll')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    )


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True

    # Use a separate test database
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'sdll_test')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    )

    # Disable rate limiting in tests
    RATELIMIT_ENABLED = False

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False


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
