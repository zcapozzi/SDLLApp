"""Assignr Sync Service - compares local SDL games to Assignr records.

Identifies discrepancies between the local database and Assignr:
- Games that exist locally but not in Assignr (need to be added)
- Games where time/date differs
- Games where location/field differs

Only checks games where umpire_override='SDL' (SDLL Academy games).
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from app.extensions import db
from app.models.game import Game
from app.models.field import Field
from app.models.organization import Organization
from app.services.assignr_service import get_assignr_service
from app.utils.logging import SDLLLogger

logger = SDLLLogger('assignr_sync')


@dataclass
class SyncDiscrepancy:
    """Represents a discrepancy between local and Assignr data."""
    game_id: int
    assignr_id: str
    discrepancy_type: str  # 'missing_in_assignr', 'time_mismatch', 'location_mismatch'
    game_desc: str
    local_value: str
    assignr_value: str
    game_date: datetime
    league: str


def normalize_location(location: str) -> str:
    """Normalize location string for comparison."""
    if not location:
        return ''
    # Remove extra whitespace, lowercase for comparison
    return ' '.join(location.lower().split())


def get_sdl_games(days_ahead: int = 60) -> List[Game]:
    """Get all SDL Academy games from local database.

    Args:
        days_ahead: How many days ahead to look for games

    Returns:
        List of Game objects where umpire_override='SDL'
    """
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    games = Game.query.filter(
        Game.active == 1,
        Game.umpire_override == 'SDL',
        Game.game_date >= now,
        Game.game_date <= cutoff,
        Game.status == 'scheduled',
        Game.game_type != 'practice'
    ).all()

    logger.info(f"Found {len(games)} SDL games in next {days_ahead} days")
    return games


def compare_games(
    local_games: List[Game],
    assignr_games: List[Dict]
) -> List[SyncDiscrepancy]:
    """Compare local SDL games against Assignr games.

    Args:
        local_games: List of local Game objects
        assignr_games: List of Assignr game dicts from API

    Returns:
        List of SyncDiscrepancy objects
    """
    discrepancies = []

    # Build lookup of Assignr games by external_id (our game ID)
    assignr_by_external_id = {}
    assignr_by_id = {}
    for ag in assignr_games:
        ext_id = ag.get('external_id')
        if ext_id:
            assignr_by_external_id[str(ext_id)] = ag
        assignr_by_id[str(ag.get('id', ''))] = ag

    for game in local_games:
        game_desc = f"{game.league} - {game.game_date.strftime('%b %d %I:%M %p')} at {game.field_name or 'TBD'}"

        # Try to find matching Assignr game
        assignr_game = None

        # First, try by assignr_id (if we have it stored)
        if game.assignr_id:
            assignr_game = assignr_by_id.get(str(game.assignr_id))

        # Second, try by external_id (our game ID)
        if not assignr_game:
            assignr_game = assignr_by_external_id.get(str(game.ID))

        if not assignr_game:
            # Game is missing from Assignr
            discrepancies.append(SyncDiscrepancy(
                game_id=game.ID,
                assignr_id='',
                discrepancy_type='missing_in_assignr',
                game_desc=game_desc,
                local_value='exists',
                assignr_value='not found',
                game_date=game.game_date,
                league=game.league or ''
            ))
            continue

        # Game exists - check for mismatches
        assignr_id = str(assignr_game.get('id', ''))

        # Parse Assignr game date
        assignr_start = assignr_game.get('start_time', '')
        assignr_datetime = None
        if assignr_start:
            try:
                assignr_datetime = datetime.strptime(assignr_start[:19], "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                pass

        # Check time/date mismatch
        if assignr_datetime and game.game_date:
            # Compare date and time (allow 1 minute tolerance)
            time_diff = abs((game.game_date - assignr_datetime).total_seconds())
            if time_diff > 60:  # More than 1 minute difference
                discrepancies.append(SyncDiscrepancy(
                    game_id=game.ID,
                    assignr_id=assignr_id,
                    discrepancy_type='time_mismatch',
                    game_desc=game_desc,
                    local_value=game.game_date.strftime('%Y-%m-%d %I:%M %p'),
                    assignr_value=assignr_datetime.strftime('%Y-%m-%d %I:%M %p'),
                    game_date=game.game_date,
                    league=game.league or ''
                ))

        # Check location mismatch
        local_location = normalize_location(game.field_name or '')
        assignr_venue = assignr_game.get('_embedded', {}).get('venue', {})
        assignr_location = normalize_location(assignr_venue.get('name', '') if assignr_venue else '')

        if local_location and assignr_location and local_location != assignr_location:
            discrepancies.append(SyncDiscrepancy(
                game_id=game.ID,
                assignr_id=assignr_id,
                discrepancy_type='location_mismatch',
                game_desc=game_desc,
                local_value=game.field_name or '',
                assignr_value=assignr_venue.get('name', '') if assignr_venue else '',
                game_date=game.game_date,
                league=game.league or ''
            ))

    return discrepancies


def run_sync_check(days_ahead: int = 60) -> Tuple[List[SyncDiscrepancy], str]:
    """Run the full sync check.

    Args:
        days_ahead: How many days ahead to check

    Returns:
        Tuple of (discrepancies list, error message if any)
    """
    try:
        # Get local SDL games
        local_games = get_sdl_games(days_ahead)

        if not local_games:
            logger.info("No SDL games found to check")
            return [], None

        # Get Assignr games for the same date range
        assignr_service = get_assignr_service()

        if not assignr_service.is_configured():
            return [], "Assignr credentials not configured"

        start_date = datetime.now()
        end_date = start_date + timedelta(days=days_ahead)

        assignr_games = assignr_service.get_all_games(start_date, end_date)
        logger.info(f"Fetched {len(assignr_games)} games from Assignr")

        # Compare
        discrepancies = compare_games(local_games, assignr_games)

        logger.info(f"Found {len(discrepancies)} discrepancies")
        return discrepancies, None

    except Exception as e:
        logger.error(f"Sync check failed: {e}")
        return [], str(e)


def format_discrepancies_html(discrepancies: List[SyncDiscrepancy]) -> str:
    """Format discrepancies as HTML for email.

    Args:
        discrepancies: List of SyncDiscrepancy objects

    Returns:
        HTML string
    """
    if not discrepancies:
        return "<p>No discrepancies found.</p>"

    # Group by type
    missing = [d for d in discrepancies if d.discrepancy_type == 'missing_in_assignr']
    time_mismatches = [d for d in discrepancies if d.discrepancy_type == 'time_mismatch']
    location_mismatches = [d for d in discrepancies if d.discrepancy_type == 'location_mismatch']

    html = []
    html.append(f"<p><strong>Found {len(discrepancies)} discrepancy(ies)</strong> between SDLL database and Assignr.</p>")

    if missing:
        html.append("<h3 style='color: #c33;'>Games Missing from Assignr</h3>")
        html.append("<p>These SDL games need to be added to Assignr:</p>")
        html.append("<ul>")
        for d in sorted(missing, key=lambda x: x.game_date):
            html.append(f"<li><strong>Game #{d.game_id}</strong>: {d.game_desc}</li>")
        html.append("</ul>")

    if time_mismatches:
        html.append("<h3 style='color: #cc7000;'>Time/Date Mismatches</h3>")
        html.append("<p>These games have different times in Assignr:</p>")
        html.append("<table style='border-collapse: collapse; width: 100%;'>")
        html.append("<tr style='background: #f5f5f5;'><th style='padding: 8px; border: 1px solid #ddd;'>Game</th><th style='padding: 8px; border: 1px solid #ddd;'>Local Time</th><th style='padding: 8px; border: 1px solid #ddd;'>Assignr Time</th></tr>")
        for d in sorted(time_mismatches, key=lambda x: x.game_date):
            html.append(f"<tr><td style='padding: 8px; border: 1px solid #ddd;'>#{d.game_id} - {d.league}</td><td style='padding: 8px; border: 1px solid #ddd;'>{d.local_value}</td><td style='padding: 8px; border: 1px solid #ddd;'>{d.assignr_value}</td></tr>")
        html.append("</table>")

    if location_mismatches:
        html.append("<h3 style='color: #cc7000;'>Location Mismatches</h3>")
        html.append("<p>These games have different locations in Assignr:</p>")
        html.append("<table style='border-collapse: collapse; width: 100%;'>")
        html.append("<tr style='background: #f5f5f5;'><th style='padding: 8px; border: 1px solid #ddd;'>Game</th><th style='padding: 8px; border: 1px solid #ddd;'>Local Field</th><th style='padding: 8px; border: 1px solid #ddd;'>Assignr Venue</th></tr>")
        for d in sorted(location_mismatches, key=lambda x: x.game_date):
            html.append(f"<tr><td style='padding: 8px; border: 1px solid #ddd;'>#{d.game_id} - {d.league}</td><td style='padding: 8px; border: 1px solid #ddd;'>{d.local_value}</td><td style='padding: 8px; border: 1px solid #ddd;'>{d.assignr_value}</td></tr>")
        html.append("</table>")

    return '\n'.join(html)


def format_discrepancies_text(discrepancies: List[SyncDiscrepancy]) -> str:
    """Format discrepancies as plain text for email.

    Args:
        discrepancies: List of SyncDiscrepancy objects

    Returns:
        Plain text string
    """
    if not discrepancies:
        return "No discrepancies found."

    lines = [f"Found {len(discrepancies)} discrepancy(ies) between SDLL database and Assignr.", ""]

    missing = [d for d in discrepancies if d.discrepancy_type == 'missing_in_assignr']
    time_mismatches = [d for d in discrepancies if d.discrepancy_type == 'time_mismatch']
    location_mismatches = [d for d in discrepancies if d.discrepancy_type == 'location_mismatch']

    if missing:
        lines.append("=== GAMES MISSING FROM ASSIGNR ===")
        lines.append("These SDL games need to be added to Assignr:")
        for d in sorted(missing, key=lambda x: x.game_date):
            lines.append(f"  - Game #{d.game_id}: {d.game_desc}")
        lines.append("")

    if time_mismatches:
        lines.append("=== TIME/DATE MISMATCHES ===")
        lines.append("These games have different times in Assignr:")
        for d in sorted(time_mismatches, key=lambda x: x.game_date):
            lines.append(f"  - Game #{d.game_id} ({d.league})")
            lines.append(f"    Local: {d.local_value}")
            lines.append(f"    Assignr: {d.assignr_value}")
        lines.append("")

    if location_mismatches:
        lines.append("=== LOCATION MISMATCHES ===")
        lines.append("These games have different locations in Assignr:")
        for d in sorted(location_mismatches, key=lambda x: x.game_date):
            lines.append(f"  - Game #{d.game_id} ({d.league})")
            lines.append(f"    Local: {d.local_value}")
            lines.append(f"    Assignr: {d.assignr_value}")
        lines.append("")

    return '\n'.join(lines)
