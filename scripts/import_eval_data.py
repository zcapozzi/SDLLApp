"""Import evaluation data from CSV.

Stores raw scores as-is. Score ranges are league-age specific:
- Younger players (6-7): typically score in lower range (1-4)
- Older players (10-12): typically score in higher range (4-7)

The valid range for each age group is understood contextually;
a "4" for an 8-year-old means something different than for a 12-year-old.
"""

import csv
import sys
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, 'C:\\Users\\zcapo\\Documents\\workspace\\claude\\SDLLApp')

from app import create_app
from app.extensions import db
from app.models.player import Player, PlayerSeason, PlayerEvaluation, EvaluationMetric, PlayerEvaluationScore
from app.models.org_season import OrgSeason


# CSV column to metric name mapping
COLUMN_TO_METRIC = {
    'contact now': 'contact',
    'power now': 'power',
    'glove Now': 'glove',
    'arm Now': 'arm',
    'outfield Now': 'outfield',
    'control Now': 'control',
    'velocity Now': 'velocity',
    'avSpeedNow': 'speed',
}


def parse_score(value):
    """Parse a score value from CSV."""
    if not value or value.strip() == '':
        return None
    try:
        score = float(value.strip())
        if 1 <= score <= 7:
            return score
        return None
    except ValueError:
        return None


def main():
    csv_path = 'C:\\Users\\zcapo\\Documents\\workspace\\claude\\SDLLApp\\docs\\2026 Fall Eval Data for Division Placement - evalDataClean2026Fall.csv'

    app = create_app()
    with app.app_context():
        # Get Fall 2026 season
        org_season = OrgSeason.query.filter_by(year=2026, is_spring=0).first()
        if not org_season:
            print("ERROR: Fall 2026 season not found")
            return

        print(f"Importing evaluations for: {org_season.season_desc}")

        # Load metric IDs
        metrics = {m.name: m for m in EvaluationMetric.query.filter_by(active=1).all()}
        print(f"Found {len(metrics)} active metrics")

        # Read all data
        print("\nReading CSV...")
        rows = []

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                league_age = row.get('leagueAge', '').strip()
                try:
                    age = int(league_age) if league_age else None
                except ValueError:
                    age = None

                row_scores = {}
                for col, metric_name in COLUMN_TO_METRIC.items():
                    score = parse_score(row.get(col, ''))
                    if score is not None:
                        row_scores[metric_name] = score

                rows.append({
                    'age': age,
                    'player_id': row.get('playerID', '').strip(),
                    'first_name': row.get('playerFirst', '').strip(),
                    'last_name': row.get('playerLast', '').strip(),
                    'email': row.get('acctEmail', '').strip(),
                    'division': row.get('Division', '').strip(),
                    'scores': row_scores
                })

        print(f"Read {len(rows)} rows")

        # Import raw scores
        print("\nImporting evaluations (raw scores, no normalization)...")
        stats = {
            'found': 0,
            'not_found': 0,
            'created': 0,
            'skipped_no_scores': 0,
        }

        for row in rows:
            # Find player
            player = None
            if row['player_id']:
                player = Player.find_by_code(row['player_id'])

            if not player and row['email'] and row['first_name']:
                player = Player.find_by_email_and_name(
                    row['email'], row['first_name'], row['last_name']
                )

            if not player:
                stats['not_found'] += 1
                if row['first_name']:
                    print(f"  Not found: {row['first_name']} {row['last_name']} ({row['player_id'] or row['email']})")
                continue

            stats['found'] += 1

            # Skip if no scores
            if not row['scores']:
                stats['skipped_no_scores'] += 1
                continue

            # Check if evaluation already exists
            existing = PlayerEvaluation.query.filter_by(
                player_id=player.id,
                org_season_id=org_season.ID
            ).first()

            if existing:
                # Update existing - delete old scores and add new
                PlayerEvaluationScore.query.filter_by(evaluation_id=existing.id).delete()
                evaluation = existing
            else:
                # Create new evaluation
                evaluation = PlayerEvaluation(
                    player_id=player.id,
                    org_season_id=org_season.ID,
                    eval_session=row['division']
                )
                db.session.add(evaluation)
                db.session.flush()  # Get ID

            # Add raw scores (no normalization - ranges are age-specific)
            total_score = 0
            score_count = 0

            for metric_name, raw_score in row['scores'].items():
                metric = metrics.get(metric_name)
                if not metric:
                    continue

                score = PlayerEvaluationScore(
                    evaluation_id=evaluation.id,
                    metric_id=metric.id,
                    score=Decimal(str(round(raw_score, 1)))
                )
                db.session.add(score)

                total_score += raw_score
                score_count += 1

            # Update overall score
            if score_count > 0:
                evaluation.overall_score = Decimal(str(round(total_score / score_count, 2)))

            stats['created'] += 1

        db.session.commit()

        print(f"\n\nImport complete!")
        print(f"  Players found: {stats['found']}")
        print(f"  Players not found: {stats['not_found']}")
        print(f"  Evaluations created/updated: {stats['created']}")
        print(f"  Skipped (no scores): {stats['skipped_no_scores']}")


if __name__ == '__main__':
    main()
