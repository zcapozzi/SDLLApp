#!/usr/bin/env python
"""
Revert a season by deleting all its data.

This is useful when you've copied a season and want to start over.

Usage:
    python scripts/revert_season.py --year 2026 --season fall --dry-run
    python scripts/revert_season.py --year 2026 --season fall
    python scripts/revert_season.py --year 2026 --season fall --hard-delete

What gets deleted (in order):
    1. Games (references teams)
    2. Teams (includes placeholders)
    3. Field slots
    4. League configs

Options:
    --year          Year of the season (e.g., 2026)
    --season        'fall' or 'spring'
    --hard-delete   Permanently delete (default is soft delete)
    --dry-run       Show what would be deleted without doing it
    --yes           Skip confirmation prompt
"""

import os
import sys
import argparse

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
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.field_slot import FieldSlot
from app.models.league_season import LeagueSeason


def revert_season(year, is_spring, hard_delete=False, dry_run=False, skip_confirm=False):
    """Delete all data for a season."""
    app = create_app('development')

    with app.app_context():
        season_name = f'{"Spring" if is_spring else "Fall"} {year}'

        # Get current counts
        counts = {
            'games': Game.query.filter_by(year=year, is_spring=is_spring, active=1).count(),
            'teams': TeamSeason.query.filter_by(year=year, is_spring=is_spring, active=1, is_placeholder=0).count(),
            'placeholders': TeamSeason.query.filter_by(year=year, is_spring=is_spring, active=1, is_placeholder=1).count(),
            'slots': FieldSlot.query.filter_by(year=year, is_spring=is_spring, active=1).count(),
            'league_configs': LeagueSeason.query.filter_by(year=year, is_spring=is_spring, active=1).count(),
        }

        total = sum(counts.values())

        print(f"\n{'='*50}")
        print(f"Season: {season_name}")
        print(f"{'='*50}")
        print(f"Games:            {counts['games']}")
        print(f"Teams:            {counts['teams']}")
        print(f"Placeholders:     {counts['placeholders']}")
        print(f"Field Slots:      {counts['slots']}")
        print(f"League Configs:   {counts['league_configs']}")
        print(f"{'='*50}")
        print(f"TOTAL RECORDS:    {total}")
        print(f"Delete mode:      {'HARD (permanent)' if hard_delete else 'SOFT (can recover)'}")
        print(f"{'='*50}")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return

        if total == 0:
            print("\nNothing to delete.")
            return

        # Confirm
        if not skip_confirm:
            confirm = input(f"\nDelete ALL data for {season_name}? Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("Cancelled.")
                return

        deleted = {'games': 0, 'teams': 0, 'placeholders': 0, 'slots': 0, 'configs': 0}

        # 1. Delete games first (references teams)
        if counts['games'] > 0:
            games = Game.query.filter_by(year=year, is_spring=is_spring, active=1).all()
            for game in games:
                if hard_delete:
                    db.session.delete(game)
                else:
                    game.active = 0
                deleted['games'] += 1
            db.session.commit()
            print(f"Deleted {deleted['games']} games")

        # 2. Delete teams (includes placeholders)
        teams = TeamSeason.query.filter_by(year=year, is_spring=is_spring, active=1).all()
        for team in teams:
            if hard_delete:
                db.session.delete(team)
            else:
                team.active = 0
            if team.is_placeholder:
                deleted['placeholders'] += 1
            else:
                deleted['teams'] += 1
        db.session.commit()
        print(f"Deleted {deleted['teams']} teams, {deleted['placeholders']} placeholders")

        # 3. Delete field slots
        if counts['slots'] > 0:
            slots = FieldSlot.query.filter_by(year=year, is_spring=is_spring, active=1).all()
            for slot in slots:
                if hard_delete:
                    db.session.delete(slot)
                else:
                    slot.active = 0
                deleted['slots'] += 1
            db.session.commit()
            print(f"Deleted {deleted['slots']} field slots")

        # 4. Delete league configs
        if counts['league_configs'] > 0:
            configs = LeagueSeason.query.filter_by(year=year, is_spring=is_spring, active=1).all()
            for config in configs:
                if hard_delete:
                    db.session.delete(config)
                else:
                    config.active = 0
                deleted['configs'] += 1
            db.session.commit()
            print(f"Deleted {deleted['configs']} league configs")

        print(f"\n{season_name} has been completely reverted.")


def main():
    parser = argparse.ArgumentParser(description='Revert a season by deleting all its data.')
    parser.add_argument('--year', type=int, required=True, help='Year (e.g., 2026)')
    parser.add_argument('--season', choices=['fall', 'spring'], required=True, help='Season type')
    parser.add_argument('--hard-delete', action='store_true', help='Permanently delete (not soft delete)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')

    args = parser.parse_args()

    is_spring = 1 if args.season == 'spring' else 0

    revert_season(
        year=args.year,
        is_spring=is_spring,
        hard_delete=args.hard_delete,
        dry_run=args.dry_run,
        skip_confirm=args.yes
    )


if __name__ == '__main__':
    main()
