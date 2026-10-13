"""Pitch count tracking service - handles pitching stats for post-game reports.

This service manages pitch count tracking for Little League compliance.
Little League has strict rules about pitch counts and required rest days.
"""

from datetime import date, timedelta
from typing import List, Dict, Optional
from app.extensions import db
from app.models.pitching_stats import PitchingStats
from app.models.post_game_report import PostGameReport
from app.models.player import Player, PlayerSeason


# Little League pitch count rules (2024 rules)
# These are the official Little League pitch count limits by age
PITCH_COUNT_LIMITS = {
    # Age: max pitches per day
    7: 50,
    8: 50,
    9: 75,
    10: 75,
    11: 85,
    12: 85,
    13: 95,
    14: 95,
    15: 95,
    16: 105,
    17: 105,
    18: 105,
}

# Rest day requirements based on pitches thrown
# Format: (min_pitches, max_pitches): required_rest_days
REST_DAY_RULES = {
    # Ages 7-8 (same as 9-14 for rest days)
    (7, 8): [
        (1, 20, 0),    # 1-20 pitches: no rest required
        (21, 35, 1),   # 21-35 pitches: 1 day rest
        (36, 50, 2),   # 36-50 pitches: 2 days rest
    ],
    # Ages 9-10
    (9, 10): [
        (1, 20, 0),    # 1-20 pitches: no rest required
        (21, 35, 1),   # 21-35 pitches: 1 day rest
        (36, 50, 2),   # 36-50 pitches: 2 days rest
        (51, 65, 3),   # 51-65 pitches: 3 days rest
        (66, 75, 4),   # 66-75 pitches: 4 days rest
    ],
    # Ages 11-12
    (11, 12): [
        (1, 20, 0),    # 1-20 pitches: no rest required
        (21, 35, 1),   # 21-35 pitches: 1 day rest
        (36, 50, 2),   # 36-50 pitches: 2 days rest
        (51, 65, 3),   # 51-65 pitches: 3 days rest
        (66, 85, 4),   # 66-85 pitches: 4 days rest
    ],
    # Ages 13-16
    (13, 16): [
        (1, 20, 0),    # 1-20 pitches: no rest required
        (21, 35, 1),   # 21-35 pitches: 1 day rest
        (36, 50, 2),   # 36-50 pitches: 2 days rest
        (51, 65, 3),   # 51-65 pitches: 3 days rest
        (66, 95, 4),   # 66-95 pitches: 4 days rest
    ],
}


class PitchCountService:
    """Service for managing pitch count tracking and compliance."""

    @staticmethod
    def save_pitching_stats(report_id: int, pitch_data: List[dict]) -> List[PitchingStats]:
        """Save pitching stats for a report.

        Args:
            report_id: The post-game report ID
            pitch_data: List of dicts with keys:
                - player_id: int
                - pitch_count: int (required)
                - strikes: int (optional)
                - innings_pitched: float (optional)
                - batters_faced: int (optional)
                - hits_allowed: int (optional)
                - walks: int (optional)
                - strikeouts: int (optional)
                - runs_allowed: int (optional)
                - earned_runs: int (optional)
                - notes: str (optional)

        Returns:
            List of PitchingStats objects created/updated
        """
        saved_stats = []

        for data in pitch_data:
            player_id = data.get('player_id')
            pitch_count = data.get('pitch_count', 0)

            # Skip if no player ID or zero pitches (non-pitchers)
            if not player_id or pitch_count <= 0:
                continue

            # Get or create stats record
            stats = PitchingStats.get_or_create(report_id, player_id)
            stats.pitch_count = pitch_count
            stats.strikes = data.get('strikes')
            stats.innings_pitched = data.get('innings_pitched')
            stats.batters_faced = data.get('batters_faced')
            stats.hits_allowed = data.get('hits_allowed')
            stats.walks = data.get('walks')
            stats.strikeouts = data.get('strikeouts')
            stats.runs_allowed = data.get('runs_allowed')
            stats.earned_runs = data.get('earned_runs')
            stats.notes = data.get('notes')

            saved_stats.append(stats)

        db.session.commit()
        return saved_stats

    @staticmethod
    def get_pitching_stats_for_report(report_id: int) -> List[PitchingStats]:
        """Get all pitching stats for a report."""
        return PitchingStats.get_for_report(report_id)

    @staticmethod
    def get_player_pitch_history(player_id: int, days: int = 7) -> List[Dict]:
        """Get player's recent pitch history for rest day calculation.

        Args:
            player_id: The player's ID
            days: Number of days to look back (default 7)

        Returns:
            List of dicts with date, pitch_count, and game info
        """
        stats = PitchingStats.get_recent_for_player(player_id, days)
        history = []

        for s in stats:
            # Get game date from report -> game
            game_date = None
            if s.report and s.report.game:
                game_date = s.report.game.game_date.date() if s.report.game.game_date else None

            history.append({
                'id': s.id,
                'date': game_date,
                'pitch_count': s.pitch_count,
                'innings_pitched': float(s.innings_pitched) if s.innings_pitched else None,
                'stat_line': s.stat_line,
                'report_id': s.report_id,
            })

        return history

    @staticmethod
    def get_required_rest_days(age: int, pitch_count: int) -> int:
        """Calculate required rest days based on Little League rules.

        Args:
            age: Player's league age
            pitch_count: Number of pitches thrown

        Returns:
            Number of required rest days (0-4)
        """
        if pitch_count <= 0:
            return 0

        # Find the appropriate age group
        rules = None
        for (min_age, max_age), age_rules in REST_DAY_RULES.items():
            if min_age <= age <= max_age:
                rules = age_rules
                break

        # Default to 11-12 rules if age not found
        if rules is None:
            rules = REST_DAY_RULES[(11, 12)]

        # Find the matching pitch count range
        for min_pitches, max_pitches, rest_days in rules:
            if min_pitches <= pitch_count <= max_pitches:
                return rest_days

        # If above all ranges, return max rest days (4)
        return 4

    @staticmethod
    def get_pitch_count_limit(age: int) -> int:
        """Get the maximum pitch count allowed for an age.

        Args:
            age: Player's league age

        Returns:
            Maximum pitches allowed per day
        """
        if age < 7:
            return 50  # Default for very young players
        if age > 18:
            return 105  # Max for oldest players
        return PITCH_COUNT_LIMITS.get(age, 85)  # Default to 85

    @staticmethod
    def check_pitcher_eligibility(player_id: int, game_date: date, org_season=None) -> Dict:
        """Check if player is eligible to pitch on a given date.

        Args:
            player_id: The player's ID
            game_date: The date of the upcoming game
            org_season: OrgSeason object for calculating league age (optional)

        Returns:
            Dict with:
                - eligible: bool
                - reason: str (if not eligible)
                - available_after: date (when they can pitch next)
                - recent_pitches: list of recent pitching appearances
        """
        player = Player.query.get(player_id)
        if not player:
            return {
                'eligible': False,
                'reason': 'Player not found',
                'available_after': None,
                'recent_pitches': []
            }

        # Calculate league age if we have the season
        league_age = 12  # Default assumption
        if org_season:
            league_age = player.league_age(org_season) or 12

        # Get recent pitching history (last 7 days)
        recent_stats = PitchingStats.get_recent_for_player(player_id, days=7)

        if not recent_stats:
            return {
                'eligible': True,
                'reason': None,
                'available_after': None,
                'recent_pitches': []
            }

        # Check each recent appearance for rest requirements
        available_after = None
        recent_pitches = []

        for stats in recent_stats:
            pitch_date = None
            if stats.report and stats.report.game and stats.report.game.game_date:
                pitch_date = stats.report.game.game_date.date()

            if pitch_date:
                rest_required = PitchCountService.get_required_rest_days(league_age, stats.pitch_count)
                rest_until = pitch_date + timedelta(days=rest_required)

                recent_pitches.append({
                    'date': pitch_date,
                    'pitch_count': stats.pitch_count,
                    'rest_required': rest_required,
                    'available_date': rest_until + timedelta(days=1)
                })

                # Track the latest "available after" date
                if available_after is None or rest_until >= available_after:
                    available_after = rest_until

        # Check if game_date is after all rest requirements
        eligible = available_after is None or game_date > available_after

        return {
            'eligible': eligible,
            'reason': f'Must rest until {available_after.strftime("%m/%d")}' if not eligible else None,
            'available_after': available_after + timedelta(days=1) if available_after and not eligible else None,
            'recent_pitches': recent_pitches
        }

    @staticmethod
    def get_team_pitching_summary(team_id: int, year: int, is_spring: int) -> List[Dict]:
        """Get pitching summary for all players on a team for the season.

        Args:
            team_id: The team's ID
            year: Season year
            is_spring: 1 for spring, 0 for fall

        Returns:
            List of dicts with player info and season pitching totals
        """
        from sqlalchemy.orm import joinedload
        from app.models.game import Game

        # Get players on this team
        players = PlayerSeason.query.filter_by(team_id=team_id).options(
            joinedload(PlayerSeason.player)
        ).all()

        if not players:
            return []

        player_ids = [ps.player_id for ps in players]

        # Get all pitching stats for these players in this season
        stats = db.session.query(PitchingStats).join(
            PostGameReport, PitchingStats.report_id == PostGameReport.id
        ).join(
            Game, PostGameReport.game_id == Game.ID
        ).filter(
            PitchingStats.player_id.in_(player_ids),
            Game.year == year,
            Game.is_spring == is_spring
        ).all()

        # Aggregate by player
        player_stats = {}
        for s in stats:
            if s.player_id not in player_stats:
                player_stats[s.player_id] = {
                    'total_pitches': 0,
                    'appearances': 0,
                    'total_innings': 0,
                    'total_strikeouts': 0,
                    'total_walks': 0,
                }
            player_stats[s.player_id]['total_pitches'] += s.pitch_count or 0
            player_stats[s.player_id]['appearances'] += 1
            if s.innings_pitched:
                player_stats[s.player_id]['total_innings'] += float(s.innings_pitched)
            if s.strikeouts:
                player_stats[s.player_id]['total_strikeouts'] += s.strikeouts
            if s.walks:
                player_stats[s.player_id]['total_walks'] += s.walks

        # Build result with player info
        result = []
        for ps in players:
            pid = ps.player_id
            pstats = player_stats.get(pid, {
                'total_pitches': 0,
                'appearances': 0,
                'total_innings': 0,
                'total_strikeouts': 0,
                'total_walks': 0,
            })

            result.append({
                'player_id': pid,
                'player_name': ps.player.full_name if ps.player else 'Unknown',
                'total_pitches': pstats['total_pitches'],
                'appearances': pstats['appearances'],
                'total_innings': round(pstats['total_innings'], 1),
                'total_strikeouts': pstats['total_strikeouts'],
                'total_walks': pstats['total_walks'],
                'avg_pitches_per_game': round(pstats['total_pitches'] / pstats['appearances'], 1) if pstats['appearances'] > 0 else 0,
            })

        # Sort by total pitches descending
        result.sort(key=lambda x: x['total_pitches'], reverse=True)
        return result
