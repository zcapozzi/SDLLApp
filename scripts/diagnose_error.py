#!/usr/bin/env python
"""
Helper script for diagnosing production errors with Claude Code.

Usage:
    python scripts/diagnose_error.py              # List pending errors
    python scripts/diagnose_error.py <error_id>  # Show error details
    python scripts/diagnose_error.py --mark-fixed <error_id>  # Mark as fixed
    python scripts/diagnose_error.py --mark-skipped <error_id>  # Mark as skipped

This script is designed to be used WITH Claude Code, not as a standalone tool.
Claude Code reads the error details and proposes fixes interactively.

Main workflow:
    claude "Diagnose and fix pending production errors"
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
from dotenv import load_dotenv
load_dotenv()

from app.services.error_diagnosis_service import ErrorDiagnosisService

ERRORS_DIR = Path(__file__).parent.parent / 'errors'
DIAGNOSIS_ATTEMPTS_FILE = ERRORS_DIR / '.diagnosis_attempts.json'
STATE_FILE = ERRORS_DIR / '.state.json'


def get_diagnosis_attempts():
    """Load diagnosis attempts per error hash."""
    if DIAGNOSIS_ATTEMPTS_FILE.exists():
        try:
            return json.loads(DIAGNOSIS_ATTEMPTS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_diagnosis_attempts(attempts):
    """Save diagnosis attempts."""
    DIAGNOSIS_ATTEMPTS_FILE.write_text(json.dumps(attempts, indent=2))


def update_state_on_diagnosis():
    """Update state after a diagnosis."""
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            state = {}
    else:
        state = {}

    state['diagnoses_today'] = state.get('diagnoses_today', 0) + 1
    state['last_diagnosis'] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def list_pending():
    """List all pending error files."""
    pending = ErrorDiagnosisService.get_pending_errors()
    if not pending:
        print("No pending errors to diagnose.")
        print("\nTo poll for new errors, run:")
        print("  python scripts/poll_errors.py")
        return

    print(f"\n{len(pending)} pending errors:\n")
    for f in pending:
        try:
            data = json.loads(f.read_text())
            print(f"  [{data['id']}] {data['error_type']}")
            print(f"       Message: {data['error_message'][:60]}...")
            print(f"       Path: {data['request_path']}")
            print(f"       Context: {data['context']}")
            print()
        except Exception as e:
            print(f"  {f.name} (could not read: {e})")

    print("\nTo diagnose an error:")
    print("  python scripts/diagnose_error.py <error_id>")
    print("\nOr with Claude Code:")
    print("  claude 'Diagnose and fix production error <error_id>'")


def show_error(error_id):
    """Show full error details for Claude Code to analyze."""
    # Try to read from pending file first
    details = ErrorDiagnosisService.get_error_details(error_id)

    if details:
        print(f"\n{'='*60}")
        print(f"ERROR #{details['id']}")
        print(f"{'='*60}\n")
        print(f"Type: {details['error_type']}")
        print(f"Message: {details['error_message']}")
        print(f"Context: {details['context']}")
        print(f"\nRequest:")
        print(f"  Method: {details['request_method']}")
        print(f"  Path: {details['request_path']}")
        print(f"  User ID: {details['user_id']}")
        print(f"  Time: {details['created_at']}")
        print(f"\nTraceback:")
        print("-" * 60)
        print(details['traceback'] or 'No traceback available')
        print("-" * 60)

        # Show markdown file path for full instructions
        md_file = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{error_id}.md"
        if md_file.exists():
            print(f"\nFull instructions: {md_file}")

        # Record that we've looked at this error
        attempts = get_diagnosis_attempts()
        error_hash = details.get('error_hash', str(error_id))
        if error_hash not in attempts:
            attempts[error_hash] = {'attempts': 0, 'last_attempt': None}
        attempts[error_hash]['attempts'] += 1
        attempts[error_hash]['last_attempt'] = datetime.now().isoformat()
        save_diagnosis_attempts(attempts)

        return details

    # Try to fetch from database
    from app import create_app
    from app.models.app_error import AppError

    app = create_app()
    with app.app_context():
        error = AppError.query.get(error_id)
        if error:
            print(f"\n{'='*60}")
            print(f"ERROR #{error.id} (from database)")
            print(f"{'='*60}\n")
            print(f"Type: {error.error_type}")
            print(f"Message: {error.error_message}")
            print(f"Context: {error.context}")
            print(f"Resolved: {error.resolved}")
            print(f"\nRequest:")
            print(f"  Method: {error.request_method}")
            print(f"  Path: {error.request_path}")
            print(f"  User ID: {error.user_id}")
            print(f"  Time: {error.created_at}")
            print(f"\nTraceback:")
            print("-" * 60)
            print(error.traceback or 'No traceback available')
            print("-" * 60)
            return error
        else:
            print(f"Error {error_id} not found.")
            return None


def mark_fixed(error_id):
    """Mark an error as fixed."""
    from app import create_app
    from app.models.app_error import AppError

    # Move file to diagnosed
    ErrorDiagnosisService.mark_diagnosed(error_id, 'fixed')

    # Update diagnosis attempts
    details = ErrorDiagnosisService.get_error_details(error_id)
    if details:
        attempts = get_diagnosis_attempts()
        error_hash = details.get('error_hash', str(error_id))
        if error_hash not in attempts:
            attempts[error_hash] = {}
        attempts[error_hash]['outcome'] = 'fixed'
        attempts[error_hash]['fixed_at'] = datetime.now().isoformat()
        save_diagnosis_attempts(attempts)

    # Mark resolved in database
    app = create_app()
    with app.app_context():
        error = AppError.query.get(error_id)
        if error:
            error.resolved = True
            error.resolved_at = datetime.utcnow()
            from app.extensions import db
            db.session.commit()
            print(f"Marked error {error_id} as fixed in database.")
        else:
            print(f"Error {error_id} not found in database (file moved).")

    # Update state
    update_state_on_diagnosis()
    print(f"Error {error_id} marked as fixed.")


def mark_skipped(error_id, reason="manually skipped"):
    """Mark an error as skipped."""
    # Move file to diagnosed
    ErrorDiagnosisService.mark_diagnosed(error_id, 'skipped')

    # Update diagnosis attempts
    details = ErrorDiagnosisService.get_error_details(error_id)
    if details:
        attempts = get_diagnosis_attempts()
        error_hash = details.get('error_hash', str(error_id))
        if error_hash not in attempts:
            attempts[error_hash] = {}
        attempts[error_hash]['outcome'] = 'skipped'
        attempts[error_hash]['skipped_at'] = datetime.now().isoformat()
        attempts[error_hash]['skip_reason'] = reason
        save_diagnosis_attempts(attempts)

    print(f"Error {error_id} marked as skipped: {reason}")


def main():
    parser = argparse.ArgumentParser(description='Diagnose production errors')
    parser.add_argument('error_id', nargs='?', type=int, help='Error ID to show')
    parser.add_argument('--mark-fixed', type=int, metavar='ID', help='Mark error as fixed')
    parser.add_argument('--mark-skipped', type=int, metavar='ID', help='Mark error as skipped')
    parser.add_argument('--reason', default='manually skipped', help='Reason for skipping')

    args = parser.parse_args()

    if args.mark_fixed:
        mark_fixed(args.mark_fixed)
    elif args.mark_skipped:
        mark_skipped(args.mark_skipped, args.reason)
    elif args.error_id:
        show_error(args.error_id)
    else:
        list_pending()


if __name__ == '__main__':
    main()
