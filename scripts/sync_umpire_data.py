#!/usr/bin/env python
"""Sync umpire data across systems.

This script:
1. Imports registration CSV data (parent emails, phone numbers)
2. Creates profiles for users with umpire role but no profile
3. Links profiles to Assignr officials by name matching
4. Identifies and creates guardian relationships (parent/child)

Usage:
    python scripts/sync_umpire_data.py [--dry-run] [--step STEP] [--csv PATH]

Options:
    --dry-run       Preview changes without making them
    --step STEP     Run only specific step: registration, profiles, assignr, guardians, or all
    --csv PATH      Path to registration CSV (default: docs/Fall2026AcademyRegistration.csv)
"""

import sys
import os
import re
import csv
from datetime import datetime
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ''
    name = name.strip().lower()
    name = re.sub(r'\s+', ' ', name)
    return name


def normalize_email(email):
    """Normalize an email for comparison."""
    if not email:
        return ''
    return email.strip().lower()


def parse_registration_csv(csv_path):
    """Parse the registration CSV and extract umpire data."""
    registrations = []

    if not os.path.exists(csv_path):
        print(f"Registration CSV not found: {csv_path}")
        return []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find the header row (contains 'Timestamp', 'First Name', etc.)
    header_row_idx = None
    for i, row in enumerate(rows):
        if len(row) > 1 and row[0] == 'Timestamp' and row[1] == 'First Name':
            header_row_idx = i
            break

    if header_row_idx is None:
        print("ERROR: Could not find header row in CSV")
        return []

    headers = rows[header_row_idx]

    # Process data rows
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
            'umpire_phone': reg.get('What is your cell phone number, if you have one?', ''),
            'age': reg.get('Age', ''),
            'parent_email': reg.get("What is your parent's email?", ''),
            'parent_phone': reg.get("What is your parent's cell phone number?", ''),
            'umpired_before': reg.get('Did you umpire for SDLL before?', ''),
        }

        if registration['first_name'] and registration['last_name']:
            registrations.append(registration)

    return registrations


def step0_import_registration_data(csv_path, dry_run=True):
    """Import registration CSV data to update profiles with parent info."""
    from app.extensions import db
    from app.models.user import User
    from app.models.umpire_profile import UmpireProfile

    print("\n" + "=" * 60)
    print("STEP 0: Import registration CSV data")
    print("=" * 60)

    registrations = parse_registration_csv(csv_path)
    print(f"Found {len(registrations)} registrations in CSV")

    if not registrations:
        return [], []

    # Build lookups for matching
    # Get all profiles
    profiles = UmpireProfile.query.all()
    profiles_by_name = {}
    profiles_by_email = {}

    for p in profiles:
        try:
            name = normalize_name(p.name)
            if name:
                profiles_by_name[name] = p
        except Exception:
            pass

        try:
            if p.umpire_email:
                profiles_by_email[normalize_email(p.umpire_email)] = p
        except Exception:
            pass

    # Get all users for email matching
    users = User.query.filter(User.active == 1).all()
    users_by_email = {}
    for u in users:
        try:
            email = normalize_email(u.email)
            if email:
                users_by_email[email] = u
        except Exception:
            pass

    updated = []
    created = []
    not_found = []

    for reg in registrations:
        full_name = normalize_name(f"{reg['first_name']} {reg['last_name']}")
        umpire_email = normalize_email(reg['umpire_email'])

        # Try to find matching profile
        profile = None

        # Match by email first
        if umpire_email and umpire_email in profiles_by_email:
            profile = profiles_by_email[umpire_email]
        elif full_name in profiles_by_name:
            profile = profiles_by_name[full_name]

        if profile:
            # Update parent info if missing
            changes = []

            try:
                if not profile.parent_email and reg['parent_email']:
                    if not dry_run:
                        profile.parent_email = reg['parent_email']
                    changes.append(f"parent_email={reg['parent_email']}")

                if not profile.parent_phone and reg['parent_phone']:
                    if not dry_run:
                        profile.parent_phone = reg['parent_phone']
                    changes.append(f"parent_phone={reg['parent_phone']}")

                if changes:
                    print(f"  - {reg['first_name']} {reg['last_name']}: {', '.join(changes)}")
                    updated.append((profile, reg))
            except Exception as e:
                print(f"  - {reg['first_name']} {reg['last_name']}: ERROR {e}")
        else:
            # Check if there's a user with this email
            user = users_by_email.get(umpire_email)
            if user:
                # User exists but no profile - will be handled in step1
                print(f"  - {reg['first_name']} {reg['last_name']}: Has user account, needs profile")
            else:
                not_found.append(reg)

    if not dry_run and updated:
        db.session.commit()

    print(f"\nUpdated {len(updated)} profiles with parent info")
    print(f"Not matched: {len(not_found)}")

    return updated, not_found


def step1_create_missing_profiles(dry_run=True):
    """Create umpire profiles for users with umpire role but no profile."""
    from app.extensions import db
    from app.models.user import User
    from app.models.umpire_profile import UmpireProfile

    print("\n" + "=" * 60)
    print("STEP 1: Create profiles for users with umpire role")
    print("=" * 60)

    # Find users with umpire role but no profile
    existing_profile_user_ids = db.session.query(UmpireProfile.user_id).filter(
        UmpireProfile.user_id.isnot(None)
    ).all()
    existing_ids = {r[0] for r in existing_profile_user_ids}

    users_without_profiles = User.query.filter(
        User.active == 1,
        User.role.like('%umpire%'),
        ~User.ID.in_(existing_ids) if existing_ids else True
    ).all()

    print(f"Found {len(users_without_profiles)} users with umpire role but no profile")

    created = []
    errors = []

    for user in users_without_profiles:
        try:
            name = user.name
            email = user.email

            # Parse first/last name
            name_parts = name.split() if name else []
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

            print(f"  - {name} ({email}) -> Creating profile...")

            if not dry_run:
                profile = UmpireProfile(
                    user_id=user.ID,
                    first_name=first_name,
                    last_name=last_name,
                    status=UmpireProfile.STATUS_ACTIVE
                )
                db.session.add(profile)
                created.append((user, profile))
            else:
                created.append((user, None))

        except Exception as e:
            errors.append((user.ID, str(e)))
            print(f"    ERROR: {e}")

    if not dry_run and created:
        db.session.commit()

    print(f"\nCreated {len(created)} profiles")
    if errors:
        print(f"Errors: {len(errors)}")

    return created, errors


def step2_link_assignr_officials(dry_run=True):
    """Link umpire profiles to Assignr officials by name matching."""
    from app.extensions import db
    from app.models.umpire_profile import UmpireProfile
    from app.services.assignr_service import get_assignr_service

    print("\n" + "=" * 60)
    print("STEP 2: Link profiles to Assignr officials")
    print("=" * 60)

    assignr = get_assignr_service()
    if not assignr.is_configured():
        print("Assignr not configured - skipping")
        return [], []

    # Get all officials from Assignr
    print("Fetching officials from Assignr...")
    try:
        officials = assignr.get_all_site_officials()
        print(f"Found {len(officials)} officials in Assignr")
    except Exception as e:
        print(f"Error fetching officials: {e}")
        return [], []

    # Build lookup by normalized name
    officials_by_name = {}
    for off in officials:
        first = off.get('first_name', '') or ''
        last = off.get('last_name', '') or ''
        full_name = normalize_name(f"{first} {last}")
        if full_name:
            if full_name not in officials_by_name:
                officials_by_name[full_name] = []
            officials_by_name[full_name].append(off)

    # Get profiles without assignr_id
    profiles = UmpireProfile.query.filter(
        UmpireProfile.assignr_id.is_(None),
        UmpireProfile.status == UmpireProfile.STATUS_ACTIVE
    ).all()

    print(f"Found {len(profiles)} profiles without Assignr ID")

    linked = []
    ambiguous = []
    not_found = []

    for profile in profiles:
        try:
            profile_name = normalize_name(profile.name)
        except Exception:
            # Decryption error
            continue

        if not profile_name:
            continue

        matches = officials_by_name.get(profile_name, [])

        if len(matches) == 1:
            official = matches[0]
            assignr_id = official.get('id')
            print(f"  - {profile.name} -> Assignr ID {assignr_id}")

            if not dry_run:
                profile.assignr_id = str(assignr_id)
                linked.append((profile, official))
            else:
                linked.append((profile, official))

        elif len(matches) > 1:
            print(f"  - {profile.name} -> AMBIGUOUS ({len(matches)} matches)")
            ambiguous.append((profile, matches))

        else:
            not_found.append(profile)

    if not dry_run and linked:
        db.session.commit()

    print(f"\nLinked: {len(linked)}")
    print(f"Ambiguous (multiple matches): {len(ambiguous)}")
    print(f"Not found in Assignr: {len(not_found)}")

    if ambiguous:
        print("\nAmbiguous matches (need manual review):")
        for profile, matches in ambiguous:
            try:
                print(f"  {profile.name}:")
                for m in matches:
                    print(f"    - ID {m.get('id')}: {m.get('first_name')} {m.get('last_name')}")
            except Exception:
                pass

    return linked, not_found


def step3_create_guardian_relationships(dry_run=True):
    """Identify parent/child relationships and create guardian links.

    Logic:
    - If a profile has parent_email that matches a user's email,
      that user is the guardian
    - If a user is a guardian, their profile (if any) should have
      the child profiles linked
    """
    from app.extensions import db
    from app.models.user import User
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_guardian import UmpireGuardian

    print("\n" + "=" * 60)
    print("STEP 3: Create guardian relationships")
    print("=" * 60)

    # Build email -> user lookup
    users = User.query.filter(User.active == 1).all()
    users_by_email = {}
    for u in users:
        try:
            email = normalize_email(u.email)
            if email:
                users_by_email[email] = u
        except Exception:
            pass  # Decryption error

    print(f"Loaded {len(users_by_email)} users by email")

    # Get profiles with parent_email set (use underlying encrypted column)
    profiles = UmpireProfile.query.filter(
        UmpireProfile._parent_email.isnot(None),
        UmpireProfile._parent_email != ''
    ).all()

    print(f"Found {len(profiles)} profiles with parent_email set")

    # Check existing guardian relationships
    existing_guardians = UmpireGuardian.query.all()
    existing_pairs = {(g.guardian_user_id, g.umpire_profile_id) for g in existing_guardians}
    print(f"Existing guardian relationships: {len(existing_pairs)}")

    created = []
    already_exists = []
    parent_not_user = []

    for profile in profiles:
        try:
            parent_email = normalize_email(profile.parent_email)
        except Exception:
            continue

        if not parent_email:
            continue

        guardian_user = users_by_email.get(parent_email)

        if guardian_user:
            pair = (guardian_user.ID, profile.id)
            if pair in existing_pairs:
                already_exists.append((profile, guardian_user))
            else:
                try:
                    profile_name = profile.name
                    guardian_name = guardian_user.name
                except Exception:
                    profile_name = f"Profile #{profile.id}"
                    guardian_name = f"User #{guardian_user.ID}"

                print(f"  - {profile_name} -> Guardian: {guardian_name}")

                if not dry_run:
                    guardian = UmpireGuardian(
                        guardian_user_id=guardian_user.ID,
                        umpire_profile_id=profile.id,
                        relationship=UmpireGuardian.REL_PARENT,
                        is_primary=1
                    )
                    db.session.add(guardian)
                    existing_pairs.add(pair)

                created.append((profile, guardian_user))
        else:
            parent_not_user.append((profile, parent_email))

    if not dry_run and created:
        db.session.commit()

    print(f"\nCreated: {len(created)} guardian relationships")
    print(f"Already existed: {len(already_exists)}")
    print(f"Parent email not a user: {len(parent_not_user)}")

    if parent_not_user and len(parent_not_user) <= 20:
        print("\nParent emails not matching any user:")
        for profile, email in parent_not_user:
            try:
                print(f"  {profile.name}: {email}")
            except Exception:
                print(f"  Profile #{profile.id}: {email}")

    return created, parent_not_user


def step4_summary():
    """Print a summary of the current state."""
    from app.extensions import db
    from app.models.umpire_profile import UmpireProfile
    from app.models.umpire_guardian import UmpireGuardian

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # Profiles summary
    result = db.session.execute(db.text('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN assignr_id IS NOT NULL AND assignr_id != '' THEN 1 ELSE 0 END) as with_assignr,
            SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as no_user,
            SUM(CASE WHEN parent_email IS NOT NULL THEN 1 ELSE 0 END) as with_parent_email
        FROM sdll_umpire_profiles
        WHERE status = 'active'
    '''))
    row = result.fetchone()
    print(f"\nActive Umpire Profiles: {row[0]}")
    print(f"  With Assignr ID: {row[1]}")
    print(f"  Without linked user (managed): {row[2]}")
    print(f"  With parent email: {row[3]}")

    # Guardian relationships
    result = db.session.execute(db.text('SELECT COUNT(*) FROM sdll_umpire_guardians'))
    print(f"\nGuardian relationships: {result.fetchone()[0]}")

    # Users with umpire role but no profile
    result = db.session.execute(db.text('''
        SELECT COUNT(*)
        FROM sdll_users u
        LEFT JOIN sdll_umpire_profiles p ON u.ID = p.user_id
        WHERE u.role LIKE "%umpire%"
        AND u.active = 1
        AND p.id IS NULL
    '''))
    print(f"Users with umpire role but no profile: {result.fetchone()[0]}")


def run_sync(dry_run=True, step='all', csv_path=None):
    """Run the sync process."""
    from app import create_app

    app = create_app()

    # Default CSV path
    if csv_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        csv_path = os.path.join(project_root, 'docs', 'Fall2026AcademyRegistration.csv')

    with app.app_context():
        print("=" * 60)
        print(f"UMPIRE DATA SYNC {'(DRY RUN)' if dry_run else ''}")
        print("=" * 60)

        if step in ('all', 'registration'):
            step0_import_registration_data(csv_path, dry_run)

        if step in ('all', 'profiles'):
            step1_create_missing_profiles(dry_run)

        if step in ('all', 'assignr'):
            step2_link_assignr_officials(dry_run)

        if step in ('all', 'guardians'):
            step3_create_guardian_relationships(dry_run)

        step4_summary()

        print("\n" + "=" * 60)
        if dry_run:
            print("This was a DRY RUN. No changes were made.")
            print("Run without --dry-run to apply changes.")
        else:
            print("Sync complete!")
        print("=" * 60)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Sync umpire data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without applying them')
    parser.add_argument('--step', type=str, default='all',
                        choices=['all', 'registration', 'profiles', 'assignr', 'guardians'],
                        help='Run only specific step')
    parser.add_argument('--csv', type=str, default=None,
                        help='Path to registration CSV')

    args = parser.parse_args()

    run_sync(dry_run=args.dry_run, step=args.step, csv_path=args.csv)
