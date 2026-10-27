#!/usr/bin/env python3
"""Backfill batters_faced from GC screenshot sessions.

This script re-parses existing GameChanger screenshots to extract batters_faced
data that was not originally captured, and updates the corresponding PitchingStats records.

Usage:
    cd SDLLApp
    python scripts/backfill_batters_faced.py [--dry-run] [--limit N]

Options:
    --dry-run   Show what would be updated without making changes
    --limit N   Process only N sessions (for testing)
"""

import sys
import os
import argparse

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.gc_screenshot_session import GCScreenshotSession
from app.models.pitching_stats import PitchingStats
from app.models.post_game_report import PostGameReport
from app.models.player import Player, PlayerSeason
from app.models.team import TeamSeason
from app.services.gc_screenshot_service import GCScreenshotService


def get_player_by_code(team_id: int, player_code: str):
    """Get player by player_code for a team."""
    ps = PlayerSeason.query.filter_by(team_id=team_id).join(
        Player, PlayerSeason.player_id == Player.id
    ).filter(Player.player_code == player_code).first()

    return ps.player if ps else None


def backfill_session(session: GCScreenshotSession, dry_run: bool = False) -> dict:
    """Re-parse a session and update batters_faced in pitching stats.

    Returns dict with:
        - success: bool
        - error: str (if failed)
        - updated: int (count of stats updated)
        - details: list of update details
    """
    result = {
        'session_id': session.id,
        'game_id': session.game_id,
        'team_id': session.team_id,
        'success': False,
        'error': None,
        'updated': 0,
        'details': []
    }

    # Check if we have image data
    if not session.image_data:
        result['error'] = 'No image data'
        return result

    # Get team and game context
    team = TeamSeason.query.get(session.team_id)
    if not team:
        result['error'] = 'Team not found'
        return result

    # Get the post-game report for this game/team
    report = PostGameReport.query.filter_by(
        game_id=session.game_id,
        team_id=session.team_id
    ).first()

    if not report:
        result['error'] = 'No post-game report found'
        return result

    # Get existing pitching stats
    existing_stats = {s.player_id: s for s in PitchingStats.get_for_report(report.id)}
    if not existing_stats:
        result['error'] = 'No pitching stats for this report'
        return result

    # Check if parsed_json already has batters_faced
    # If so, we can use that instead of re-parsing
    parsed_json = session.get_parsed_data()
    pitchers_data = parsed_json.get('pitchers', []) if parsed_json else []

    # Check if any pitcher has batters_faced data
    has_bf_data = any(p.get('batters_faced') is not None for p in pitchers_data)

    if has_bf_data:
        # Use existing parsed data
        for p in pitchers_data:
            player_code = p.get('player_code')
            bf = p.get('batters_faced')

            if not player_code or bf is None:
                continue

            # Find the player
            player = get_player_by_code(session.team_id, player_code)
            if not player:
                result['details'].append(f"Player {player_code} not found")
                continue

            # Find their pitching stats
            stats = existing_stats.get(player.id)
            if not stats:
                result['details'].append(f"No stats for {player_code}")
                continue

            # Check if batters_faced needs updating
            if stats.batters_faced is None or stats.batters_faced != bf:
                old_val = stats.batters_faced
                if not dry_run:
                    stats.batters_faced = bf
                result['details'].append(f"{player_code}: {old_val} -> {bf}")
                result['updated'] += 1

        if not dry_run and result['updated'] > 0:
            db.session.commit()

        result['success'] = True
        return result

    # Need to re-parse the screenshot
    # Get context for parsing
    from app.models.game import Game
    from sqlalchemy.orm import joinedload

    game = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).get(session.game_id)

    if not game:
        result['error'] = 'Game not found'
        return result

    team_name = team.computed_display_name
    opponent_id = game.away_ID if session.team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)
    opponent_name = opponent.computed_display_name if opponent else 'Unknown'

    # Get roster
    roster = GCScreenshotService.get_roster_for_prompt(session.team_id)

    # Re-parse
    print(f"  Re-parsing session {session.id}...")
    parsed_data, parse_error = GCScreenshotService.parse_screenshot(
        session, team_name, opponent_name, roster
    )

    if parse_error:
        result['error'] = f'Parse error: {parse_error}'
        return result

    # Update pitching stats with batters_faced
    for p in parsed_data.pitchers:
        if not p.player_code or p.batters_faced is None:
            continue

        # Find the player
        player = get_player_by_code(session.team_id, p.player_code)
        if not player:
            result['details'].append(f"Player {p.player_code} not found")
            continue

        # Find their pitching stats
        stats = existing_stats.get(player.id)
        if not stats:
            result['details'].append(f"No stats for {p.player_code}")
            continue

        # Update batters_faced
        if stats.batters_faced is None or stats.batters_faced != p.batters_faced:
            old_val = stats.batters_faced
            if not dry_run:
                stats.batters_faced = p.batters_faced
            result['details'].append(f"{p.player_code}: {old_val} -> {p.batters_faced}")
            result['updated'] += 1

    if not dry_run and result['updated'] > 0:
        db.session.commit()

    result['success'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description='Backfill batters_faced from GC screenshots')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated')
    parser.add_argument('--limit', type=int, help='Process only N sessions')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        # Check API configuration
        if not GCScreenshotService.is_configured():
            print("WARNING: ANTHROPIC_API_KEY not set. Will only use existing parsed data.")

        # Get submitted sessions with image data
        query = GCScreenshotSession.query.filter(
            GCScreenshotSession.status == GCScreenshotSession.STATUS_SUBMITTED,
            GCScreenshotSession.image_data.isnot(None)
        ).order_by(GCScreenshotSession.created_at.desc())

        if args.limit:
            query = query.limit(args.limit)

        sessions = query.all()

        print(f"Found {len(sessions)} submitted sessions with image data")
        if args.dry_run:
            print("DRY RUN - no changes will be made")
        print()

        # Track stats
        total = len(sessions)
        success_count = 0
        updated_count = 0
        error_count = 0

        for i, session in enumerate(sessions, 1):
            print(f"[{i}/{total}] Session {session.id} (game={session.game_id}, team={session.team_id})")

            result = backfill_session(session, dry_run=args.dry_run)

            if result['success']:
                success_count += 1
                updated_count += result['updated']
                if result['updated'] > 0:
                    print(f"  Updated {result['updated']} records")
                    for detail in result['details']:
                        print(f"    {detail}")
                else:
                    print("  No updates needed")
            else:
                error_count += 1
                print(f"  ERROR: {result['error']}")

        print()
        print("=" * 50)
        print(f"Summary:")
        print(f"  Processed: {total}")
        print(f"  Success: {success_count}")
        print(f"  Errors: {error_count}")
        print(f"  Stats updated: {updated_count}")
        if args.dry_run:
            print("  (DRY RUN - no actual changes made)")


if __name__ == '__main__':
    main()
