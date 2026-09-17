"""Red Flag Service - identifies scheduling and umpire assignment issues.

Red flags include:
1. Games without umpire_override set (no delegation decision made)
2. Practices with umpire_override set (shouldn't have umpires)
3. Overlapping/same-time games for the same SDL umpire
4. SDL-assigned games with no Assignr assignments (when game date is near)
5. Games on dates when the assigned SDL umpire has a blackout
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from app.extensions import db
from app.models.game import Game
from app.models.league import League


@dataclass
class RedFlag:
    """Represents a single red flag issue."""
    flag_type: str  # 'missing_assignment', 'practice_with_umpire', 'umpire_overlap', etc.
    severity: str  # 'error', 'warning', 'info'
    message: str
    game_id: Optional[int] = None
    game: Optional[Game] = None
    official_id: Optional[int] = None
    official_name: Optional[str] = None
    details: Dict = field(default_factory=dict)


@dataclass
class RedFlagReport:
    """Collection of red flags grouped by type."""
    missing_assignments: List[RedFlag] = field(default_factory=list)
    practices_with_umpires: List[RedFlag] = field(default_factory=list)
    umpire_overlaps: List[RedFlag] = field(default_factory=list)
    sdl_without_assignr: List[RedFlag] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return (len(self.missing_assignments) +
                len(self.practices_with_umpires) +
                len(self.umpire_overlaps) +
                len(self.sdl_without_assignr))

    @property
    def has_errors(self) -> bool:
        """Check if any red flags are errors (vs warnings)."""
        all_flags = (self.missing_assignments + self.practices_with_umpires +
                     self.umpire_overlaps + self.sdl_without_assignr)
        return any(f.severity == 'error' for f in all_flags)


class RedFlagService:
    """Service for detecting scheduling and umpire assignment red flags."""

    def __init__(self, year: int = None, is_spring: bool = None, days: int = 7):
        """Initialize the service.

        Args:
            year: Season year (defaults to current)
            is_spring: Spring season flag (defaults to current)
            days: Number of days ahead to check (default 7)
        """
        self.days = days
        self.now = datetime.utcnow()
        self.cutoff = self.now + timedelta(days=days)

        # Default to current season if not specified
        if year is None or is_spring is None:
            from app.models.org_season import OrgSeason
            current = OrgSeason.get_current_season()
            if current:
                self.year = year or current.year
                self.is_spring = is_spring if is_spring is not None else current.is_spring
            else:
                self.year = year or date.today().year
                self.is_spring = is_spring if is_spring is not None else (date.today().month < 7)
        else:
            self.year = year
            self.is_spring = is_spring

        # Cache for leagues
        self._leagues: Dict[str, League] = {}

    def _get_league(self, league_name: str) -> Optional[League]:
        """Get league by name with caching."""
        if league_name not in self._leagues:
            self._leagues[league_name] = League.get_by_name(league_name)
        return self._leagues[league_name]

    def run_all_checks(self) -> RedFlagReport:
        """Run all red flag checks and return a report."""
        report = RedFlagReport()

        # Run each check
        report.missing_assignments = self.check_missing_umpire_assignments()
        report.practices_with_umpires = self.check_practices_with_umpires()
        report.umpire_overlaps = self.check_umpire_overlaps()
        report.sdl_without_assignr = self.check_sdl_without_assignr_assignments()

        return report

    def check_missing_umpire_assignments(self) -> List[RedFlag]:
        """Find games needing umpires but without delegation decision (umpire_override not set)."""
        from sqlalchemy.orm import joinedload
        from app.models.game_umpire import GameUmpire
        from app.models.field_slot import FieldSlot

        flags = []

        # Get upcoming games (excluding practices)
        upcoming_games = Game.query.options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel)
        ).filter(
            Game.game_date >= self.now,
            Game.game_date <= self.cutoff,
            Game.active == 1,
            Game.status == 'scheduled',
            Game.game_type != 'practice'
        ).all()

        # Pre-load field slots for ownership check
        if upcoming_games:
            field_slots = FieldSlot.query.filter_by(
                year=self.year,
                is_spring=1 if self.is_spring else 0,
                active=1
            ).all()
            slot_ownership = {}
            for slot in field_slots:
                key = (slot.field_ID, slot.day_of_week, slot.start_time.hour, slot.start_time.minute)
                slot_ownership[key] = slot.is_owned
        else:
            slot_ownership = {}

        def is_slot_sdll_owned(game):
            if not game.game_date or not game.field_id:
                return True
            day_of_week = game.game_date.weekday()
            hour = game.game_date.hour
            minute = game.game_date.minute
            key = (game.field_id, day_of_week, hour, minute)
            return slot_ownership.get(key, 1) == 1

        for game in upcoming_games:
            # Skip scrimmages
            if game.is_scrimmage:
                continue

            # Skip if explicitly marked as no umpires needed
            if game.umpire_count_override == 0:
                continue

            # Get league to check if it needs umpires
            league = self._get_league(game.league)
            if not league or not league.needs_umpires:
                continue

            # Skip if umpire_override is already set (delegation decision made)
            if game.umpire_override:
                continue

            # Get required umpire count
            required_count = game.umpire_count
            if required_count == 0:
                continue

            # Check slot ownership
            is_owned = is_slot_sdll_owned(game)

            flags.append(RedFlag(
                flag_type='missing_assignment',
                severity='error',
                message=f"No umpire delegation decision for game",
                game_id=game.ID,
                game=game,
                details={
                    'league': game.league,
                    'required_umpires': required_count,
                    'is_sdll_owned_slot': is_owned,
                    'game_date': game.game_date,
                    'field': game.field_name
                }
            ))

        return flags

    def check_practices_with_umpires(self) -> List[RedFlag]:
        """Find practices that have umpire_override set (shouldn't have umpires)."""
        from sqlalchemy.orm import joinedload

        flags = []

        # Get upcoming practices with umpire_override set
        practices_with_umpires = Game.query.options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel)
        ).filter(
            Game.game_date >= self.now,
            Game.game_date <= self.cutoff,
            Game.active == 1,
            Game.game_type == 'practice',
            Game.umpire_override.isnot(None)
        ).all()

        for game in practices_with_umpires:
            flags.append(RedFlag(
                flag_type='practice_with_umpire',
                severity='warning',
                message=f"Practice has umpire override set to '{game.umpire_override}'",
                game_id=game.ID,
                game=game,
                details={
                    'umpire_override': game.umpire_override,
                    'game_date': game.game_date,
                    'field': game.field_name,
                    'team': game.home_team.display_name if game.home_team else 'Unknown'
                }
            ))

        return flags

    def check_umpire_overlaps(self) -> List[RedFlag]:
        """Find SDL umpires assigned to truly overlapping games.

        Checks games in Assignr where the same official is assigned to multiple
        games that overlap in time (game 2 starts before game 1 ends).

        Back-to-back games (e.g., 2 hours apart for 2-hour games) are NOT flagged
        as that's normal scheduling.
        """
        from app.services.assignr_service import get_assignr_service

        flags = []

        assignr = get_assignr_service()
        if not assignr.is_configured():
            return flags

        # Get games from Assignr for the date range
        start_dt = self.now
        end_dt = self.cutoff

        try:
            assignr_games = assignr.get_all_games(start_dt, end_dt)
        except Exception:
            return flags

        # Build map of official_id -> list of (game_time, game_end_time, game_info)
        # We'll estimate end time as start + 2 hours for games
        GAME_DURATION_HOURS = 2

        official_games: Dict[int, List[Tuple[datetime, datetime, dict]]] = defaultdict(list)

        for game in assignr_games:
            # Skip cancelled games
            if game.get('is_cancelled'):
                continue

            game_time = game.get('_game_date')
            if not game_time:
                continue

            # Estimate end time
            game_end = game_time + timedelta(hours=GAME_DURATION_HOURS)

            # Get assignments
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            for assignment in assignments:
                # Only count accepted assignments
                if assignment.get('accepted') not in [True, 'True']:
                    continue

                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}
                official_id = official.get('id')

                if official_id:
                    official_name = f"{official.get('first_name', '')} {official.get('last_name', '')}".strip()
                    official_games[official_id].append((
                        game_time,
                        game_end,
                        {
                            'assignr_id': game.get('id'),
                            'game_name': game.get('localized_title') or f"{game.get('home', '')} vs {game.get('away', '')}",
                            'official_name': official_name,
                            'field': game.get('venue_name', 'Unknown'),
                            'position': assignment.get('position', 'Unknown')
                        }
                    ))

        # Check for TRUE overlaps within each official's games
        for official_id, games in official_games.items():
            if len(games) < 2:
                continue

            # Sort by start time
            games.sort(key=lambda x: x[0])

            # Check each pair of consecutive games
            for i in range(len(games) - 1):
                start1, end1, info1 = games[i]
                start2, end2, info2 = games[i + 1]

                # Only flag if game 2 starts BEFORE game 1 ends (true overlap)
                if start2 < end1:
                    overlap_minutes = int((end1 - start2).total_seconds() / 60)
                    message = f"Umpire {info1['official_name']} double-booked: games overlap by {overlap_minutes} minutes"

                    flags.append(RedFlag(
                        flag_type='umpire_overlap',
                        severity='error',
                        message=message,
                        official_id=official_id,
                        official_name=info1['official_name'],
                        details={
                            'game1': {
                                'assignr_id': info1['assignr_id'],
                                'name': info1['game_name'],
                                'time': start1.strftime('%Y-%m-%d %I:%M %p'),
                                'field': info1['field'],
                                'position': info1['position']
                            },
                            'game2': {
                                'assignr_id': info2['assignr_id'],
                                'name': info2['game_name'],
                                'time': start2.strftime('%Y-%m-%d %I:%M %p'),
                                'field': info2['field'],
                                'position': info2['position']
                            },
                            'overlap_minutes': overlap_minutes
                        }
                    ))

        return flags

    def check_sdl_without_assignr_assignments(self, days_threshold: int = 3) -> List[RedFlag]:
        """Find games assigned to SDL that have no Assignr assignments.

        Only flags games within days_threshold days (default 3), since assignments
        might not be made far in advance.
        """
        from sqlalchemy.orm import joinedload
        from app.services.assignr_service import get_assignr_service

        flags = []

        assignr = get_assignr_service()
        if not assignr.is_configured():
            return flags

        # Only check games within threshold
        threshold_cutoff = self.now + timedelta(days=days_threshold)

        # Get upcoming SDL-assigned games
        sdl_games = Game.query.options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel)
        ).filter(
            Game.game_date >= self.now,
            Game.game_date <= threshold_cutoff,
            Game.active == 1,
            Game.status == 'scheduled',
            Game.game_type != 'practice',
            Game.umpire_override == 'SDL',
            Game.assignr_id.isnot(None)
        ).all()

        if not sdl_games:
            return flags

        # Get Assignr game details
        start_dt = self.now
        end_dt = threshold_cutoff

        try:
            assignr_games = assignr.get_all_games(start_dt, end_dt)
        except Exception:
            return flags

        # Build lookup of Assignr games with accepted assignments
        assignr_with_assignments = set()
        for game in assignr_games:
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            has_accepted = any(a.get('accepted') in [True, 'True'] for a in assignments)
            if has_accepted:
                assignr_with_assignments.add(str(game.get('id')))

        # Check local SDL games against Assignr
        for game in sdl_games:
            if str(game.assignr_id) not in assignr_with_assignments:
                # Get required count
                league = self._get_league(game.league)
                required = game.umpire_count

                flags.append(RedFlag(
                    flag_type='sdl_without_assignr',
                    severity='error',
                    message=f"SDL-assigned game has no accepted Assignr assignments",
                    game_id=game.ID,
                    game=game,
                    details={
                        'assignr_id': game.assignr_id,
                        'required_umpires': required,
                        'game_date': game.game_date,
                        'field': game.field_name,
                        'league': game.league
                    }
                ))

        return flags


def generate_red_flag_email(report: RedFlagReport, days: int = 7, base_url: str = None) -> Tuple[str, str, str]:
    """Generate email content for a red flag report.

    Returns:
        Tuple of (subject, body_text, body_html)
    """
    import os

    if base_url is None:
        base_url = os.environ.get('APP_URL', 'https://www.southdurhamlittleleague.org')

    total = report.total_count

    if total == 0:
        subject = "SDLL: No umpire issues found"
        body_text = f"No umpire scheduling issues found in the next {days} days."
        body_html = f"<p>No umpire scheduling issues found in the next {days} days.</p>"
        return subject, body_text, body_html

    # Count by severity
    all_flags = (report.missing_assignments + report.practices_with_umpires +
                 report.umpire_overlaps + report.sdl_without_assignr)
    error_count = sum(1 for f in all_flags if f.severity == 'error')
    warning_count = sum(1 for f in all_flags if f.severity == 'warning')

    subject = f"SDLL Alert: {total} umpire issue(s) found"
    if error_count > 0:
        subject = f"🚨 SDLL Alert: {error_count} urgent umpire issue(s)"

    # Plain text version
    lines = [f"Umpire Scheduling Issues ({days}-day lookahead):", ""]

    if report.missing_assignments:
        lines.append(f"❌ GAMES MISSING UMPIRE DELEGATION ({len(report.missing_assignments)}):")
        for flag in report.missing_assignments:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            field = flag.details.get('field', 'TBD')
            home = game.home_team.display_name if game.home_team else 'TBD'
            away = game.away_team.display_name if game.away_team else 'TBD'
            slot_note = "" if flag.details.get('is_sdll_owned_slot', True) else " [AWAY-ONLY SLOT]"
            lines.append(f"  - {game_date} @ {field}{slot_note}")
            lines.append(f"    {away} vs {home} ({flag.details.get('league', '')})")
        lines.append("")

    if report.practices_with_umpires:
        lines.append(f"⚠️ PRACTICES WITH UMPIRE OVERRIDE SET ({len(report.practices_with_umpires)}):")
        for flag in report.practices_with_umpires:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            team = flag.details.get('team', 'Unknown')
            lines.append(f"  - {game_date}: {team} practice")
            lines.append(f"    Umpire override: {flag.details.get('umpire_override', 'Unknown')}")
        lines.append("")

    if report.umpire_overlaps:
        lines.append(f"🚨 UMPIRE DOUBLE-BOOKED ({len(report.umpire_overlaps)}):")
        for flag in report.umpire_overlaps:
            lines.append(f"  - {flag.official_name}:")
            g1 = flag.details.get('game1', {})
            g2 = flag.details.get('game2', {})
            overlap = flag.details.get('overlap_minutes', 0)
            lines.append(f"    Game 1: {g1.get('time', '?')} @ {g1.get('field', '?')}")
            lines.append(f"    Game 2: {g2.get('time', '?')} @ {g2.get('field', '?')}")
            lines.append(f"    Games overlap by {overlap} minutes")
        lines.append("")

    if report.sdl_without_assignr:
        lines.append(f"❌ SDL GAMES WITHOUT ASSIGNR ASSIGNMENTS ({len(report.sdl_without_assignr)}):")
        for flag in report.sdl_without_assignr:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
            field = flag.details.get('field', 'TBD')
            lines.append(f"  - {game_date} @ {field}")
            lines.append(f"    Needs {flag.details.get('required_umpires', '?')} umpire(s)")
        lines.append("")

    lines.append("- SDLL Automated Alert")
    body_text = '\n'.join(lines)

    # HTML version
    html = ['<!DOCTYPE html><html><body style="font-family: Arial, sans-serif; color: #333;">']

    if error_count > 0:
        html.append(f'<h2 style="color: #c33;">🚨 {error_count} Urgent Umpire Issue(s)</h2>')
    else:
        html.append(f'<h2 style="color: #f0ad4e;">⚠️ {total} Umpire Issue(s) Found</h2>')

    html.append(f'<p>Issues found in the next {days} days:</p>')

    # Missing assignments section
    if report.missing_assignments:
        html.append('<h3 style="color: #c33;">❌ Games Missing Umpire Delegation</h3>')
        html.append('<table style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
        for flag in report.missing_assignments:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d') if game.game_date else 'TBD'
            game_time = game.game_date.strftime('%I:%M %p').lstrip('0') if game.game_date else ''
            field = flag.details.get('field', 'TBD')
            home = game.home_team.display_name if game.home_team else 'TBD'
            away = game.away_team.display_name if game.away_team else 'TBD'

            game_date_str = game.game_date.strftime('%Y-%m-%d') if game.game_date else ''
            calendar_url = f"{base_url}/umpires/{game.year}/{1 if game.is_spring else 0}/day/{game_date_str}"

            slot_badge = ''
            if not flag.details.get('is_sdll_owned_slot', True):
                slot_badge = '<span style="background: #ffc107; color: #000; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 8px;">AWAY-ONLY</span>'

            html.append(
                f'<tr style="border-bottom: 1px solid #eee;">'
                f'<td style="padding: 8px 0;">'
                f'<strong>{game_date}</strong> {game_time} @ {field}{slot_badge}<br>'
                f'<span style="color: #555;">{away} vs {home}</span><br>'
                f'<span style="color: #888; font-size: 12px;">{flag.details.get("league", "")}</span>'
                f'</td>'
                f'<td style="padding: 8px; text-align: right; vertical-align: top;">'
                f'<a href="{calendar_url}" style="color: #1976d2;">View Day</a>'
                f'</td>'
                f'</tr>'
            )
        html.append('</table>')

    # Practices with umpires section
    if report.practices_with_umpires:
        html.append('<h3 style="color: #f0ad4e;">⚠️ Practices with Umpire Override Set</h3>')
        html.append('<p style="font-size: 13px; color: #666;">Practices should not have umpires assigned.</p>')
        html.append('<table style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
        for flag in report.practices_with_umpires:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d') if game.game_date else 'TBD'
            game_time = game.game_date.strftime('%I:%M %p').lstrip('0') if game.game_date else ''
            team = flag.details.get('team', 'Unknown')
            umpire_override = flag.details.get('umpire_override', 'Unknown')

            html.append(
                f'<tr style="border-bottom: 1px solid #eee;">'
                f'<td style="padding: 8px 0;">'
                f'<strong>{game_date}</strong> {game_time}<br>'
                f'<span style="color: #555;">{team} Practice</span><br>'
                f'<span style="color: #c33; font-size: 12px;">Umpire override: {umpire_override}</span>'
                f'</td>'
                f'</tr>'
            )
        html.append('</table>')

    # Umpire overlaps section
    if report.umpire_overlaps:
        html.append('<h3 style="color: #c33;">🚨 Umpire Double-Booked</h3>')
        html.append('<p style="font-size: 13px; color: #666;">Same umpire assigned to overlapping games.</p>')
        for flag in report.umpire_overlaps:
            g1 = flag.details.get('game1', {})
            g2 = flag.details.get('game2', {})
            overlap = flag.details.get('overlap_minutes', 0)

            html.append(
                f'<div style="background: #f9f9f9; padding: 10px; border-radius: 4px; margin-bottom: 10px; border-left: 4px solid #c33;">'
                f'<strong>{flag.official_name}</strong><br>'
                f'<span style="color: #c33; font-size: 13px;">Games overlap by {overlap} minutes</span>'
                f'<table style="width: 100%; margin-top: 8px; font-size: 13px;">'
                f'<tr><td style="padding: 4px 0;">Game 1: {g1.get("time", "?")} @ {g1.get("field", "?")}</td></tr>'
                f'<tr><td style="padding: 4px 0;">Game 2: {g2.get("time", "?")} @ {g2.get("field", "?")}</td></tr>'
                f'</table>'
                f'</div>'
            )

    # SDL without Assignr section
    if report.sdl_without_assignr:
        html.append('<h3 style="color: #c33;">❌ SDL Games Without Assignr Assignments</h3>')
        html.append('<p style="font-size: 13px; color: #666;">These games are assigned to SDL Academy but have no accepted umpires in Assignr.</p>')
        html.append('<table style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
        for flag in report.sdl_without_assignr:
            game = flag.game
            game_date = game.game_date.strftime('%a, %b %d') if game.game_date else 'TBD'
            game_time = game.game_date.strftime('%I:%M %p').lstrip('0') if game.game_date else ''
            field = flag.details.get('field', 'TBD')
            required = flag.details.get('required_umpires', '?')

            html.append(
                f'<tr style="border-bottom: 1px solid #eee;">'
                f'<td style="padding: 8px 0;">'
                f'<strong>{game_date}</strong> {game_time} @ {field}<br>'
                f'<span style="color: #c33; font-size: 12px;">Needs {required} umpire(s) - None assigned in Assignr</span>'
                f'</td>'
                f'</tr>'
            )
        html.append('</table>')

    html.append('<hr><p style="color: #888; font-size: 12px;">SDLL Automated Alert</p></body></html>')
    body_html = '\n'.join(html)

    return subject, body_text, body_html
