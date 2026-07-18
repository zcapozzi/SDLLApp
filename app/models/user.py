"""User model - maps to sdll_users table with PII encryption"""

from datetime import datetime, timedelta
import secrets
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class User(UserMixin, db.Model):
    """User model with encrypted PII fields"""
    __tablename__ = 'sdll_users'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    active = db.Column(db.SmallInteger, default=1)

    # Email - stored encrypted with hash for lookup
    _email = db.Column('email', db.String(200), nullable=False)
    email_hash = db.Column(db.String(64), unique=True, nullable=False)

    # Password
    password_hash = db.Column(db.String(256), nullable=False)

    # PII - stored encrypted
    _name = db.Column('name', db.String(200))
    _phone = db.Column('phone', db.String(50))

    # Role-based access
    role = db.Column(db.String(50), default='viewer')

    # Organization
    org_ID = db.Column(db.BigInteger, default=1)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Password reset
    password_reset_token = db.Column(db.String(100))
    password_reset_expiry = db.Column(db.DateTime)

    # Valid roles
    ROLES = ['admin', 'scheduler', 'umpire_coordinator', 'viewer']

    def __repr__(self):
        return f'<User {self.ID} ({self.role})>'

    def get_id(self):
        """Required by Flask-Login"""
        return str(self.ID)

    # Email property with encryption
    @property
    def email(self):
        return decrypt_value(self._email)

    @email.setter
    def email(self, value):
        self._email = encrypt_value(value)
        self.email_hash = hash_for_lookup(value)

    # Name property with encryption
    @property
    def name(self):
        return decrypt_value(self._name)

    @name.setter
    def name(self, value):
        self._name = encrypt_value(value)

    # Phone property with encryption
    @property
    def phone(self):
        return decrypt_value(self._phone)

    @phone.setter
    def phone(self, value):
        self._phone = encrypt_value(value)

    def set_password(self, password):
        """Hash and store password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()

    def generate_reset_token(self):
        """Generate password reset token valid for 1 hour"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expiry = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        return self.password_reset_token

    def verify_reset_token(self, token):
        """Verify password reset token"""
        if not self.password_reset_token or not self.password_reset_expiry:
            return False
        if self.password_reset_token != token:
            return False
        if datetime.utcnow() > self.password_reset_expiry:
            return False
        return True

    def clear_reset_token(self):
        """Clear password reset token after use"""
        self.password_reset_token = None
        self.password_reset_expiry = None
        db.session.commit()

    # Role checking methods
    def is_admin(self):
        return self.role == 'admin'

    def is_scheduler(self):
        return self.role in ['admin', 'scheduler']

    def is_umpire_coordinator(self):
        return self.role in ['admin', 'umpire_coordinator']

    def can_edit_schedule(self):
        return self.role in ['admin', 'scheduler']

    def can_manage_umpires(self):
        return self.role in ['admin', 'umpire_coordinator']

    @classmethod
    def get_by_email(cls, email):
        """Find user by email using hash lookup"""
        email_hash = hash_for_lookup(email)
        return cls.query.filter_by(email_hash=email_hash, active=1).first()

    @classmethod
    def create_user(cls, email, password, name=None, phone=None, role='viewer', org_ID=1):
        """Create a new user"""
        if len(password) < 8:
            raise ValueError('Password must be at least 8 characters')

        if role not in cls.ROLES:
            raise ValueError(f'Invalid role. Must be one of: {cls.ROLES}')

        user = cls(
            role=role,
            org_ID=org_ID
        )
        user.email = email
        user.name = name
        user.phone = phone
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
        return user
