"""Flask extensions initialization"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# SQLAlchemy database instance
db = SQLAlchemy()

# Login manager
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=['200 per hour']
)

# CSRF protection
csrf = CSRFProtect()
