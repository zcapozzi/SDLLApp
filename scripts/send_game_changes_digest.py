#!/usr/bin/env python
"""
Cron job script to send game changes digest email.

Sends a summary of all game changes made in the past N hours to the umpire
coordinator and admin. Smart enough to detect "net changes" - if a field
was changed and then reverted within the window, it won't be reported.

Usage:
    python scripts/send_game_changes_digest.py [--hours 2] [--dry-run] [--force]

Environment variables:
    GAME_CHANGES_DIGEST_EMAILS: Comma-separated list of recipient emails
    (defaults to admin and umpire coordinator)

Typical cron setup (every 2 hours):
    0 */2 * * * cd /app && python scripts/send_game_changes_digest.py --hours 2
"""

import os
import sys
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.services.game_changes_digest_service import (
    get_changes_with_net_effect,
    send_game_changes_digest,
    get_recipient_emails
)


def main():
    parser = argparse.ArgumentParser(description='Send game changes digest email')
    parser.add_argument('--hours', type=int, default=2,
                        help='Hours to look back (default: 2)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Check changes but do not send email')
    parser.add_argument('--force', action='store_true',
                        help='Send email even if no changes')

    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        print(f"Checking for game changes in the last {args.hours} hour(s)...")

        # Get changes
        changes_data = get_changes_with_net_effect(args.hours)

        if not changes_data:
            print("No game changes found in the time window.")
            if not args.force:
                return 0

        # Summarize what we found
        total_changes = sum(len(item['changes']) for item in changes_data)
        print(f"\nFound {len(changes_data)} game(s) with {total_changes} total change record(s)")

        # Show details
        for item in changes_data:
            game = item['game']
            net_changes = item['net_changes']
            change_types = item['change_types']

            game_date = game.game_date.strftime('%Y-%m-%d %H:%M') if game.game_date else 'TBD'
            print(f"\n  {game.league}: {game_date}")
            print(f"    Types: {', '.join(change_types)}")

            if net_changes:
                print("    Net changes:")
                for field, vals in net_changes.items():
                    print(f"      - {field}: {vals['old']} -> {vals['new']}")
            else:
                print("    (No net field changes - actions only)")

            # Check for reversed changes
            num_changes = len(item['changes'])
            if num_changes > 1 and not net_changes:
                print(f"    (Changes were reversed within the window)")

        if args.dry_run:
            print(f"\n[DRY RUN] Would send digest to: {', '.join(get_recipient_emails())}")
            return 0

        # Send the digest
        print(f"\nSending digest email...")
        result = send_game_changes_digest(hours=args.hours, force=args.force)

        if result['sent']:
            print(f"Digest sent successfully to {', '.join(result['recipients'])}")
            return 0
        else:
            if result['error']:
                print(f"ERROR: {result['error']}")
                return 1
            else:
                print("No email sent (no changes to report)")
                return 0


if __name__ == '__main__':
    sys.exit(main())
