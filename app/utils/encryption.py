"""PII encryption utilities using Fernet symmetric encryption"""

import os
import hashlib
from cryptography.fernet import Fernet
from flask import current_app


def get_fernet():
    """Get Fernet instance from app config or environment"""
    key = current_app.config.get('ENCRYPTION_KEY') or os.environ.get('ENCRYPTION_KEY')
    if not key:
        # Generate a key for development (should be set in production)
        key = Fernet.generate_key()
        current_app.config['ENCRYPTION_KEY'] = key
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_value(value):
    """Encrypt a string value for storage"""
    if value is None:
        return None
    fernet = get_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value):
    """Decrypt an encrypted value"""
    if encrypted_value is None:
        return None
    fernet = get_fernet()
    return fernet.decrypt(encrypted_value.encode()).decode()


def hash_for_lookup(value):
    """Create a SHA256 hash of a value for lookup purposes (email)"""
    if value is None:
        return None
    # Normalize to lowercase for consistent hashing
    normalized = value.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_encryption_key():
    """Generate a new Fernet encryption key"""
    return Fernet.generate_key().decode()
