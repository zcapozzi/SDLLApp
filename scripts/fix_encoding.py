#!/usr/bin/env python
"""Fix double-encoded UTF-8 text in post-game reports."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.post_game_report import PostGameReport

# Common mojibake patterns (UTF-8 decoded as Windows-1252)
MOJIBAKE_FIXES = {
    'â€¦': '…',   # ellipsis
    'â€™': "'",   # right single quote
    'â€˜': "'",   # left single quote
    'â€œ': '"',   # left double quote
    'â€': '"',    # right double quote
    'â€"': '—',   # em dash
    'â€"': '–',   # en dash
    'Ã¡': 'á',
    'Ã©': 'é',
    'Ã­': 'í',
    'Ã³': 'ó',
    'Ãº': 'ú',
    'Ã±': 'ñ',
}

def fix_text(text):
    """Fix mojibake in text."""
    if not text:
        return text

    fixed = text
    for bad, good in MOJIBAKE_FIXES.items():
        fixed = fixed.replace(bad, good)

    return fixed

def main():
    app = create_app()
    with app.app_context():
        reports = PostGameReport.query.filter(
            PostGameReport.umpire_comments.isnot(None)
        ).all()

        fixed_count = 0
        for r in reports:
            if r.umpire_comments:
                fixed = fix_text(r.umpire_comments)
                if fixed != r.umpire_comments:
                    print(f"Report {r.id}:")
                    print(f"  Before: {r.umpire_comments}")
                    print(f"  After:  {fixed}")
                    r.umpire_comments = fixed
                    fixed_count += 1

        if fixed_count > 0:
            db.session.commit()
            print(f"\nFixed {fixed_count} reports")
        else:
            print("No corrupted text found")

if __name__ == '__main__':
    main()
