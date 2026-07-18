#!/usr/bin/env python
"""
Derive field slots from existing game data.

This script analyzes games from a source season and creates field slots
based on the actual usage patterns.

Usage:
    python scripts/derive_field_slots.py --year 2025 --season fall
    python scripts/derive_field_slots.py --year 2025 --season fall --target-year 2026
    python scripts/derive_field_slots.py --year 2025 --season fall --dry-run

Options:
    --year          Source year to analyze (e.g., 2025)
    --season        'fall' or 'spring'
    --target-year   Year to create slots for (defaults to source year)
    --target-season Season to create slots for (defaults to source season)
    --dry-run       Show what would be created without doing it
"""

import os
import sys
import argparse
from datetime import datetime, time
from collections import defaultdict

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from cryptography.fernet import Fernet
if not os.environ.get('ENCRYPTION_KEY'):
    os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from app import create_app, db
from app.models.game import Game
from app.models.field import Field
from app.models.field_slot import FieldSlot


def derive_field_slots(source_year, source_is_spring, target_year=None, target_is_spring=None, dry_run=False):
    """Analyze games and derive field slots."""
    app = create_app('development')

    with app.app_context():
        # Default target to source if not specified
        if target_year is None:
            target_year = source_year
        if target_is_spring is None:
            target_is_spring = source_is_spring

        source_name = f'{"Spring" if source_is_spring else "Fall"} {source_year}'
        target_name = f'{"Spring" if target_is_spring else "Fall"} {target_year}'

        print(f"\nAnalyzing games from: {source_name}")
        print(f"Creating slots for: {target_name}")

        # Check if target season already has slots
        existing_slots = FieldSlot.query.filter_by(
            year=target_year,
            is_spring=target_is_spring,
            active=1
        ).count()

        if existing_slots > 0:
            print(f"\nWARNING: {target_name} already has {existing_slots} field slots.")
            if not dry_run:
                confirm = input("Delete existing slots and recreate? (yes/no): ")
                if confirm.lower() != 'yes':
                    print("Cancelled.")
                    return
                FieldSlot.hard_delete_season_slots(target_year, target_is_spring)
                print(f"Deleted {existing_slots} existing slots.")

        # Get all games for source season
        games = Game.query.filter_by(
            year=source_year,
            is_spring=source_is_spring,
            active=1
        ).all()

        print(f"Found {len(games)} games to analyze")

        # Build a mapping of location -> field ID
        fields = Field.query.filter_by(active=1).all()
        location_to_field_id = {f.location_title: f.ID for f in fields}

        # Also check for alternate names
        for field in fields:
            if hasattr(field, 'alternate_names'):
                for alt in field.alternate_names:
                    location_to_field_id[alt.alternate_name] = field.ID

        # Analyze games to find unique (field, day, time) combinations
        # Key: (field_ID, day_of_week, start_time, league)
        # Value: count of games
        slot_patterns = defaultdict(lambda: {'count': 0, 'leagues': set()})

        unmatched_locations = set()

        for game in games:
            if not game.game_date or not game.location:
                continue

            # Find field_ID for this location
            field_id = location_to_field_id.get(game.location)
            if not field_id:
                unmatched_locations.add(game.location)
                continue

            # Extract day of week (0=Monday, 6=Sunday)
            day_of_week = game.game_date.weekday()

            # Extract start time
            start_time = game.game_date.time()

            # Round to nearest 15 minutes for consistency
            minutes = start_time.minute
            rounded_minutes = round(minutes / 15) * 15
            if rounded_minutes == 60:
                start_hour = start_time.hour + 1
                rounded_minutes = 0
            else:
                start_hour = start_time.hour
            start_time = time(start_hour, rounded_minutes)

            # Calculate end time (assume 1.5 hour games by default)
            duration = game.duration_in_hours if game.duration_in_hours else 1.5
            end_minutes = int(start_time.hour * 60 + start_time.minute + duration * 60)
            end_time = time(end_minutes // 60, end_minutes % 60)

            # Create key (without league - we'll track leagues separately)
            key = (field_id, day_of_week, start_time, end_time)
            slot_patterns[key]['count'] += 1
            if game.league:
                slot_patterns[key]['leagues'].add(game.league)

        if unmatched_locations:
            print(f"\nWARNING: {len(unmatched_locations)} locations could not be matched to fields:")
            for loc in sorted(unmatched_locations)[:10]:
                print(f"  - {loc}")
            if len(unmatched_locations) > 10:
                print(f"  ... and {len(unmatched_locations) - 10} more")

        # Convert patterns to slots
        print(f"\nFound {len(slot_patterns)} unique field/day/time combinations")

        # Group by field for display
        slots_by_field = defaultdict(list)
        for (field_id, day_of_week, start_time, end_time), data in slot_patterns.items():
            field = Field.query.get(field_id)
            field_name = field.location_title if field else f"Field {field_id}"
            slots_by_field[field_name].append({
                'field_id': field_id,
                'day_of_week': day_of_week,
                'start_time': start_time,
                'end_time': end_time,
                'count': data['count'],
                'leagues': data['leagues']
            })

        # Sort slots within each field
        for field_name in slots_by_field:
            slots_by_field[field_name].sort(key=lambda x: (x['day_of_week'], x['start_time']))

        # Display summary
        print(f"\n{'=' * 60}")
        print("FIELD SLOT SUMMARY")
        print(f"{'=' * 60}")

        total_slots = 0
        for field_name in sorted(slots_by_field.keys()):
            slots = slots_by_field[field_name]
            print(f"\n{field_name} ({len(slots)} slots):")
            for slot in slots:
                day = FieldSlot.DAY_ABBREV[slot['day_of_week']]
                start = slot['start_time'].strftime('%I:%M %p').lstrip('0')
                end = slot['end_time'].strftime('%I:%M %p').lstrip('0')
                leagues = ', '.join(sorted(slot['leagues'])) if slot['leagues'] else 'Any'
                print(f"  {day} {start}-{end} ({slot['count']} games) - {leagues}")
                total_slots += 1

        print(f"\n{'=' * 60}")
        print(f"Total slots to create: {total_slots}")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return

        # Create the slots
        print(f"\nCreating {total_slots} field slots...")
        created = 0

        for field_name, slots in slots_by_field.items():
            for slot_data in slots:
                # Determine league (if only one league uses this slot)
                leagues = slot_data['leagues']
                league = list(leagues)[0] if len(leagues) == 1 else None

                slot = FieldSlot(
                    active=1,
                    field_ID=slot_data['field_id'],
                    year=target_year,
                    is_spring=target_is_spring,
                    day_of_week=slot_data['day_of_week'],
                    start_time=slot_data['start_time'],
                    end_time=slot_data['end_time'],
                    league=league,
                    is_owned=1,  # Assume SDLL owns - adjust manually for away slots
                    notes=f"Derived from {source_name} ({slot_data['count']} games)"
                )
                db.session.add(slot)
                created += 1

        db.session.commit()
        print(f"Created {created} field slots for {target_name}")


def main():
    parser = argparse.ArgumentParser(description='Derive field slots from game data.')
    parser.add_argument('--year', type=int, required=True, help='Source year (e.g., 2025)')
    parser.add_argument('--season', choices=['fall', 'spring'], required=True, help='Source season')
    parser.add_argument('--target-year', type=int, help='Target year (defaults to source)')
    parser.add_argument('--target-season', choices=['fall', 'spring'], help='Target season (defaults to source)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created')

    args = parser.parse_args()

    source_is_spring = 1 if args.season == 'spring' else 0
    target_is_spring = None
    if args.target_season:
        target_is_spring = 1 if args.target_season == 'spring' else 0

    derive_field_slots(
        source_year=args.year,
        source_is_spring=source_is_spring,
        target_year=args.target_year,
        target_is_spring=target_is_spring,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    main()
