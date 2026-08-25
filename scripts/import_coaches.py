#!/usr/bin/env python3
"""
Import coaches from f2026_coaches.json into sdll_users and sdll_coaches tables.

Run this script from the project root:
    python scripts/import_coaches.py

Prerequisites:
    1. Run scripts/create_coaches_table.sql first
    2. Set ENCRYPTION_KEY environment variable (or use app config)
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.utils.encryption import encrypt_value, hash_for_lookup
from werkzeug.security import generate_password_hash


def import_coaches():
    """Import coaches from JSON file."""
    app = create_app()

    with app.app_context():
        # Load coach data
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'f2026_coaches.json')
        with open(json_path, 'r') as f:
            coaches = json.load(f)

        print(f"Found {len(coaches)} coaches to import")

        imported = 0
        skipped = 0
        errors = []

        for coach in coaches:
            first_name = coach.get('first_name', '').strip()
            last_name = coach.get('last_name', '').strip()
            email = coach.get('email')
            phone = coach.get('phone')
            sport = coach.get('sport', 'baseball')

            full_name = f"{first_name} {last_name}"

            # Skip coaches without email (can't create user without it)
            if not email:
                print(f"  SKIP (no email): {full_name}")
                skipped += 1
                continue

            email = email.strip().lower()

            # Check if user already exists
            email_hash = hash_for_lookup(email)
            existing_user = User.query.filter_by(email_hash=email_hash).first()

            if existing_user:
                print(f"  EXISTS: {full_name} ({email})")
                # Still add to sdll_coaches if not already there
                add_to_coaches_table(existing_user.ID, sport)
                skipped += 1
                continue

            # Determine role - Ben Porche gets coach|treasurer
            if first_name.lower() == 'benjamin' and last_name.lower() == 'porche':
                role = 'coach|treasurer'
            else:
                role = 'coach'

            try:
                # Create new user
                user = User(
                    _email=encrypt_value(email),
                    email_hash=email_hash,
                    _name=encrypt_value(full_name),
                    _phone=encrypt_value(phone) if phone else None,
                    password_hash=generate_password_hash('NEEDS_RESET_' + os.urandom(8).hex()),
                    role=role,
                    active=1,
                    org_ID=1
                )

                db.session.add(user)
                db.session.flush()  # Get the ID

                # Add to sdll_coaches table
                add_to_coaches_table(user.ID, sport)

                print(f"  ADDED: {full_name} ({email}) - {role} - {sport}")
                imported += 1

            except Exception as e:
                errors.append(f"{full_name}: {str(e)}")
                print(f"  ERROR: {full_name} - {str(e)}")
                db.session.rollback()

        # Commit all changes
        db.session.commit()

        print(f"\n{'='*50}")
        print(f"Import complete:")
        print(f"  Imported: {imported}")
        print(f"  Skipped:  {skipped}")
        print(f"  Errors:   {len(errors)}")

        if errors:
            print(f"\nErrors:")
            for error in errors:
                print(f"  - {error}")


def add_to_coaches_table(user_id, sport):
    """Add user to sdll_coaches table if not already there."""
    # Check if already exists
    result = db.session.execute(
        db.text("""
            SELECT id FROM sdll_coaches
            WHERE user_id = :user_id AND season_year = 2026 AND is_spring = 1
        """),
        {'user_id': user_id}
    ).fetchone()

    if result:
        return  # Already exists

    # Insert into sdll_coaches
    db.session.execute(
        db.text("""
            INSERT INTO sdll_coaches (user_id, sport, season_year, is_spring, active)
            VALUES (:user_id, :sport, 2026, 1, 1)
        """),
        {'user_id': user_id, 'sport': sport}
    )


if __name__ == '__main__':
    import_coaches()
