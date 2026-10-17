"""Pitching report service - aggregate pitching stats by team/league."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models.pitching_stats import PitchingStats
from app.models.post_game_report import PostGameReport
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.player import Player
from app.utils.league_helpers import get_league_id_from_param


@dataclass
class PitcherSummary:
    """Aggregated pitching stats for a single pitcher."""
    player: Player
    appearances: int
    total_pitches: int
    total_strikes: int
    total_innings: float
    strike_ball_ratio: Optional[float]
    total_strikeouts: int
    total_walks: int
    total_earned_runs: int
    era: Optional[float]


@dataclass
class TeamPitchingSummary:
    """Pitching summary for a team."""
    team: TeamSeason
    pitchers: List[PitcherSummary]


class PitchingReportService:
    """Service for generating pitching reports."""

    @staticmethod
    def get_league_pitching_summary(year: int, is_spring: int, league_param) -> List[TeamPitchingSummary]:
        """Get pitching summary for all teams in a league.

        Args:
            year: Season year
            is_spring: 1 for spring, 0 for fall
            league_param: League name or ID

        Returns:
            List of TeamPitchingSummary objects, one per team
        """
        # Convert league name to ID
        league_id = get_league_id_from_param(league_param)
        if not league_id:
            return []

        # Get all teams in this league
        teams = TeamSeason.query.filter(
            TeamSeason.year == year,
            TeamSeason.is_spring == is_spring,
            TeamSeason.league_id == league_id,
            TeamSeason.is_placeholder == 0,
            TeamSeason.active == 1
        ).order_by(TeamSeason.display_name).all()

        if not teams:
            return []

        team_ids = {t.team_ID for t in teams}
        team_lookup = {t.team_ID: t for t in teams}

        # Get aggregated pitching stats grouped by team and player
        # Join through PostGameReport -> Game to filter by season/league
        stats_query = db.session.query(
            PostGameReport.team_id,
            PitchingStats.player_id,
            func.count(PitchingStats.id).label('appearances'),
            func.sum(PitchingStats.pitch_count).label('total_pitches'),
            func.sum(PitchingStats.strikes).label('total_strikes'),
            func.sum(PitchingStats.innings_pitched).label('total_innings'),
            func.sum(PitchingStats.strikeouts).label('total_strikeouts'),
            func.sum(PitchingStats.walks).label('total_walks'),
            func.sum(PitchingStats.earned_runs).label('total_earned_runs')
        ).join(
            PostGameReport, PitchingStats.report_id == PostGameReport.id
        ).join(
            Game, PostGameReport.game_id == Game.ID
        ).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.league_id == league_id,
            Game.active == 1,
            PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
            PostGameReport.team_id.in_(team_ids)
        ).group_by(
            PostGameReport.team_id,
            PitchingStats.player_id
        ).all()

        if not stats_query:
            return []

        # Get all player objects
        player_ids = {row.player_id for row in stats_query}
        players = Player.query.filter(Player.id.in_(player_ids)).all()
        player_lookup = {p.id: p for p in players}

        # Group stats by team
        team_stats: Dict[int, List] = {tid: [] for tid in team_ids}

        for row in stats_query:
            team_id = row.team_id
            player = player_lookup.get(row.player_id)
            if not player or team_id not in team_stats:
                continue

            total_pitches = int(row.total_pitches or 0)
            total_strikes = int(row.total_strikes or 0)
            total_innings = float(row.total_innings or 0)
            total_earned_runs = int(row.total_earned_runs or 0)

            # Calculate strike/ball ratio: strikes / (pitches - strikes)
            balls = total_pitches - total_strikes
            strike_ball_ratio = None
            if balls > 0:
                strike_ball_ratio = round(total_strikes / balls, 2)
            elif total_strikes > 0:
                # All strikes, no balls - show as high ratio
                strike_ball_ratio = float('inf') if total_pitches > 0 else None

            # Calculate ERA: (earned_runs / innings) * 9
            # Note: For Little League, sometimes 6-inning games, but ERA traditionally uses 9
            era = None
            if total_innings > 0:
                era = round((total_earned_runs / total_innings) * 9, 2)

            pitcher_summary = PitcherSummary(
                player=player,
                appearances=int(row.appearances),
                total_pitches=total_pitches,
                total_strikes=total_strikes,
                total_innings=total_innings,
                strike_ball_ratio=strike_ball_ratio,
                total_strikeouts=int(row.total_strikeouts or 0),
                total_walks=int(row.total_walks or 0),
                total_earned_runs=total_earned_runs,
                era=era
            )
            team_stats[team_id].append(pitcher_summary)

        # Sort pitchers by appearances (descending) then pitches
        for team_id in team_stats:
            team_stats[team_id].sort(key=lambda p: (-p.appearances, -p.total_pitches))

        # Build result list (only teams with pitching data)
        result = []
        for team in teams:
            pitchers = team_stats.get(team.team_ID, [])
            if pitchers:  # Only include teams with pitching data
                result.append(TeamPitchingSummary(
                    team=team,
                    pitchers=pitchers
                ))

        return result

    @staticmethod
    def format_innings(innings: float) -> str:
        """Format innings pitched in baseball notation (e.g., 2.1 = 2 and 1/3).

        The database already stores innings in baseball notation:
        - 0.1 = 1/3 inning (1 out)
        - 0.2 = 2/3 inning (2 outs)
        - 1.0 = 1 inning
        - 2.1 = 2 and 1/3 innings

        Args:
            innings: Innings in baseball notation (already stored correctly)

        Returns:
            String representation (e.g., "2.1" or "3.0")
        """
        if innings is None:
            return '-'

        # Data is already stored in baseball notation, just format it
        # Remove trailing .0 for whole innings (2.0 -> "2")
        if innings == int(innings):
            return str(int(innings))

        # Otherwise show as-is (2.1 -> "2.1", 2.2 -> "2.2")
        return str(float(innings))

    @staticmethod
    def format_strike_ball_ratio(ratio: Optional[float]) -> str:
        """Format strike/ball ratio for display.

        Args:
            ratio: Strike to ball ratio

        Returns:
            Formatted string
        """
        if ratio is None:
            return '-'
        if ratio == float('inf'):
            return 'All Strikes'
        return f"{ratio:.2f}"
