"""Signed tokens for email mute links.

Generates secure, time-limited tokens that encode mute parameters.
These tokens can be used in email links without requiring login.
"""

import os
import hmac
import hashlib
import base64
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any


# Token validity period (7 days)
TOKEN_VALIDITY_DAYS = 7


def _get_secret_key() -> bytes:
    """Get the secret key for signing tokens."""
    # Use Flask's SECRET_KEY or a fallback
    secret = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    return secret.encode('utf-8')


def generate_mute_token(
    game_id: int,
    notification_type: str,
    expires_days: int = TOKEN_VALIDITY_DAYS
) -> str:
    """Generate a signed token for muting a notification.

    Args:
        game_id: The game ID to mute
        notification_type: Type of notification (e.g., 'missing_assignment')
        expires_days: Days until token expires

    Returns:
        URL-safe base64-encoded signed token
    """
    # Create payload
    expires_at = datetime.utcnow() + timedelta(days=expires_days)
    payload = {
        'g': game_id,
        't': notification_type,
        'e': int(expires_at.timestamp())
    }

    # Encode payload
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_bytes = payload_json.encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip('=')

    # Sign it
    signature = hmac.new(
        _get_secret_key(),
        payload_bytes,
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature[:16]).decode('utf-8').rstrip('=')

    # Combine: payload.signature
    return f"{payload_b64}.{signature_b64}"


def verify_mute_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Verify a mute token and extract its payload.

    Args:
        token: The token to verify

    Returns:
        Tuple of (is_valid, payload_dict, error_message)
        payload_dict contains 'game_id' and 'notification_type' if valid
    """
    if not token or '.' not in token:
        return False, None, "Invalid token format"

    try:
        # Split payload and signature
        parts = token.split('.')
        if len(parts) != 2:
            return False, None, "Invalid token format"

        payload_b64, signature_b64 = parts

        # Add padding back
        payload_b64 += '=' * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ''
        signature_b64 += '=' * (4 - len(signature_b64) % 4) if len(signature_b64) % 4 else ''

        # Decode payload
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Verify signature
        expected_signature = hmac.new(
            _get_secret_key(),
            payload_bytes,
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_signature[:16]).decode('utf-8').rstrip('=')

        # Add padding for comparison
        expected_sig_b64_padded = expected_sig_b64 + '=' * (4 - len(expected_sig_b64) % 4) if len(expected_sig_b64) % 4 else expected_sig_b64
        actual_sig_padded = signature_b64

        if not hmac.compare_digest(expected_sig_b64_padded.encode(), actual_sig_padded.encode()):
            return False, None, "Invalid signature"

        # Check expiration
        expires_at = datetime.fromtimestamp(payload['e'])
        if datetime.utcnow() > expires_at:
            return False, None, "Token has expired"

        # Return decoded payload
        return True, {
            'game_id': payload['g'],
            'notification_type': payload['t']
        }, ""

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        return False, None, f"Token decode error: {str(e)}"


def generate_mute_url(
    base_url: str,
    game_id: int,
    notification_type: str
) -> str:
    """Generate a full mute URL with signed token.

    Args:
        base_url: The base URL of the app (e.g., https://www.southdurhamlittleleague.org)
        game_id: The game ID to mute
        notification_type: Type of notification

    Returns:
        Full URL with token
    """
    token = generate_mute_token(game_id, notification_type)
    return f"{base_url}/umpires/quick-mute/{token}"
