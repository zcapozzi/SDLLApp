#!/usr/bin/env python
"""
Poll production database for new errors and export for Claude Code diagnosis.

Run via Windows Task Scheduler every 5 minutes:
  schtasks /create /tn "SDLL Error Poll" /tr "python scripts\\poll_errors.py" /sc minute /mo 5

Or run manually:
  python scripts/poll_errors.py

Commands:
  python scripts/poll_errors.py           # Poll for new errors
  python scripts/poll_errors.py --status  # Show current state and limits
  python scripts/poll_errors.py --resume  # Clear PAUSED state
  python scripts/poll_errors.py --list    # List pending errors
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment for database connection
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
ERRORS_DIR = Path(__file__).parent.parent / 'errors'
PENDING_DIR = ERRORS_DIR / 'pending'
PAUSE_FILE = ERRORS_DIR / 'PAUSED'
STATE_FILE = ERRORS_DIR / '.state.json'
EXPORTED_FILE = ERRORS_DIR / '.exported_ids.json'
DIAGNOSIS_ATTEMPTS_FILE = ERRORS_DIR / '.diagnosis_attempts.json'

# Rate limits
MAX_ERRORS_PER_HOUR = 5       # Pause if > 5 errors in 1 hour
MAX_DIAGNOSES_PER_DAY = 10    # Max 10 diagnoses per day
COOLDOWN_MINUTES = 10         # Wait between diagnoses
MAX_ATTEMPTS_PER_ERROR = 2    # Don't retry same error too many times

# Contexts to skip (non-critical)
SKIP_CONTEXTS = {'tracking', 'analytics', 'page_view', 'ad_impression', 'ad_click'}

# Bot patterns to skip
BOT_PATTERNS = ['bot', 'crawler', 'spider', 'curl', 'wget', 'python-requests']

# Paths to skip
SKIP_PATHS = ['/health', '/favicon', '/static/', '/robots.txt', '/.well-known']


def load_state():
    """Load current state from file."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            # Reset hourly counter if hour changed
            last_hour = data.get('last_hour_reset', '')
            current_hour = datetime.now().strftime('%Y-%m-%d-%H')
            if last_hour != current_hour:
                data['errors_this_hour'] = 0
                data['last_hour_reset'] = current_hour
            # Reset daily counter if day changed
            last_day = data.get('last_day_reset', '')
            current_day = datetime.now().strftime('%Y-%m-%d')
            if last_day != current_day:
                data['diagnoses_today'] = 0
                data['last_day_reset'] = current_day
            return data
        except Exception:
            pass
    return {
        'errors_this_hour': 0,
        'diagnoses_today': 0,
        'last_diagnosis': None,
        'last_hour_reset': datetime.now().strftime('%Y-%m-%d-%H'),
        'last_day_reset': datetime.now().strftime('%Y-%m-%d'),
    }


def save_state(state):
    """Save state to file."""
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_exported_ids():
    """Load list of already-exported error IDs."""
    if EXPORTED_FILE.exists():
        try:
            return set(json.loads(EXPORTED_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_exported_ids(ids):
    """Save list of exported error IDs."""
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTED_FILE.write_text(json.dumps(list(ids)))


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


def is_paused():
    """Check if system is paused."""
    return PAUSE_FILE.exists()


def pause_system(reason):
    """Pause the system and alert admin."""
    PAUSE_FILE.write_text(f"Paused at {datetime.now()}\nReason: {reason}")
    send_notification(f"⚠️ Error diagnosis PAUSED: {reason}\n\nTo resume: delete errors/PAUSED")
    print(f"[PAUSED] {reason}")


def resume_system():
    """Resume the system."""
    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink()
        print("[RESUMED] Error polling resumed.")
        return True
    print("[INFO] System was not paused.")
    return False


def is_error_skipped(error_id):
    """Check if error is marked to skip."""
    skip_file = ERRORS_DIR / f'SKIP_{error_id}'
    return skip_file.exists()


def should_diagnose(error):
    """
    Check if an error should be diagnosed.

    Returns:
        (bool, str) - (should_diagnose, reason_if_not)
    """
    # Tier I only (500 errors)
    if error.tier != 1:
        return False, "Not Tier I"

    # Skip certain contexts (non-critical)
    if error.context in SKIP_CONTEXTS:
        return False, f"Skipped context: {error.context}"

    # Skip bot/crawler requests
    ua = (error.request_user_agent or '').lower()
    for pattern in BOT_PATTERNS:
        if pattern in ua:
            return False, f"Bot request: {pattern}"

    # Skip health check / favicon / static
    path = error.request_path or ''
    for skip_path in SKIP_PATHS:
        if path.startswith(skip_path):
            return False, f"Skipped path: {path}"

    # Skip if manually marked to skip
    if is_error_skipped(error.id):
        return False, "Manually skipped"

    # Check diagnosis attempts for this error hash
    attempts = get_diagnosis_attempts()
    if error.error_hash in attempts:
        attempt_data = attempts[error.error_hash]
        if attempt_data.get('attempts', 0) >= MAX_ATTEMPTS_PER_ERROR:
            return False, f"Max attempts ({MAX_ATTEMPTS_PER_ERROR}) reached"
        if attempt_data.get('outcome') == 'fixed':
            return False, "Already fixed"

    return True, ""


def check_circuit_breaker(new_error_count):
    """
    Check if we should pause due to high volume.

    Returns:
        (bool, str) - (can_proceed, reason_if_not)
    """
    state = load_state()

    # Too many errors?
    if state['errors_this_hour'] + new_error_count > MAX_ERRORS_PER_HOUR:
        pause_system(f"High error volume: {state['errors_this_hour'] + new_error_count} errors in 1 hour")
        return False, "High error volume"

    # Too many diagnoses today?
    if state['diagnoses_today'] >= MAX_DIAGNOSES_PER_DAY:
        return False, f"Daily diagnosis limit reached ({MAX_DIAGNOSES_PER_DAY})"

    # Still in cool-down?
    if state['last_diagnosis']:
        try:
            last = datetime.fromisoformat(state['last_diagnosis'])
            elapsed = datetime.now() - last
            if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
                remaining = COOLDOWN_MINUTES - int(elapsed.total_seconds() / 60)
                return False, f"Cool-down period ({remaining} min remaining)"
        except Exception:
            pass

    return True, ""


def send_notification(message):
    """Send notification via Telegram."""
    try:
        import subprocess
        script_path = r"C:\Users\zcapo\Documents\workspace\send_message.py"

        if not os.path.exists(script_path):
            return False

        # Replace newlines for command line
        safe_message = message.replace('\n', '<BR>')

        subprocess.run(
            ['python', script_path, '-msg', safe_message, '--telegram-alert'],
            capture_output=True,
            timeout=30
        )
        return True
    except Exception:
        return False


def poll_and_export():
    """Check for new errors and export them."""
    # Check if paused
    if is_paused():
        print(f"[{datetime.now()}] System is PAUSED. Run with --resume to clear.")
        return

    from app import create_app
    from app.models.app_error import AppError
    from app.services.error_diagnosis_service import ErrorDiagnosisService

    app = create_app()

    with app.app_context():
        # Get errors from last 24 hours that aren't resolved
        cutoff = datetime.utcnow() - timedelta(hours=24)
        errors = AppError.query.filter(
            AppError.created_at >= cutoff,
            AppError.resolved == False,
            AppError.tier == 1  # Only Tier I (500 errors)
        ).all()

        if not errors:
            print(f"[{datetime.now()}] No new Tier I errors.")
            return

        # Filter to only exportable errors
        exported_ids = get_exported_ids()
        exportable = []
        for error in errors:
            if error.id in exported_ids:
                continue
            should, reason = should_diagnose(error)
            if should:
                exportable.append(error)
            else:
                print(f"  Skipping error {error.id}: {reason}")

        if not exportable:
            print(f"[{datetime.now()}] {len(errors)} errors found, none exportable.")
            return

        # Check circuit breaker
        can_proceed, reason = check_circuit_breaker(len(exportable))
        if not can_proceed:
            print(f"[{datetime.now()}] Cannot proceed: {reason}")
            return

        print(f"[{datetime.now()}] Found {len(exportable)} new errors to export.")

        # Update state
        state = load_state()
        state['errors_this_hour'] += len(exportable)
        save_state(state)

        for error in exportable:
            file_path = ErrorDiagnosisService.export_for_diagnosis(error)
            print(f"  Exported error {error.id} to {file_path}")
            exported_ids.add(error.id)

        save_exported_ids(exported_ids)

        # Send notification
        if os.environ.get('NOTIFY_ON_NEW_ERRORS') == '1':
            message = f"🔍 {len(exportable)} new error(s) ready for diagnosis\n\n"
            for e in exportable[:5]:  # Show first 5
                message += f"• [{e.id}] {e.error_type}: {e.error_message[:50]}...\n"
            message += f"\nRun: claude 'Diagnose pending errors'"
            send_notification(message)


def show_status():
    """Show current state and limits."""
    print("\n=== Error Diagnosis System Status ===\n")

    # Paused?
    if is_paused():
        content = PAUSE_FILE.read_text()
        print(f"🔴 SYSTEM PAUSED")
        print(f"   {content}")
        print()
    else:
        print("🟢 System Active")
        print()

    # State
    state = load_state()
    print("Rate Limits:")
    print(f"  Errors this hour: {state['errors_this_hour']} / {MAX_ERRORS_PER_HOUR}")
    print(f"  Diagnoses today: {state['diagnoses_today']} / {MAX_DIAGNOSES_PER_DAY}")
    if state['last_diagnosis']:
        print(f"  Last diagnosis: {state['last_diagnosis']}")
    print()

    # Pending errors
    from app.services.error_diagnosis_service import ErrorDiagnosisService
    pending = ErrorDiagnosisService.get_pending_errors()
    print(f"Pending Errors: {len(pending)}")
    for f in pending[:5]:
        try:
            data = json.loads(f.read_text())
            print(f"  [{data['id']}] {data['error_type']}: {data['error_message'][:50]}...")
        except Exception:
            print(f"  {f.name} (could not read)")
    if len(pending) > 5:
        print(f"  ... and {len(pending) - 5} more")
    print()

    # Exported IDs
    exported = get_exported_ids()
    print(f"Total Exported: {len(exported)} errors")
    print()

    # Diagnosis attempts
    attempts = get_diagnosis_attempts()
    print(f"Diagnosis Attempts Tracked: {len(attempts)} error hashes")


def list_pending():
    """List all pending error files."""
    from app.services.error_diagnosis_service import ErrorDiagnosisService

    pending = ErrorDiagnosisService.get_pending_errors()
    if not pending:
        print("No pending errors to diagnose.")
        return

    print(f"\n{len(pending)} pending errors:\n")
    for f in pending:
        try:
            data = json.loads(f.read_text())
            print(f"  [{data['id']}] {data['error_type']}: {data['error_message'][:60]}...")
            print(f"       Path: {data['request_path']}")
            print(f"       Time: {data['created_at']}")
            print()
        except Exception:
            print(f"  {f.name} (could not read)")


def main():
    parser = argparse.ArgumentParser(description='Poll for production errors')
    parser.add_argument('--status', action='store_true', help='Show current state')
    parser.add_argument('--resume', action='store_true', help='Clear PAUSED state')
    parser.add_argument('--list', action='store_true', help='List pending errors')
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.resume:
        resume_system()
    elif args.list:
        list_pending()
    else:
        poll_and_export()


if __name__ == '__main__':
    main()
