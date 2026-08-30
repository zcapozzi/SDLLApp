#!/usr/bin/env python
"""
Poll production database for new errors and export for Claude Code diagnosis.

DEDUPLICATION BY ERROR HASH:
  - Same bug triggering 100 times = 1 unique error to diagnose
  - Errors are grouped by error_hash (based on traceback/line number)
  - Circuit breaker counts UNIQUE errors, not raw occurrences
  - If one broken endpoint is hit 50 times, we diagnose it once

SINGLE-THREADED DESIGN:
  - Only ONE Claude Code diagnosis runs at a time
  - Uses a lock file to prevent concurrent sessions
  - Additional errors are queued and processed in subsequent polls
  - Prevents git conflicts, resource contention, and competing edits

Run via Windows Task Scheduler every 5 minutes:
  schtasks /create /tn "SDLL Error Poll" /tr "python scripts\\poll_errors.py" /sc minute /mo 5

Or run manually:
  python scripts/poll_errors.py

Commands:
  python scripts/poll_errors.py           # Poll for new errors
  python scripts/poll_errors.py --status  # Show current state and limits
  python scripts/poll_errors.py --resume  # Clear PAUSED state
  python scripts/poll_errors.py --unlock  # Release diagnosis lock (if stuck)
  python scripts/poll_errors.py --list    # List pending errors
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment for database connection
# Use .env.prod for production database access, fall back to .env
from dotenv import load_dotenv
env_prod = PROJECT_ROOT / '.env.prod'
env_local = PROJECT_ROOT / '.env'

if env_prod.exists():
    load_dotenv(env_prod)
    print(f"[Config] Using production credentials from .env.prod")
else:
    load_dotenv(env_local)
    print(f"[Config] Using local credentials from .env (create .env.prod for production)")

# --- Configuration ---
ERRORS_DIR = Path(__file__).parent.parent / 'errors'
PENDING_DIR = ERRORS_DIR / 'pending'
PAUSE_FILE = ERRORS_DIR / 'PAUSED'
STATE_FILE = ERRORS_DIR / '.state.json'
EXPORTED_FILE = ERRORS_DIR / '.exported_ids.json'
DIAGNOSIS_ATTEMPTS_FILE = ERRORS_DIR / '.diagnosis_attempts.json'
LOCK_FILE = ERRORS_DIR / '.diagnosis_in_progress.lock'

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
                data['unique_errors_this_hour'] = 0
                data['last_hour_reset'] = current_hour
            # Reset daily counter if day changed
            last_day = data.get('last_day_reset', '')
            current_day = datetime.now().strftime('%Y-%m-%d')
            if last_day != current_day:
                data['diagnoses_today'] = 0
                data['last_day_reset'] = current_day
            # Migration: rename old key if present
            if 'errors_this_hour' in data and 'unique_errors_this_hour' not in data:
                data['unique_errors_this_hour'] = data.pop('errors_this_hour')
            return data
        except Exception:
            pass
    return {
        'unique_errors_this_hour': 0,
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


def get_exported_hashes():
    """Load set of already-exported error hashes (unique errors)."""
    exported_hashes_file = ERRORS_DIR / '.exported_hashes.json'
    if exported_hashes_file.exists():
        try:
            return set(json.loads(exported_hashes_file.read_text()))
        except Exception:
            pass
    return set()


def save_exported_hashes(hashes):
    """Save set of exported error hashes."""
    exported_hashes_file = ERRORS_DIR / '.exported_hashes.json'
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    exported_hashes_file.write_text(json.dumps(list(hashes)))


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


def is_diagnosis_in_progress():
    """
    Check if a diagnosis is currently in progress.

    Uses a lock file to prevent concurrent diagnoses.
    Lock files older than 2 hours are considered stale (diagnosis crashed).
    """
    if not LOCK_FILE.exists():
        return False

    # Check if lock is stale (older than 2 hours = likely crashed)
    try:
        lock_data = json.loads(LOCK_FILE.read_text())
        lock_time = datetime.fromisoformat(lock_data.get('started', ''))
        age = datetime.now() - lock_time
        if age > timedelta(hours=2):
            print(f"[Warning] Stale lock detected (age: {age}). Removing.")
            LOCK_FILE.unlink()
            return False
        return True
    except Exception:
        # Malformed lock file, remove it
        LOCK_FILE.unlink()
        return False


def acquire_diagnosis_lock(error_id):
    """Acquire lock for diagnosis. Returns True if acquired."""
    if is_diagnosis_in_progress():
        return False

    LOCK_FILE.write_text(json.dumps({
        'error_id': error_id,
        'started': datetime.now().isoformat(),
        'pid': os.getpid()
    }))
    return True


def release_diagnosis_lock():
    """Release the diagnosis lock."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


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
    Check if an error (AppError object) should be diagnosed.

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


def should_diagnose_dict(error):
    """
    Check if an error (dict from DB query) should be diagnosed.

    Returns:
        (bool, str) - (should_diagnose, reason_if_not)
    """
    # Tier I only (500 errors)
    if error['tier'] != 1:
        return False, "Not Tier I"

    # Skip certain contexts (non-critical)
    if error['context'] in SKIP_CONTEXTS:
        return False, f"Skipped context: {error['context']}"

    # Skip bot/crawler requests
    ua = (error.get('request_user_agent') or '').lower()
    for pattern in BOT_PATTERNS:
        if pattern in ua:
            return False, f"Bot request: {pattern}"

    # Skip health check / favicon / static
    path = error.get('request_path') or ''
    for skip_path in SKIP_PATHS:
        if path.startswith(skip_path):
            return False, f"Skipped path: {path}"

    # Skip if manually marked to skip
    if is_error_skipped(error['id']):
        return False, "Manually skipped"

    # Check diagnosis attempts for this error hash
    attempts = get_diagnosis_attempts()
    error_hash = error.get('error_hash')
    if error_hash and error_hash in attempts:
        attempt_data = attempts[error_hash]
        if attempt_data.get('attempts', 0) >= MAX_ATTEMPTS_PER_ERROR:
            return False, f"Max attempts ({MAX_ATTEMPTS_PER_ERROR}) reached"
        if attempt_data.get('outcome') == 'fixed':
            return False, "Already fixed"

    return True, ""


def get_user_email(user_id):
    """Look up user email by ID. Returns None if not found."""
    if not user_id:
        return None
    try:
        from app import create_app
        from app.models.user import User
        app = create_app()
        with app.app_context():
            user = User.query.get(user_id)
            return user.email if user else None
    except Exception:
        return None


def export_error_dict(error):
    """
    Export an error dict to markdown/JSON files for Claude Code analysis.

    Args:
        error: Dict with error fields from database

    Returns:
        Path to the exported markdown file
    """
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    error_id = error['id']
    created_at = error['created_at']
    if hasattr(created_at, 'isoformat'):
        created_at = created_at.isoformat()

    # Look up user email if user_id is available
    user_email = get_user_email(error.get('user_id'))

    # Create markdown file
    md_file = PENDING_DIR / f"error_{error_id}.md"
    content = f"""# Production Error #{error_id}

## Error Details
- **Type**: {error['error_type']}
- **Message**: {error['error_message']}
- **Context**: {error['context']}
- **Time**: {created_at}

## Request Info
- **Method**: {error.get('request_method') or 'N/A'}
- **Path**: {error.get('request_path') or 'N/A'}
- **User ID**: {error.get('user_id') or 'Anonymous'}
- **User Email**: {user_email or 'Unknown'}

## Traceback
```
{error.get('traceback') or 'No traceback available'}
```

## Instructions for Claude Code

Please analyze this production error and follow TDD principles:

1. **Read the affected source files** mentioned in the traceback
2. **Create a reproducing test** in `tests/test_regressions.py`:
   - Test name: `test_regression_error_{error_id}_<brief_description>`
   - The test MUST fail with the same error type before the fix
3. **Run the test** to verify reproduction (should FAIL)
4. **Implement the fix** with minimal code changes
5. **Run the test** again (should PASS now)
6. **Run full test suite**: `python run_tests.py` (no regressions)
7. **Ask for approval** before committing
8. **Commit** the fix AND the new test together

To start diagnosis, run:
```
python scripts/diagnose_error.py {error_id}
```
"""
    md_file.write_text(content)

    # Create JSON file
    json_file = PENDING_DIR / f"error_{error_id}.json"
    json_data = {
        'id': error['id'],
        'error_type': error['error_type'],
        'error_message': error['error_message'],
        'context': error['context'],
        'traceback': error.get('traceback'),
        'request_method': error.get('request_method'),
        'request_path': error.get('request_path'),
        'user_id': error.get('user_id'),
        'user_email': user_email,
        'created_at': created_at,
        'error_hash': error.get('error_hash'),
    }
    json_file.write_text(json.dumps(json_data, indent=2, default=str))

    return md_file


def check_circuit_breaker(unique_error_count):
    """
    Check if we should pause due to high volume of UNIQUE errors.

    IMPORTANT: This counts unique error hashes, not raw error occurrences.
    The same bug triggering 100 times = 1 unique error.
    10 different bugs = 10 unique errors (potential systemic issue).

    Returns:
        (bool, str) - (can_proceed, reason_if_not)
    """
    state = load_state()

    # Too many UNIQUE errors? (indicates systemic issues, not just one bug)
    if state['unique_errors_this_hour'] + unique_error_count > MAX_ERRORS_PER_HOUR:
        pause_system(f"High unique error volume: {state['unique_errors_this_hour'] + unique_error_count} different errors in 1 hour")
        return False, "High unique error volume"

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


def _send_telegram_alert(error_id):
    """Send Telegram alert that Claude Code is diagnosing an error."""
    try:
        import subprocess
        script_path = r"C:\Users\zcapo\Documents\workspace\send_message.py"

        if not os.path.exists(script_path):
            return False

        # Get error details for the message
        error_file = PENDING_DIR / f"error_{error_id}.json"
        error_info = ""
        user_info = ""
        if error_file.exists():
            try:
                data = json.loads(error_file.read_text())
                error_info = f"<BR>Type: {data.get('error_type', 'Unknown')}<BR>Path: {data.get('request_path', 'Unknown')}"
                # Include user email if available (for bug resolution follow-up)
                user_email = data.get('user_email')
                if user_email:
                    user_info = f"<BR>User: {user_email}"
            except:
                pass

        message = f"🔧 Claude Code Diagnosis Started<BR><BR>"
        message += f"Error #{error_id} detected in production.{error_info}{user_info}<BR><BR>"
        message += f"A Claude Code window has been opened on your machine.<BR>"
        message += f"Check your taskbar to interact with the diagnosis."

        subprocess.Popen(
            ['python', script_path, '-msg', message, '--telegram-alert'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False


def poll_and_export():
    """Check for new errors and export them."""
    import pymysql

    # Check if paused
    if is_paused():
        print(f"[{datetime.now()}] System is PAUSED. Run with --resume to clear.")
        return

    from app.services.error_diagnosis_service import ErrorDiagnosisService

    # Connect directly to production database using .env.prod credentials
    try:
        conn = pymysql.connect(
            host=os.environ.get('MYSQL_HOST', 'localhost'),
            port=int(os.environ.get('MYSQL_PORT', 3306)),
            user=os.environ.get('MYSQL_USER', 'root'),
            password=os.environ.get('MYSQL_PASSWORD', ''),
            database=os.environ.get('MYSQL_DB', 'railway')
        )
    except Exception as e:
        print(f"[{datetime.now()}] Failed to connect to database: {e}")
        return

    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Get errors from last 24 hours that aren't resolved
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        SELECT id, tier, context, error_type, error_message, traceback,
               request_method, request_path, request_user_agent, user_id,
               created_at, error_hash, resolved
        FROM sdll_app_errors
        WHERE created_at >= %s AND resolved = FALSE AND tier = 1
        ORDER BY created_at DESC
    ''', (cutoff,))

    errors = cursor.fetchall()
    conn.close()

    if not errors:
        print(f"[{datetime.now()}] No new Tier I errors.")
        return

    # Filter and DEDUPLICATE by error_hash
    # The same bug triggering 100 times = 1 unique error to diagnose
    exported_ids = get_exported_ids()
    exported_hashes = get_exported_hashes()

    # Group errors by hash, keeping only the first (oldest) occurrence of each
    errors_by_hash = {}
    skipped_duplicates = 0

    for error in errors:
        error_hash = error.get('error_hash')

        # Skip if already exported (by ID)
        if error['id'] in exported_ids:
            continue

        # Skip if this error_hash was already exported (duplicate of same bug)
        if error_hash and error_hash in exported_hashes:
            skipped_duplicates += 1
            continue

        # Check if should diagnose
        should, reason = should_diagnose_dict(error)
        if not should:
            print(f"  Skipping error {error['id']}: {reason}")
            continue

        # Deduplicate: only keep first occurrence of each hash
        if error_hash:
            if error_hash not in errors_by_hash:
                errors_by_hash[error_hash] = error
            else:
                skipped_duplicates += 1
        else:
            # No hash = treat as unique (shouldn't happen, but handle it)
            errors_by_hash[f"no_hash_{error['id']}"] = error

    # Get unique errors to export
    exportable = list(errors_by_hash.values())

    if skipped_duplicates > 0:
        print(f"  Skipped {skipped_duplicates} duplicate occurrences of same errors")

    if not exportable:
        print(f"[{datetime.now()}] {len(errors)} error occurrences found, but no NEW unique errors to diagnose.")
        return

    # Check circuit breaker (using UNIQUE error count, not raw count)
    can_proceed, reason = check_circuit_breaker(len(exportable))
    if not can_proceed:
        print(f"[{datetime.now()}] Cannot proceed: {reason}")
        return

    print(f"[{datetime.now()}] Found {len(exportable)} unique new error(s) to diagnose.")

    # Update state with unique error count
    state = load_state()
    state['unique_errors_this_hour'] += len(exportable)
    save_state(state)

    for error in exportable:
        file_path = export_error_dict(error)
        print(f"  Exported error {error['id']} (hash: {error.get('error_hash', 'none')[:8]}...) to {file_path}")
        exported_ids.add(error['id'])
        # Track the hash so future occurrences of same bug are skipped
        if error.get('error_hash'):
            exported_hashes.add(error['error_hash'])

    save_exported_ids(exported_ids)
    save_exported_hashes(exported_hashes)

    # Send notification
    if os.environ.get('NOTIFY_ON_NEW_ERRORS') == '1':
        message = f"🔍 {len(exportable)} new error(s) ready for diagnosis\n\n"
        for e in exportable[:5]:  # Show first 5
            message += f"• [{e['id']}] {e['error_type']}: {e['error_message'][:50]}...\n"
        message += f"\nRun: claude 'Diagnose pending errors'"
        send_notification(message)

    # Auto-invoke Claude Code to diagnose ONLY THE FIRST error
    # IMPORTANT: Only one diagnosis at a time to prevent:
    # - Multiple competing Claude sessions
    # - Git conflicts from concurrent commits
    # - Resource contention
    # Remaining errors will be picked up in subsequent polling cycles
    if os.environ.get('AUTO_DIAGNOSE', '1') == '1':
        # Check if a diagnosis is already running
        if is_diagnosis_in_progress():
            try:
                lock_data = json.loads(LOCK_FILE.read_text())
                print(f"[Queued] Diagnosis already in progress for error #{lock_data.get('error_id')}.")
                print(f"         {len(exportable)} error(s) waiting in queue.")
            except Exception:
                print(f"[Queued] Diagnosis in progress. {len(exportable)} error(s) waiting.")
            return

        error = exportable[0]  # Process only the first/oldest error
        print(f"[Single-thread] Diagnosing error #{error['id']} (remaining {len(exportable)-1} will be queued)")

        # Acquire lock before starting
        if acquire_diagnosis_lock(error['id']):
            invoke_claude_diagnosis(error['id'])
        else:
            print(f"[Error] Could not acquire diagnosis lock")


def invoke_claude_diagnosis(error_id):
    """
    Invoke Claude Code to diagnose and fix an error.

    Opens a NEW CMD window so the user can interact with Claude Code.
    The scheduled task runs silently, but Claude needs user interaction.
    """
    import subprocess
    import platform

    print(f"\n{'='*60}")
    print(f"Invoking Claude Code to diagnose error #{error_id}")
    print(f"{'='*60}\n")

    # Update state to track diagnosis
    state = load_state()
    state['diagnoses_today'] = state.get('diagnoses_today', 0) + 1
    state['last_diagnosis'] = datetime.now().isoformat()
    save_state(state)

    prompt = f"""Diagnose and fix production error #{error_id}.

The error has been exported to errors/pending/error_{error_id}.md - read it first.

Follow the TDD workflow (CI_CD.md):
1. Read the error file and affected source code
1a. Check the recent git commits to make sure that the issue has not already been fixed (if it has and the code changes reflect that, you can mark it resolved and notify admins)
2. Create a regression test in tests/test_regressions.py that reproduces the bug
3. Run the test to verify it FAILS (confirming the bug)
4. Implement a minimal fix
5. Run the test to verify it PASSES
6. Run quick tests to check for regressions: python run_tests.py --quick
7. Ask me for approval before committing
8. After approval, commit both the fix AND the test, then push to production

Start by reading the error file."""

    try:
        if platform.system() == 'Windows':
            # On Windows: Open a NEW visible CMD window with Claude
            # The /K flag keeps the window open after Claude exits
            # Title the window so user knows what it is
            cmd = f'start "Claude Code - Error #{error_id}" cmd /K "cd /d {PROJECT_ROOT} && claude \\"{prompt}\\""'
            subprocess.run(cmd, shell=True)

            # Play a sound to alert the user (Windows system sound)
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass

            # Send Telegram notification
            _send_telegram_alert(error_id)

            print(f"Opened Claude Code window for error #{error_id}")
            print("Check your taskbar for the new CMD window!")
        else:
            # On Linux/Mac: Open a new terminal window
            # This varies by system, try common terminal emulators
            terminals = [
                ['gnome-terminal', '--', 'claude', prompt],
                ['xterm', '-e', 'claude', prompt],
                ['open', '-a', 'Terminal', 'claude', prompt],  # macOS
            ]
            for term_cmd in terminals:
                try:
                    subprocess.Popen(term_cmd, cwd=str(PROJECT_ROOT))
                    print(f"Opened terminal for error #{error_id}")
                    break
                except FileNotFoundError:
                    continue
            else:
                # Fallback: run in current terminal
                subprocess.run(['claude', prompt], cwd=str(PROJECT_ROOT))

        return True
    except FileNotFoundError:
        print("ERROR: 'claude' CLI not found. Make sure Claude Code is installed.")
        print("Install with: npm install -g @anthropic-ai/claude-code")
        return False
    except Exception as e:
        print(f"ERROR invoking Claude Code: {e}")
        return False


def show_status():
    """Show current state and limits."""
    print("\n=== Error Diagnosis System Status ===\n")

    # Paused?
    if is_paused():
        content = PAUSE_FILE.read_text()
        print("[X] SYSTEM PAUSED")
        print(f"   {content}")
        print()
    else:
        print("[OK] System Active")
        print()

    # Diagnosis in progress?
    if LOCK_FILE.exists():
        try:
            lock_data = json.loads(LOCK_FILE.read_text())
            started = lock_data.get('started', 'unknown')
            error_id = lock_data.get('error_id', 'unknown')
            print("[LOCK] Diagnosis in Progress:")
            print(f"   Error: #{error_id}")
            print(f"   Started: {started}")
            print(f"   (Run --unlock to force release if stuck)")
            print()
        except Exception:
            print("[LOCK] Lock file exists but unreadable")
            print()
    else:
        print("[UNLOCKED] No diagnosis in progress")
        print()

    # State
    state = load_state()
    print("Rate Limits:")
    print(f"  Unique errors this hour: {state.get('unique_errors_this_hour', 0)} / {MAX_ERRORS_PER_HOUR}")
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

    # Exported IDs and Hashes
    exported = get_exported_ids()
    exported_hashes = get_exported_hashes()
    print(f"Total Exported: {len(exported)} error instances")
    print(f"Unique Error Hashes: {len(exported_hashes)} (duplicates are auto-skipped)")
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
    parser.add_argument('--unlock', action='store_true', help='Release diagnosis lock (if stuck)')
    parser.add_argument('--list', action='store_true', help='List pending errors')
    parser.add_argument('--no-diagnose', action='store_true',
                        help='Export errors but do not auto-invoke Claude Code')
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.resume:
        resume_system()
    elif args.unlock:
        if LOCK_FILE.exists():
            release_diagnosis_lock()
            print("[Unlocked] Diagnosis lock released. Next poll will start a new diagnosis.")
        else:
            print("[Info] No lock to release.")
    elif args.list:
        list_pending()
    else:
        # Set environment variable to control auto-diagnosis
        if args.no_diagnose:
            os.environ['AUTO_DIAGNOSE'] = '0'
        poll_and_export()


if __name__ == '__main__':
    main()
