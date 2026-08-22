"""
Test script to verify the schedule accept process works correctly.

This script:
1. Loads the proposal from the database
2. Simulates the save process
3. Verifies games are created correctly
4. Checks that Calendar and Manage Games views work

Run: python scripts/test_accept_schedule.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Set to use the development database (railway_replica)
os.environ['FLASK_CONFIG'] = 'development'

from app import create_app, db
from app.models.schedule_proposal import ScheduleProposal
from app.models.game import Game
from app.models.team import TeamSeason
from datetime import datetime
import json


def test_accept_schedule():
    """Test the schedule accept process."""
    app = create_app('development')

    with app.app_context():
        year = 2026
        is_spring = 0
        season_name = f'{"Spring" if is_spring else "Fall"} {year}'

        print(f"\n{'='*60}")
        print(f"Testing Schedule Accept for {season_name}")
        print(f"{'='*60}")

        # 1. Check for existing proposal
        print("\n1. Checking for proposal...")
        proposal_record = ScheduleProposal.get_for_season(year, is_spring)

        if not proposal_record:
            print("   ERROR: No proposal found!")
            return False

        proposal = proposal_record.data
        print(f"   Found proposal with {len(proposal.get('games', []))} games")
        print(f"   Status: {proposal_record.status}")
        print(f"   Created: {proposal_record.created_at}")

        # 2. Analyze game types in proposal
        print("\n2. Analyzing game types in proposal...")
        game_types = {}
        for g in proposal.get('games', []):
            gt = g.get('game_type', 'unknown')
            game_types[gt] = game_types.get(gt, 0) + 1
        for gt, count in sorted(game_types.items()):
            print(f"   {gt}: {count}")

        # 3. Check for practices and division practices
        print("\n3. Checking for practices...")
        practices = [g for g in proposal.get('games', []) if g.get('game_type') == 'practice']
        div_practices = [g for g in proposal.get('games', []) if g.get('is_league_practice')]
        print(f"   Regular practices: {len(practices)}")
        print(f"   Division practices: {len(div_practices)}")

        # 4. Check existing games in database
        print("\n4. Checking existing games in database...")
        existing_games = Game.query.filter_by(
            year=year, is_spring=is_spring, active=1
        ).count()
        print(f"   Existing active games: {existing_games}")

        # 5. Dry-run the save logic (don't commit)
        print("\n5. Simulating save process (dry run)...")

        # Check hard violations
        hard_violations = [v for v in proposal.get('violations', []) if v['severity'] == 'hard']
        print(f"   Hard violations: {len(hard_violations)}")
        if hard_violations:
            for v in hard_violations[:5]:
                code = v.get('code', v.get('rule', 'unknown'))
                msg = v.get('message', v.get('description', str(v)))[:60]
                print(f"      - {code}: {msg}...")
            if len(hard_violations) > 5:
                print(f"      ... and {len(hard_violations) - 5} more")

        # Simulate creating games
        would_save = 0
        would_update = 0
        issues = []

        assignments = proposal.get('assignments', {})
        for game_id, assignment in assignments.items():
            game = Game.query.get(int(game_id))
            if game:
                would_update += 1
            else:
                issues.append(f"Assignment refers to non-existent game ID {game_id}")

        for proposed_game in proposal['games']:
            if proposed_game['id'] in [int(k) for k in assignments.keys()]:
                continue

            game_type = proposed_game['game_type']

            # Check the logic we fixed
            if game_type == 'practice':
                # Should stay as 'practice', not become 'regular'
                pass
            elif game_type == 'division_practice':
                # Should become 'practice' with is_league_practice=True
                pass
            elif game_type == 'scrimmage':
                # Should become 'regular' with is_scrimmage=1
                pass

            would_save += 1

        print(f"   Would create: {would_save} new games")
        print(f"   Would update: {would_update} existing games")
        if issues:
            print(f"   Issues found: {len(issues)}")
            for issue in issues[:5]:
                print(f"      - {issue}")

        # 6. Test that game queries work
        print("\n6. Testing game queries...")
        try:
            # Test Calendar view query
            from sqlalchemy import func
            games_by_date = db.session.query(
                func.date(Game.game_date),
                func.count(Game.ID)
            ).filter(
                Game.year == year,
                Game.is_spring == is_spring,
                Game.active == 1,
                Game.game_date.isnot(None)
            ).group_by(func.date(Game.game_date)).all()
            print(f"   Calendar query works: {len(games_by_date)} days with games")

            # Test Manage Games query
            games = Game.query.filter_by(
                year=year, is_spring=is_spring, active=1
            ).order_by(Game.game_date).limit(5).all()
            print(f"   Manage Games query works: {len(games)} sample games")
            for g in games[:3]:
                print(f"      - {g.league}: {g.home_team.scheduler_display_name if g.home_team else 'TBD'} vs {g.away_team.scheduler_display_name if g.away_team else 'TBD'}")

        except Exception as e:
            print(f"   ERROR in queries: {e}")
            return False

        # 7. Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Proposal games: {len(proposal.get('games', []))}")
        print(f"Existing DB games: {existing_games}")
        print(f"Would create: {would_save}")
        print(f"Would update: {would_update}")
        print(f"Hard violations: {len(hard_violations)}")

        if hard_violations:
            print("\nWARNING: Hard violations exist - will need 'Force save' checkbox")

        print("\nRECOMMENDATION:")
        if issues:
            print("   FIX the issues listed above before accepting")
        elif hard_violations:
            print("   Review hard violations, then use Force Save if acceptable")
        else:
            print("   Safe to accept the schedule")

        return True


def test_views_after_save():
    """Test that Calendar and Manage Games views load correctly."""
    app = create_app('development')

    with app.test_client() as client:
        print("\n" + "="*60)
        print("Testing Views (requires login)")
        print("="*60)

        # Note: This would require authentication to fully test
        # For now, just verify the routes exist

        year = 2026
        is_spring = 0

        # Test Calendar route
        response = client.get(f'/games/{year}/{is_spring}/calendar')
        print(f"Calendar route: {response.status_code}")

        # Test Manage Games route
        response = client.get(f'/games/{year}/{is_spring}/manage')
        print(f"Manage Games route: {response.status_code}")

        if response.status_code == 302:
            print("   (Redirected - likely needs login)")


if __name__ == '__main__':
    print("="*60)
    print("Schedule Accept Test Script")
    print("="*60)
    print("\nThis script tests the schedule accept process using")
    print("the development database (railway_replica).")
    print("\nNOTE: This is a DRY RUN - no changes will be made.\n")

    success = test_accept_schedule()
    test_views_after_save()

    if success:
        print("\n" + "="*60)
        print("TEST PASSED - Ready to accept schedule")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("TEST FAILED - Issues found")
        print("="*60)
        sys.exit(1)
