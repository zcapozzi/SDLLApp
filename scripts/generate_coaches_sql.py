#!/usr/bin/env python3
"""
Generate SQL to import coaches from f2026_coaches.json.

This script generates a .sql file with INSERT statements.
It reads ENCRYPTION_KEY from .env file.

Usage:
    python scripts/generate_coaches_sql.py > scripts/import_coaches_data.sql

Then run the SQL file against your database.
"""

import json
import os
import sys
import hashlib
from datetime import datetime

# Load .env file
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, '.env')

if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# Check for encryption key
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    print("-- ERROR: ENCRYPTION_KEY environment variable not set!", file=sys.stderr)
    print("-- Set it with: set ENCRYPTION_KEY=your_key_here", file=sys.stderr)
    print("-- You can find it in Railway's environment variables", file=sys.stderr)
    sys.exit(1)

# Import encryption after we have the key
from cryptography.fernet import Fernet

def get_fernet():
    key = ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)

def encrypt_value(value):
    if value is None:
        return None
    fernet = get_fernet()
    return fernet.encrypt(value.encode()).decode()

def hash_for_lookup(value):
    if value is None:
        return None
    normalized = value.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()

def escape_sql(value):
    """Escape a value for SQL."""
    if value is None:
        return 'NULL'
    # Escape single quotes
    escaped = value.replace("'", "''")
    return f"'{escaped}'"

def generate_sql():
    # Load coach data
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(os.path.dirname(script_dir), 'f2026_coaches.json')

    with open(json_path, 'r') as f:
        coaches = json.load(f)

    print("-- Generated SQL for importing coaches")
    print(f"-- Generated at: {datetime.now().isoformat()}")
    print(f"-- Total coaches in JSON: {len(coaches)}")
    print()

    # Track emails we've seen to avoid duplicates
    seen_emails = set()
    skipped = 0

    print("-- ============================================")
    print("-- INSERT USERS")
    print("-- ============================================")
    print()

    for coach in coaches:
        first_name = coach.get('first_name', '').strip()
        last_name = coach.get('last_name', '').strip()
        email = coach.get('email')
        phone = coach.get('phone')
        sport = coach.get('sport', 'baseball')

        full_name = f"{first_name} {last_name}"

        # Skip coaches without email
        if not email:
            print(f"-- SKIP (no email): {full_name}")
            skipped += 1
            continue

        email = email.strip().lower()

        # Skip duplicates
        if email in seen_emails:
            print(f"-- SKIP (duplicate email): {full_name} ({email})")
            skipped += 1
            continue

        seen_emails.add(email)

        # Determine role
        if first_name.lower() == 'benjamin' and last_name.lower() == 'porche':
            role = 'coach|treasurer'
        else:
            role = 'coach'

        # Encrypt values
        encrypted_email = encrypt_value(email)
        email_hash = hash_for_lookup(email)
        encrypted_name = encrypt_value(full_name)
        encrypted_phone = encrypt_value(phone) if phone else None

        # Generate random password hash (user will need to reset)
        import secrets
        temp_password = f"NEEDS_RESET_{secrets.token_hex(8)}"
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(temp_password)

        print(f"-- Coach: {full_name} ({email}) - {sport}")
        print(f"INSERT INTO sdll_users (active, email, email_hash, name, phone, password_hash, role, org_ID, created_at)")
        print(f"SELECT 1, {escape_sql(encrypted_email)}, {escape_sql(email_hash)}, {escape_sql(encrypted_name)}, {escape_sql(encrypted_phone)}, {escape_sql(password_hash)}, {escape_sql(role)}, 1, NOW()")
        print(f"WHERE NOT EXISTS (SELECT 1 FROM sdll_users WHERE email_hash = {escape_sql(email_hash)});")
        print()

    print()
    print("-- ============================================")
    print("-- INSERT COACH RECORDS (link users to sports)")
    print("-- ============================================")
    print()

    # Reset seen emails for coach records
    seen_emails = set()

    for coach in coaches:
        first_name = coach.get('first_name', '').strip()
        last_name = coach.get('last_name', '').strip()
        email = coach.get('email')
        sport = coach.get('sport', 'baseball')

        full_name = f"{first_name} {last_name}"

        if not email:
            continue

        email = email.strip().lower()

        if email in seen_emails:
            continue

        seen_emails.add(email)

        email_hash = hash_for_lookup(email)

        print(f"-- Link: {full_name} -> {sport}")
        print(f"INSERT INTO sdll_coaches (user_id, sport, season_year, is_spring, active, created_at)")
        print(f"SELECT u.ID, '{sport}', 2026, 1, 1, NOW()")
        print(f"FROM sdll_users u")
        print(f"WHERE u.email_hash = {escape_sql(email_hash)}")
        print(f"AND NOT EXISTS (")
        print(f"    SELECT 1 FROM sdll_coaches c")
        print(f"    WHERE c.user_id = u.ID AND c.season_year = 2026 AND c.is_spring = 1")
        print(f");")
        print()

    print(f"-- ============================================")
    print(f"-- Summary: {len(seen_emails)} coaches to import, {skipped} skipped")
    print(f"-- ============================================")


if __name__ == '__main__':
    generate_sql()
