#!/usr/bin/env python
"""
Cron job script to check for recently added games that need umpires.

Sends an email alert to the admin if any games were added in the last N hours
for leagues that require umpires.

Usage:
    python scripts/check_new_games.py [--hours 2] [--dry-run]

Environment variables needed:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, GMAIL_SENDER
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models.game import Game
from app.models.league import League
from app.services.notification_service import GmailService


def get_recent_games_needing_umpires(hours=2):
    """
    Find games added in the last N hours that are in leagues requiring umpires.

    Args:
        hours: Number of hours to look back

    Returns:
        List of (Game, League) tuples
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Get all games added since cutoff
    recent_games = Game.query.filter(
        Game.date_added >= cutoff,
        Game.active == 1,
        Game.game_type != 'practice'  # Practices don't need umpires
    ).all()

    results = []

    for game in recent_games:
        # Get the league for this game
        league = League.get_by_name(game.league)
        if league and league.needs_umpires:
            results.append((game, league))

    return results


def format_game_list(games_with_leagues):
    """Format list of games for email."""
    if not games_with_leagues:
        return "No games found."

    lines = []
    for game, league in games_with_leagues:
        game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
        lines.append(f"  - {league.display_name}: {game_date}")
        if game.home_team:
            lines.append(f"    {game.home_team.school_name if hasattr(game.home_team, 'school_name') else 'Home'} vs {game.away_team.school_name if game.away_team and hasattr(game.away_team, 'school_name') else 'Away'}")

    return '\n'.join(lines)


def send_alert_email(games_with_leagues, hours, recipient='sdll.umpires@gmail.com'):
    """Send email alert about new games needing umpires."""
    gmail = GmailService()

    if not gmail.is_configured:
        print("ERROR: Email service not configured")
        return False

    count = len(games_with_leagues)
    subject = f"SDLL Alert: {count} new game(s) added needing umpires"

    # Group by league for better readability
    by_league = {}
    for game, league in games_with_leagues:
        league_name = league.display_name
        if league_name not in by_league:
            by_league[league_name] = []
        by_league[league_name].append(game)

    # Build plain text body
    body_lines = [
        f"{count} game(s) have been added in the last {hours} hour(s) for leagues that require umpires:",
        ""
    ]

    for league_name, games in sorted(by_league.items()):
        body_lines.append(f"{league_name} ({len(games)} game(s)):")
        for game in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            body_lines.append(f"  - {game_date}")
        body_lines.append("")

    body_lines.extend([
        "Please review and ensure umpire assignments are in place.",
        "",
        "- SDLL Automated Alert"
    ])

    body_text = '\n'.join(body_lines)

    # Build HTML body
    html_parts = [
        '<!DOCTYPE html>',
        '<html><head></head>',
        '<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">',
        f'<h2 style="color: #228B22;">{count} New Game(s) Need Umpires</h2>',
        f'<p>The following games were added in the last {hours} hour(s) for leagues that require umpires:</p>',
    ]

    for league_name, games in sorted(by_league.items()):
        html_parts.append(f'<h3 style="color: #FF8C00; margin-bottom: 5px;">{league_name}</h3>')
        html_parts.append('<ul style="margin-top: 5px;">')
        for game in games:
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            html_parts.append(f'<li>{game_date}</li>')
        html_parts.append('</ul>')

    html_parts.extend([
        '<p style="margin-top: 20px;">Please review and ensure umpire assignments are in place.</p>',
        '<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">',
        '<p style="color: #888; font-size: 12px;">SDLL Automated Alert</p>',
        '</body></html>'
    ])

    body_html = '\n'.join(html_parts)

    try:
        gmail.send_email(recipient, subject, body_text, body_html)
        print(f"Alert email sent to {recipient}")
        return True
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Check for new games needing umpires')
    parser.add_argument('--hours', type=int, default=2,
                        help='Hours to look back (default: 2)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Check but do not send email')
    parser.add_argument('--recipient', type=str, default='sdll.umpires@gmail.com',
                        help='Email recipient (default: sdll.umpires@gmail.com)')

    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        print(f"Checking for games added in the last {args.hours} hour(s)...")

        games_with_leagues = get_recent_games_needing_umpires(args.hours)

        if not games_with_leagues:
            print("No new games found that need umpires.")
            return 0

        print(f"Found {len(games_with_leagues)} game(s) needing umpires:")
        for game, league in games_with_leagues:
            game_date = game.game_date.strftime('%Y-%m-%d %H:%M') if game.game_date else 'TBD'
            print(f"  - {league.display_name}: {game_date}")

        if args.dry_run:
            print("\n[DRY RUN] Would send alert email")
            return 0

        success = send_alert_email(games_with_leagues, args.hours, args.recipient)
        return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
