"""Seed training types.

Run with: python scripts/seed_training_types.py

Creates the default training types required for umpires and coaches.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.training_type import TrainingType


TRAINING_TYPES = [
    {
        'code': 'abuse_awareness',
        'name': 'Abuse Awareness Training',
        'description': 'Little League required online training for child safety and abuse prevention.',
        'required_for': 'all',
        'expires_after_days': 365,  # Annual renewal required
    },
    {
        'code': 'background_check',
        'name': 'Background Check',
        'description': 'Criminal background check required for all adult volunteers.',
        'required_for': 'all',
        'expires_after_days': 730,  # Every 2 years
    },
    {
        'code': 'umpire_rules',
        'name': 'Rules Training',
        'description': 'In-person training on Little League rules and umpire mechanics.',
        'required_for': 'umpire',
        'expires_after_days': None,  # Never expires
    },
    {
        'code': 'umpire_field',
        'name': 'Field Training',
        'description': 'On-field umpire training covering positioning and mechanics.',
        'required_for': 'umpire',
        'expires_after_days': None,
    },
    {
        'code': 'first_aid',
        'name': 'First Aid/CPR',
        'description': 'Basic first aid and CPR certification (recommended but not required).',
        'required_for': 'all',
        'expires_after_days': 730,  # Every 2 years
    },
    {
        'code': 'coaching_certification',
        'name': 'Coaching Certification',
        'description': 'Little League coaching certification.',
        'required_for': 'coach',
        'expires_after_days': None,
    },
]


def seed_training_types():
    """Create or update all training types."""
    app = create_app()

    with app.app_context():
        created = 0
        updated = 0

        for data in TRAINING_TYPES:
            # Check if exists
            existing = TrainingType.get_by_code(data['code'])

            if existing:
                # Update existing
                for key, value in data.items():
                    setattr(existing, key, value)
                updated += 1
                print(f"Updated: {data['name']}")
            else:
                # Create new
                training_type = TrainingType(**data)
                db.session.add(training_type)
                created += 1
                print(f"Created: {data['name']}")

        db.session.commit()
        print(f"\nDone! Created {created}, updated {updated} training types.")


if __name__ == '__main__':
    seed_training_types()
