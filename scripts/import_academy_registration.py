#!/usr/bin/env python
"""Import Academy umpire registration data from CSV.

This script imports umpire registrations, matching against existing profiles
where possible and creating new ones otherwise.

Usage:
    python scripts/import_academy_registration.py [--dry-run] [--csv PATH]

Options:
    --dry-run   Preview what would be imported without making changes
    --csv PATH  Path to CSV file (default: docs/Fall2026AcademyRegistration.csv)
"""

import sys
import os
import csv
import re
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ''
    # Strip whitespace, convert to lowercase
    name = name.strip().lower()
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name)
    return name


def normalize_email(email):
    """Normalize an email for comparison."""
    if not email:
        return ''
    return email.strip().lower()


def normalize_phone(phone):
    """Normalize phone number - extract digits only."""
    if not phone:
        return ''
    return re.sub(r'\D', '', phone)


def parse_registration_csv(csv_path):
    """Parse the registration CSV and extract umpire data.

    The CSV has a header section (rows 1-9) followed by registration data
    starting at row 10 (0-indexed row 9).

    Returns:
        List of dicts with registration data
    """
    registrations = []

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
        if len(row) < 10 or not row[0]:  # Skip empty rows
            continue

        # Build registration dict
        reg = {}
        for i, header in enumerate(headers):
            if i < len(row):
                reg[header] = row[i].strip() if row[i] else ''

        # Extract key fields with better names
        registration = {
            'timestamp': reg.get('Timestamp', ''),
            'first_name': reg.get('First Name', ''),
            'last_name': reg.get('Last name', ''),
            'umpire_email': reg.get('What is your email?', ''),
            'umpire_phone': reg.get('What is your cell phone number, if you have one?', ''),
            'age': reg.get('Age', ''),
            'parent_email': reg.get("What is your parent's email?", ''),
            'parent_phone': reg.get("What is your parent's cell phone number?", ''),
            'played_sdll': reg.get('Did you play in South Durham Little League?', ''),
            'seasons_played': reg.get('How many seasons did you play baseball or softball? (include fall seasons)', ''),
            'highest_level': reg.get('What was the highest level you played at SDLL', ''),
            'travel_team': reg.get('Are you currently playing on a school team or travel ball team that will impact your availability? If so which team(s)? (ex. Githens Middle School Softball. Blues 14u or Orange Crushers 13U) This is for scheduling purposes.', ''),
            'shirt_size': reg.get('Select your adult-sized shirt size', ''),
            'interested_in': reg.get('I am interested in umpiring', ''),  # Baseball, Softball, or both
            'umpired_before': reg.get('Did you umpire for SDLL before?', ''),
            'btp_interest': reg.get('For our experienced umpires and with additional training, are you interested in calling balls and strikes behind the plate for kid pitch divisions?', ''),
        }

        # Only include if we have a name
        if registration['first_name'] and registration['last_name']:
            registrations.append(registration)

    return registrations


def find_matching_profile(registration, profiles_by_email, profiles_by_name):
    """Find an existing profile that matches this registration.

    Matching strategy:
    1. Exact email match (umpire email or parent email) -> definite match
    2. Exact name match + same parent email -> likely match
    3. Name-only match -> flag for review

    Returns:
        Tuple of (profile, match_type) where match_type is 'exact', 'likely', 'name_only', or None
    """
    umpire_email = normalize_email(registration['umpire_email'])
    parent_email = normalize_email(registration['parent_email'])
    full_name = normalize_name(f"{registration['first_name']} {registration['last_name']}")

    # Check exact email match
    if umpire_email and umpire_email in profiles_by_email:
        return profiles_by_email[umpire_email], 'exact_umpire_email'

    if parent_email and parent_email in profiles_by_email:
        return profiles_by_email[parent_email], 'exact_parent_email'

    # Check name match
    if full_name in profiles_by_name:
        profile = profiles_by_name[full_name]
        # If parent email also matches, it's a likely match
        if parent_email and profile.parent_email:
            if normalize_email(profile.parent_email) == parent_email:
                return profile, 'name_and_parent_email'
        # Name-only match - flag for review
        return profile, 'name_only'

    return None, None


def run_import(csv_path, dry_run=True):
    """Run the import process.

    Args:
        csv_path: Path to the CSV file
        dry_run: If True, don't make any changes
    """
    from app import create_app
    from app.extensions import db
    from app.models.umpire_profile import UmpireProfile
    from app.models.org_season import OrgSeason
    from app.utils.encryption import hash_for_lookup

    app = create_app()

    with app.app_context():
        # Parse CSV
        print(f"Parsing {csv_path}...")
        registrations = parse_registration_csv(csv_path)
        print(f"Found {len(registrations)} registrations")

        # Get current season for target_org_season_id
        current_season = OrgSeason.get_current_season()
        season_id = current_season.ID if current_season else None
        print(f"Target season: {current_season.season_name if current_season else 'None'}")

        # Load existing profiles for matching
        existing_profiles = UmpireProfile.query.all()
        print(f"Found {len(existing_profiles)} existing profiles")

        # Build lookup dictionaries
        profiles_by_email = {}
        profiles_by_name = {}

        for profile in existing_profiles:
            try:
                # Index by umpire email
                if profile.umpire_email:
                    profiles_by_email[normalize_email(profile.umpire_email)] = profile
            except Exception:
                pass  # Decryption error - different encryption key

            try:
                # Index by parent email
                if profile.parent_email:
                    profiles_by_email[normalize_email(profile.parent_email)] = profile
            except Exception:
                pass

            # Index by user email (if linked)
            try:
                if profile.user and profile.user.email:
                    profiles_by_email[normalize_email(profile.user.email)] = profile
            except Exception:
                pass

            try:
                # Index by name
                if profile.name:
                    profiles_by_name[normalize_name(profile.name)] = profile
            except Exception:
                pass  # Decryption error

        # Deduplicate registrations within the batch (by email)
        seen_emails = set()
        unique_registrations = []
        duplicates_in_csv = []

        for reg in registrations:
            email_key = normalize_email(reg['umpire_email'])
            if email_key and email_key in seen_emails:
                duplicates_in_csv.append(reg)
            else:
                if email_key:
                    seen_emails.add(email_key)
                unique_registrations.append(reg)

        if duplicates_in_csv:
            print(f"Skipping {len(duplicates_in_csv)} duplicate entries in CSV:")
            for dup in duplicates_in_csv:
                print(f"  - {dup['first_name']} {dup['last_name']} ({dup['umpire_email']})")

        registrations = unique_registrations

        # Process registrations
        results = {
            'exact_match': [],
            'likely_match': [],
            'name_only_match': [],
            'new_profile': [],
            'duplicates_in_csv': duplicates_in_csv,
            'errors': []
        }

        for reg in registrations:
            try:
                profile, match_type = find_matching_profile(
                    reg, profiles_by_email, profiles_by_name
                )

                full_name = f"{reg['first_name']} {reg['last_name']}"

                if match_type in ('exact_umpire_email', 'exact_parent_email'):
                    results['exact_match'].append({
                        'registration': reg,
                        'profile': profile,
                        'match_type': match_type
                    })
                    if not dry_run:
                        # Update profile with any missing info
                        update_profile_from_registration(profile, reg)

                elif match_type == 'name_and_parent_email':
                    results['likely_match'].append({
                        'registration': reg,
                        'profile': profile,
                        'match_type': match_type
                    })
                    if not dry_run:
                        update_profile_from_registration(profile, reg)

                elif match_type == 'name_only':
                    # Flag for manual review
                    results['name_only_match'].append({
                        'registration': reg,
                        'profile': profile,
                        'match_type': match_type
                    })
                    # Don't auto-merge name-only matches

                else:
                    # Create new profile
                    results['new_profile'].append({
                        'registration': reg
                    })
                    if not dry_run:
                        create_profile_from_registration(reg, season_id)

            except Exception as e:
                results['errors'].append({
                    'registration': reg,
                    'error': str(e)
                })

        if not dry_run:
            db.session.commit()

        # Print results
        print("\n" + "=" * 60)
        print("IMPORT RESULTS" + (" (DRY RUN)" if dry_run else ""))
        print("=" * 60)

        print(f"\nExact matches (will update): {len(results['exact_match'])}")
        for item in results['exact_match']:
            reg = item['registration']
            profile = item['profile']
            print(f"  - {reg['first_name']} {reg['last_name']} -> Profile #{profile.id} ({item['match_type']})")

        print(f"\nLikely matches (will update): {len(results['likely_match'])}")
        for item in results['likely_match']:
            reg = item['registration']
            profile = item['profile']
            print(f"  - {reg['first_name']} {reg['last_name']} -> Profile #{profile.id} ({item['match_type']})")

        print(f"\nName-only matches (NEEDS REVIEW): {len(results['name_only_match'])}")
        for item in results['name_only_match']:
            reg = item['registration']
            profile = item['profile']
            print(f"  - {reg['first_name']} {reg['last_name']} ({reg['umpire_email']})")
            print(f"    Potential match: Profile #{profile.id} - {profile.name}")
            if profile.umpire_email:
                print(f"    Profile email: {profile.umpire_email}")

        print(f"\nNew profiles to create: {len(results['new_profile'])}")
        for item in results['new_profile']:
            reg = item['registration']
            status = 'active' if reg['umpired_before'] == 'Yes' else 'prospective'
            print(f"  - {reg['first_name']} {reg['last_name']} ({reg['umpire_email']}) -> {status}")

        if results['errors']:
            print(f"\nErrors: {len(results['errors'])}")
            for item in results['errors']:
                reg = item['registration']
                print(f"  - {reg['first_name']} {reg['last_name']}: {item['error']}")

        print("\n" + "=" * 60)
        if dry_run:
            print("This was a DRY RUN. No changes were made.")
            print("Run without --dry-run to apply changes.")
        else:
            print("Import complete!")


def update_profile_from_registration(profile, reg):
    """Update an existing profile with registration data.

    Only fills in missing fields, doesn't overwrite existing data.
    """
    # Update contact info if missing
    if not profile.umpire_email and reg['umpire_email']:
        profile.umpire_email = reg['umpire_email']

    if not profile.umpire_phone and reg['umpire_phone']:
        profile.umpire_phone = reg['umpire_phone']

    if not profile.parent_email and reg['parent_email']:
        profile.parent_email = reg['parent_email']

    if not profile.parent_phone and reg['parent_phone']:
        profile.parent_phone = reg['parent_phone']

    # Build lead notes
    notes_parts = []
    if reg['interested_in']:
        notes_parts.append(f"Interested in: {reg['interested_in']}")
    if reg['travel_team']:
        notes_parts.append(f"Travel/school team: {reg['travel_team']}")
    if reg['btp_interest']:
        notes_parts.append(f"BTP interest: {reg['btp_interest']}")
    if reg['shirt_size']:
        notes_parts.append(f"Shirt size: {reg['shirt_size']}")

    if notes_parts:
        new_notes = " | ".join(notes_parts)
        if profile.lead_notes:
            if new_notes not in profile.lead_notes:
                profile.lead_notes = f"{profile.lead_notes}\n[Registration {reg['timestamp'][:10]}] {new_notes}"
        else:
            profile.lead_notes = f"[Registration {reg['timestamp'][:10]}] {new_notes}"


def create_profile_from_registration(reg, season_id):
    """Create a new umpire profile from registration data."""
    from app.models.umpire_profile import UmpireProfile

    # Determine status based on prior experience
    if reg['umpired_before'] == 'Yes':
        status = UmpireProfile.STATUS_ACTIVE
    else:
        status = UmpireProfile.STATUS_PROSPECTIVE

    # Build lead notes
    notes_parts = []
    if reg['interested_in']:
        notes_parts.append(f"Interested in: {reg['interested_in']}")
    if reg['travel_team']:
        notes_parts.append(f"Travel/school team: {reg['travel_team']}")
    if reg['btp_interest']:
        notes_parts.append(f"BTP interest: {reg['btp_interest']}")
    if reg['shirt_size']:
        notes_parts.append(f"Shirt size: {reg['shirt_size']}")
    if reg['seasons_played']:
        notes_parts.append(f"Seasons played: {reg['seasons_played']}")
    if reg['highest_level']:
        notes_parts.append(f"Highest level: {reg['highest_level']}")

    lead_notes = " | ".join(notes_parts) if notes_parts else None

    # Create profile using the create_lead method for proper encryption
    profile = UmpireProfile.create_lead(
        first_name=reg['first_name'],
        last_name=reg['last_name'],
        umpire_email=reg['umpire_email'] if reg['umpire_email'] else None,
        umpire_phone=reg['umpire_phone'] if reg['umpire_phone'] else None,
        parent_email=reg['parent_email'] if reg['parent_email'] else None,
        parent_phone=reg['parent_phone'] if reg['parent_phone'] else None,
        lead_source='registration_form',
        lead_notes=lead_notes,
        target_org_season_id=season_id
    )

    # Update status if returning umpire
    if status == UmpireProfile.STATUS_ACTIVE:
        profile.status = status

    return profile


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Import Academy registration CSV')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without applying them')
    parser.add_argument('--csv', type=str,
                        default='docs/Fall2026AcademyRegistration.csv',
                        help='Path to CSV file')

    args = parser.parse_args()

    # Resolve path relative to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    csv_path = os.path.join(project_root, args.csv)

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    run_import(csv_path, dry_run=args.dry_run)
