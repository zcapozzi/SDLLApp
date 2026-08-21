"""Service for exporting errors for local Claude Code analysis.

This service exports production errors to markdown files that Claude Code
can read and analyze locally. This approach is superior to using the Claude API
because Claude Code has full codebase context, can read source files, and
understands project patterns.

Workflow:
1. Production error captured by existing Tier I system
2. poll_errors.py polls DB and calls export_for_diagnosis()
3. Error info written to errors/pending/ as markdown + JSON
4. Admin runs Claude Code to diagnose and fix
5. Claude creates test, implements fix, commits if approved
"""

import os
import json
from datetime import datetime
from pathlib import Path


class ErrorDiagnosisService:
    """Exports errors for local Claude Code analysis."""

    # Directory where error files are written for Claude Code
    ERROR_QUEUE_DIR = Path(os.environ.get(
        'ERROR_QUEUE_DIR',
        Path(__file__).parent.parent.parent / 'errors' / 'pending'
    ))

    @staticmethod
    def export_for_diagnosis(app_error):
        """
        Export error to a file for local Claude Code analysis.

        Args:
            app_error: AppError instance

        Returns:
            Path to the exported error file
        """
        ErrorDiagnosisService.ERROR_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        # Create error file with all context
        error_file = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{app_error.id}.md"

        content = f"""# Production Error #{app_error.id}

## Error Details
- **Type**: {app_error.error_type}
- **Message**: {app_error.error_message}
- **Context**: {app_error.context}
- **Time**: {app_error.created_at.isoformat()}

## Request Info
- **Method**: {app_error.request_method or 'N/A'}
- **Path**: {app_error.request_path or 'N/A'}
- **User ID**: {app_error.user_id or 'Anonymous'}

## Traceback
```
{app_error.traceback or 'No traceback available'}
```

## Instructions for Claude Code

Please analyze this production error and follow TDD principles:

1. **Read the affected source files** mentioned in the traceback
2. **Create a reproducing test** in `tests/test_regressions.py`:
   - Test name: `test_regression_error_{app_error.id}_<brief_description>`
   - The test MUST fail with the same error type before the fix
3. **Run the test** to verify reproduction (should FAIL)
4. **Implement the fix** with minimal code changes
5. **Run the test** again (should PASS now)
6. **Run full test suite**: `python run_tests.py` (no regressions)
7. **Ask for approval** before committing
8. **Commit** the fix AND the new test together

To start diagnosis, run:
```
python scripts/diagnose_error.py {app_error.id}
```

Or directly with Claude Code:
```
claude "Diagnose and fix production error {app_error.id}"
```
"""
        error_file.write_text(content)

        # Also write JSON for programmatic access
        json_file = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{app_error.id}.json"
        json_file.write_text(json.dumps({
            'id': app_error.id,
            'error_type': app_error.error_type,
            'error_message': app_error.error_message,
            'context': app_error.context,
            'traceback': app_error.traceback,
            'request_method': app_error.request_method,
            'request_path': app_error.request_path,
            'user_id': app_error.user_id,
            'created_at': app_error.created_at.isoformat(),
            'error_hash': app_error.error_hash,
        }, indent=2))

        return error_file

    @staticmethod
    def get_pending_errors():
        """Get list of error files awaiting diagnosis."""
        if not ErrorDiagnosisService.ERROR_QUEUE_DIR.exists():
            return []
        return sorted(ErrorDiagnosisService.ERROR_QUEUE_DIR.glob("error_*.json"))

    @staticmethod
    def mark_diagnosed(error_id, outcome='diagnosed'):
        """
        Move error file to diagnosed folder.

        Args:
            error_id: The error ID
            outcome: 'diagnosed', 'fixed', 'skipped', etc.
        """
        diagnosed_dir = ErrorDiagnosisService.ERROR_QUEUE_DIR.parent / "diagnosed"
        diagnosed_dir.mkdir(exist_ok=True)

        for ext in ['.md', '.json']:
            src = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{error_id}{ext}"
            if src.exists():
                # Add timestamp and outcome to filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                dest = diagnosed_dir / f"error_{error_id}_{outcome}_{timestamp}{ext}"
                src.rename(dest)

    @staticmethod
    def is_error_pending(error_id):
        """Check if an error is pending diagnosis."""
        json_file = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{error_id}.json"
        return json_file.exists()

    @staticmethod
    def get_error_details(error_id):
        """
        Load error details from pending file.

        Args:
            error_id: The error ID

        Returns:
            Dict with error details or None
        """
        json_file = ErrorDiagnosisService.ERROR_QUEUE_DIR / f"error_{error_id}.json"
        if json_file.exists():
            return json.loads(json_file.read_text())
        return None
