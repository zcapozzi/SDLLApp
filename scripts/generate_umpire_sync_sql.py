#!/usr/bin/env python
"""Generate SQL script for umpire data sync.

This script generates SQL that can be run directly in MySQL Workbench
against the production database.

Usage:
    python scripts/generate_umpire_sync_sql.py > scripts/umpire_sync.sql
"""

import sys
import os
import csv
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file into environment variables
from dotenv import load_dotenv
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, '.env'))


def parse_registration_csv(csv_path):
    """Parse the registration CSV and extract umpire data."""
    registrations = []

    if not os.path.exists(csv_path):
        return []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    header_row_idx = None
    for i, row in enumerate(rows):
        if len(row) > 1 and row[0] == 'Timestamp' and row[1] == 'First Name':
            header_row_idx = i
            break

    if header_row_idx is None:
        return []

    headers = rows[header_row_idx]

    for row in rows[header_row_idx + 1:]:
        if len(row) < 10 or not row[0]:
            continue

        reg = {}
        for i, header in enumerate(headers):
            if i < len(row):
                reg[header] = row[i].strip() if row[i] else ''

        registration = {
            'first_name': reg.get('First Name', ''),
            'last_name': reg.get('Last name', ''),
            'umpire_email': reg.get('What is your email?', ''),
            'parent_email': reg.get("What is your parent's email?", ''),
            'parent_phone': reg.get("What is your parent's cell phone number?", ''),
        }

        if registration['first_name'] and registration['last_name']:
            registrations.append(registration)

    return registrations


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ''
    return name.lower().strip()


def generate_sql():
    """Generate the SQL script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    csv_path = os.path.join(project_root, 'docs', 'Fall2026AcademyRegistration.csv')

    registrations = parse_registration_csv(csv_path)

    # Create app context for encryption functions and Assignr API
    from app import create_app
    app = create_app()

    print("-- =============================================================")
    print("-- UMPIRE DATA SYNC SQL SCRIPT")
    print(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-- =============================================================")
    print("-- ")
    print("-- Run this script in MySQL Workbench connected to Railway prod DB")
    print("-- Review each section before running!")
    print("-- ")
    print("-- IMPORTANT: Run steps in order! Some steps depend on previous steps.")
    print("-- =============================================================")
    print()

    # Push app context for all operations
    ctx = app.app_context()
    ctx.push()

    try:
        from app.utils.encryption import hash_for_lookup, encrypt_value
        from app.services.assignr_service import AssignrService

        # =========================================================
        # STEP 1: Create profiles for users with umpire role
        # =========================================================
        print("-- =============================================================")
        print("-- STEP 1: Create profiles for users with umpire role but no profile")
        print("-- =============================================================")
        print()
        print("-- First, let's see who needs profiles:")
        print("SELECT u.ID, u.name, u.email, u.role")
        print("FROM sdll_users u")
        print("LEFT JOIN sdll_umpire_profiles p ON u.ID = p.user_id")
        print("WHERE u.role LIKE '%umpire%'")
        print("AND u.active = 1")
        print("AND p.id IS NULL;")
        print()
        print("-- Create profiles for these users:")
        print()
        print("INSERT INTO sdll_umpire_profiles (user_id, status, created_at)")
        print("SELECT ")
        print("    u.ID,")
        print("    'active',")
        print("    NOW()")
        print("FROM sdll_users u")
        print("LEFT JOIN sdll_umpire_profiles p ON u.ID = p.user_id")
        print("WHERE u.role LIKE '%umpire%'")
        print("AND u.active = 1")
        print("AND p.id IS NULL;")
        print()

        # =========================================================
        # STEP 2: Update parent info from CSV
        # =========================================================
        if registrations:
            print("-- =============================================================")
            print("-- STEP 2: Update parent contact info from registration CSV")
            print("-- =============================================================")
            print("-- ")
            print(f"-- Found {len(registrations)} registrations in CSV")
            print("-- ")
            print("-- WARNING: Encrypted values use LOCAL encryption key.")
            print("-- If production uses a DIFFERENT key, run Python script instead:")
            print("--   railway run python scripts/sync_umpire_data.py")
            print()
            print("-- Updates for profiles:")
            print()

            # Collect unique parent emails for Step 3
            parent_info = {}  # hash -> {email, first umpire name}

            for reg in registrations:
                if reg['parent_email'] and reg['umpire_email']:
                    umpire_email_hash = hash_for_lookup(reg['umpire_email'])
                    parent_email_encrypted = encrypt_value(reg['parent_email'])
                    parent_hash = hash_for_lookup(reg['parent_email'])

                    # Track parent emails for Step 3
                    if parent_hash not in parent_info:
                        parent_info[parent_hash] = {
                            'email': reg['parent_email'],
                            'umpire_name': f"{reg['first_name']} {reg['last_name']}"
                        }

                    parent_phone_encrypted = None
                    if reg['parent_phone']:
                        parent_phone_encrypted = encrypt_value(reg['parent_phone'])

                    print(f"-- {reg['first_name']} {reg['last_name']} ({reg['umpire_email']})")
                    # Match via user's email_hash (profiles are linked to users via user_id)
                    print(f"UPDATE sdll_umpire_profiles p")
                    print(f"INNER JOIN sdll_users u ON p.user_id = u.ID")
                    print(f"SET p.parent_email = '{parent_email_encrypted}',")
                    print(f"    p.parent_email_hash = '{parent_hash}'")
                    if parent_phone_encrypted:
                        print(f"    , p.parent_phone = '{parent_phone_encrypted}'")
                    print(f"WHERE u.email_hash = '{umpire_email_hash}'")
                    print(f"AND (p.parent_email IS NULL OR p.parent_email = '');")
                    print()

            # =========================================================
            # STEP 3: Create parent user accounts
            # =========================================================
            print("-- =============================================================")
            print("-- STEP 3: Create user accounts for parents")
            print("-- =============================================================")
            print("-- ")
            print("-- Creates user accounts for parents who don't have one.")
            print("-- Password is set to empty - they'll need to use 'Forgot Password'.")
            print("-- ")
            print("-- First, check which parents already have accounts:")
            print()

            # Build a VALUES clause with all parent hashes for the check
            hash_list = "', '".join(parent_info.keys())
            print(f"SELECT email_hash, name, email")
            print(f"FROM sdll_users")
            print(f"WHERE email_hash IN ('{hash_list}')")
            print(f"AND active = 1;")
            print()

            print("-- Insert parent accounts (only if they don't exist):")
            print()

            for parent_hash, info in parent_info.items():
                parent_email = info['email']
                umpire_name = info['umpire_name']

                # Encrypt the parent's email for storage
                encrypted_email = encrypt_value(parent_email)
                # Use email as name placeholder (they can update later)
                encrypted_name = encrypt_value(parent_email.split('@')[0])

                print(f"-- Parent of {umpire_name} ({parent_email})")
                print(f"INSERT INTO sdll_users (email, email_hash, name, password_hash, role, active, created_at)")
                print(f"SELECT")
                print(f"    '{encrypted_email}',")
                print(f"    '{parent_hash}',")
                print(f"    '{encrypted_name}',")
                print(f"    '',")  # Empty password_hash - requires reset
                print(f"    'parent',")
                print(f"    1,")
                print(f"    NOW()")
                print(f"WHERE NOT EXISTS (")
                print(f"    SELECT 1 FROM sdll_users WHERE email_hash = '{parent_hash}'")
                print(f");")
                print()

        # =========================================================
        # STEP 4: Create guardian relationships
        # =========================================================
        print("-- =============================================================")
        print("-- STEP 4: Create guardian relationships")
        print("-- =============================================================")
        print("-- ")
        print("-- Links parent user accounts to umpire profiles.")
        print()
        print("-- Preview matches:")
        print("SELECT ")
        print("    p.id as profile_id,")
        print("    p._first_name,")
        print("    p._last_name,")
        print("    u.ID as guardian_user_id,")
        print("    u.name as guardian_name")
        print("FROM sdll_umpire_profiles p")
        print("INNER JOIN sdll_users u ON p.parent_email_hash = u.email_hash")
        print("WHERE p.parent_email_hash IS NOT NULL")
        print("AND u.active = 1")
        print("AND NOT EXISTS (")
        print("    SELECT 1 FROM sdll_umpire_guardians g ")
        print("    WHERE g.umpire_profile_id = p.id AND g.guardian_user_id = u.ID")
        print(");")
        print()
        print("-- Create the guardian relationships:")
        print("INSERT INTO sdll_umpire_guardians (guardian_user_id, umpire_profile_id, relationship, is_primary, created_at)")
        print("SELECT ")
        print("    u.ID,")
        print("    p.id,")
        print("    'parent',")
        print("    1,")
        print("    NOW()")
        print("FROM sdll_umpire_profiles p")
        print("INNER JOIN sdll_users u ON p.parent_email_hash = u.email_hash")
        print("WHERE p.parent_email_hash IS NOT NULL")
        print("AND u.active = 1")
        print("AND NOT EXISTS (")
        print("    SELECT 1 FROM sdll_umpire_guardians g ")
        print("    WHERE g.umpire_profile_id = p.id AND g.guardian_user_id = u.ID")
        print(");")
        print()

        # =========================================================
        # STEP 5: Link Assignr Official IDs
        # =========================================================
        print("-- =============================================================")
        print("-- STEP 5: Link Assignr Official IDs")
        print("-- =============================================================")
        print("-- ")

        # Fetch Assignr officials
        try:
            assignr = AssignrService()
            officials = assignr.get_all_site_officials()
            print(f"-- Fetched {len(officials)} officials from Assignr")
            print("-- ")

            # Debug: Print all Assignr officials and their emails
            if officials:
                print("-- Assignr Officials found:")
                for official in officials:
                    oid = official.get('id')
                    first = official.get('first_name', '') or ''
                    last = official.get('last_name', '') or ''
                    emails = []
                    for e in official.get('email_addresses', []):
                        if isinstance(e, str):
                            emails.append(e)
                        elif isinstance(e, dict):
                            emails.append(e.get('email', ''))
                    print(f"--   ID {oid}: {first} {last} - {', '.join(emails) if emails else 'NO EMAIL'}")
                print("-- ")
            else:
                print("-- WARNING: No officials returned from Assignr API")
                print("-- This could mean:")
                print("--   1. Assignr credentials not configured (ASSIGNR_CLIENT_ID, ASSIGNR_CLIENT_SECRET, ASSIGNR_SITE_ID)")
                print("--   2. API returned an error")
                print("--   3. No officials registered on the Assignr site")
                print("-- ")

            # Build lookups by email and by name
            officials_by_email = {}
            officials_by_name = {}

            for official in officials:
                official_id = official.get('id')
                first = official.get('first_name', '') or ''
                last = official.get('last_name', '') or ''
                full_name = f"{first} {last}".strip()

                official_data = {
                    'id': official_id,
                    'first_name': first,
                    'last_name': last,
                    'full_name': full_name
                }

                # Index by email(s)
                email_addresses = official.get('email_addresses', [])
                for email_obj in email_addresses:
                    if isinstance(email_obj, str):
                        email = email_obj.lower().strip()
                    elif isinstance(email_obj, dict):
                        email = (email_obj.get('email') or '').lower().strip()
                    else:
                        continue
                    if email:
                        officials_by_email[email] = official_data

                # Index by name (fallback)
                if official_id and full_name:
                    key = normalize_name(full_name)
                    officials_by_name[key] = official_data

            print(f"-- Built lookup: {len(officials_by_email)} emails, {len(officials_by_name)} names")
            print("-- ")
            print("-- Matching umpires from CSV to Assignr officials (by email, then by name):")
            print()

            matched = 0
            matched_by_email = 0
            matched_by_name = 0
            unmatched = []

            for reg in registrations:
                umpire_name = f"{reg['first_name']} {reg['last_name']}"
                umpire_email = reg['umpire_email'].lower().strip()
                name_key = normalize_name(umpire_name)

                official = None
                match_method = None

                # Try email match first (most reliable)
                if umpire_email in officials_by_email:
                    official = officials_by_email[umpire_email]
                    match_method = "email"
                    matched_by_email += 1
                # Fall back to name match
                elif name_key in officials_by_name:
                    official = officials_by_name[name_key]
                    match_method = "name"
                    matched_by_name += 1

                if official:
                    umpire_email_hash = hash_for_lookup(reg['umpire_email'])

                    print(f"-- {umpire_name} ({umpire_email}) -> Assignr ID {official['id']} (matched by {match_method})")
                    # Match via user's email_hash (profiles are linked to users via user_id)
                    print(f"UPDATE sdll_umpire_profiles p")
                    print(f"INNER JOIN sdll_users u ON p.user_id = u.ID")
                    print(f"SET p.assignr_id = '{official['id']}'")
                    print(f"WHERE u.email_hash = '{umpire_email_hash}'")
                    print(f"AND (p.assignr_id IS NULL OR p.assignr_id = '');")
                    print()
                    matched += 1
                else:
                    unmatched.append(f"{umpire_name} ({umpire_email})")

            if unmatched:
                print("-- =============================================================")
                print("-- UNMATCHED UMPIRES (not found in Assignr by email or name)")
                print("-- =============================================================")
                print("-- These umpires were in the CSV but couldn't be matched to Assignr:")
                for name in unmatched:
                    print(f"--   - {name}")
                print()
                print("-- You may need to:")
                print("--   1. Check if they're registered in Assignr with a different name")
                print("--   2. Add them to Assignr if they're not registered")
                print("--   3. Manually update their assignr_id in the database")
                print()

            print(f"-- Matched {matched} of {len(registrations)} umpires to Assignr officials")
            print(f"--   ({matched_by_email} by email, {matched_by_name} by name)")
            print()

        except Exception as e:
            print(f"-- Could not fetch Assignr officials: {e}")
            print("-- You'll need to set assignr_id values manually.")
            print()
            print("-- To see profiles without Assignr ID:")
            print("SELECT id, _first_name, _last_name, assignr_id")
            print("FROM sdll_umpire_profiles")
            print("WHERE status = 'active'")
            print("AND (assignr_id IS NULL OR assignr_id = '');")
            print()

        # =========================================================
        # VERIFICATION QUERIES
        # =========================================================
        print("-- =============================================================")
        print("-- VERIFICATION QUERIES")
        print("-- =============================================================")
        print()
        print("-- Check profile counts:")
        print("SELECT ")
        print("    COUNT(*) as total_profiles,")
        print("    SUM(CASE WHEN assignr_id IS NOT NULL AND assignr_id != '' THEN 1 ELSE 0 END) as with_assignr,")
        print("    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as managed_profiles,")
        print("    SUM(CASE WHEN parent_email_hash IS NOT NULL THEN 1 ELSE 0 END) as with_parent_hash")
        print("FROM sdll_umpire_profiles")
        print("WHERE status = 'active';")
        print()
        print("-- Check guardian relationships:")
        print("SELECT COUNT(*) as guardian_relationships FROM sdll_umpire_guardians;")
        print()
        print("-- Check parent accounts created:")
        print("SELECT COUNT(*) as parent_accounts FROM sdll_users WHERE role = 'parent';")
        print()
        print("-- Check profiles still missing assignr_id:")
        print("SELECT COUNT(*) as missing_assignr")
        print("FROM sdll_umpire_profiles")
        print("WHERE status = 'active'")
        print("AND (assignr_id IS NULL OR assignr_id = '');")

    except Exception as e:
        print(f"-- ERROR: {e}")
        import traceback
        print(f"-- {traceback.format_exc()}")
    finally:
        ctx.pop()


if __name__ == '__main__':
    generate_sql()
