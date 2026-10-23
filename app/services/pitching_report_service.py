"""Pitching report service - aggregate pitching stats by team/league."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Set
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
class GameNeedingData:
    """A game that needs post-game data."""
    game_id: int
    team_id: int
    game_date: date
    opponent_name: str


@dataclass
class PitcherSummary:
    """Aggregated pitching stats for a single pitcher."""
    player: Player
    appearances: int
    total_pitches: int
    total_strikes: int
    pitches_with_strike_data: int  # Pitches from games where strikes were recorded
    games_without_strikes: int  # Number of games where strikes were NULL
    total_innings: float
    strike_pct: Optional[float]
    total_strikeouts: int
    total_walks: int


@dataclass
class TeamPitchingSummary:
    """Pitching summary for a team."""
    team: TeamSeason
    pitchers: List[PitcherSummary]
    has_incomplete_strike_data: bool  # True if any pitcher has games without strike counts
    games_missing_strikes: List[GameNeedingData]  # Games with reports but missing strike data
    games_without_reports: List[GameNeedingData]  # Games with no post-game report at all


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

        # Get all completed games for these teams (exclude cancelled/rainout/postponed)
        all_games = Game.query.filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.league_id == league_id,
            Game.active == 1,
            Game.game_date < db.func.now(),
            Game.game_type.in_(['regular', 'playoff']),
            ~Game.status.in_(['cancelled', 'rainout', 'postponed']),
            db.or_(
                Game.home_ID.in_(team_ids),
                Game.away_ID.in_(team_ids)
            )
        ).all()

        # Get all submitted post-game reports for these teams
        submitted_reports = PostGameReport.query.filter(
            PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
            PostGameReport.team_id.in_(team_ids)
        ).all()

        # Build set of (game_id, team_id) that have reports
        games_with_reports = {(r.game_id, r.team_id) for r in submitted_reports}

        # Find games without reports for each team
        games_without_reports_per_team: Dict[int, List[GameNeedingData]] = {tid: [] for tid in team_ids}
        for game in all_games:
            for team_id in [game.home_ID, game.away_ID]:
                if team_id in team_ids:
                    if (game.ID, team_id) not in games_with_reports:
                        opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
                        opponent = team_lookup.get(opponent_id)
                        opponent_name = opponent.computed_display_name if opponent else 'Unknown'
                        games_without_reports_per_team[team_id].append(GameNeedingData(
                            game_id=game.ID,
                            team_id=team_id,
                            game_date=game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date,
                            opponent_name=opponent_name
                        ))

        # Sort games without reports by date
        for team_id in games_without_reports_per_team:
            games_without_reports_per_team[team_id].sort(key=lambda g: g.game_date)

        # Get individual pitching stats (not aggregated) so we can track
        # which games have strike data and which don't
        stats_records = db.session.query(
            PostGameReport.team_id,
            PostGameReport.game_id,
            PitchingStats.player_id,
            PitchingStats.pitch_count,
            PitchingStats.strikes,
            PitchingStats.innings_pitched,
            PitchingStats.strikeouts,
            PitchingStats.walks,
            Game.game_date,
            Game.home_ID,
            Game.away_ID
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
        ).all()

        if not stats_records:
            return []

        # Get all player objects
        player_ids = {row.player_id for row in stats_records}
        players = Player.query.filter(Player.id.in_(player_ids)).all()
        player_lookup = {p.id: p for p in players}

        # Aggregate stats by team and player, tracking strike data availability
        # Key: (team_id, player_id) -> aggregated data
        aggregated: Dict[tuple, dict] = {}
        # Track games missing strike data per team: team_id -> set of (game_id, game_date, opponent_id)
        games_missing_per_team: Dict[int, Set[tuple]] = {tid: set() for tid in team_ids}

        for row in stats_records:
            key = (row.team_id, row.player_id)
            if key not in aggregated:
                aggregated[key] = {
                    'appearances': 0,
                    'total_pitches': 0,
                    'total_strikes': 0,
                    'pitches_with_strike_data': 0,
                    'games_without_strikes': 0,
                    'total_innings': 0.0,
                    'total_strikeouts': 0,
                    'total_walks': 0,
                }

            agg = aggregated[key]
            pitch_count = int(row.pitch_count or 0)

            agg['appearances'] += 1
            agg['total_pitches'] += pitch_count
            agg['total_innings'] += float(row.innings_pitched or 0)
            agg['total_strikeouts'] += int(row.strikeouts or 0)
            agg['total_walks'] += int(row.walks or 0)

            # Track strike data separately
            if row.strikes is not None:
                agg['total_strikes'] += int(row.strikes)
                agg['pitches_with_strike_data'] += pitch_count
            else:
                agg['games_without_strikes'] += 1
                # Track this game as missing strike data
                # Determine opponent: if team is home, opponent is away and vice versa
                opponent_id = row.away_ID if row.team_id == row.home_ID else row.home_ID
                games_missing_per_team[row.team_id].add(
                    (row.game_id, row.team_id, row.game_date, opponent_id)
                )

        # Build pitcher summaries grouped by team
        team_stats: Dict[int, List] = {tid: [] for tid in team_ids}

        for (team_id, player_id), agg in aggregated.items():
            player = player_lookup.get(player_id)
            if not player or team_id not in team_stats:
                continue

            # Calculate strike percentage only from games with strike data
            strike_pct = None
            if agg['pitches_with_strike_data'] > 0:
                strike_pct = round(
                    (agg['total_strikes'] / agg['pitches_with_strike_data']) * 100, 1
                )

            pitcher_summary = PitcherSummary(
                player=player,
                appearances=agg['appearances'],
                total_pitches=agg['total_pitches'],
                total_strikes=agg['total_strikes'],
                pitches_with_strike_data=agg['pitches_with_strike_data'],
                games_without_strikes=agg['games_without_strikes'],
                total_innings=round(agg['total_innings'], 1),  # Round to 1 decimal to avoid floating point artifacts
                strike_pct=strike_pct,
                total_strikeouts=agg['total_strikeouts'],
                total_walks=agg['total_walks'],
            )
            team_stats[team_id].append(pitcher_summary)

        # Sort pitchers by appearances (descending) then pitches
        for team_id in team_stats:
            team_stats[team_id].sort(key=lambda p: (-p.appearances, -p.total_pitches))

        # Build result list - include teams with pitching data OR games needing reports
        result = []
        for team in teams:
            pitchers = team_stats.get(team.team_ID, [])
            games_without_reports = games_without_reports_per_team.get(team.team_ID, [])

            # Check if any pitcher has incomplete strike data
            has_incomplete = any(p.games_without_strikes > 0 for p in pitchers)

            # Build list of games missing strike data with opponent names
            games_missing = []
            if has_incomplete:
                for game_id, team_id, game_date, opponent_id in games_missing_per_team.get(team.team_ID, []):
                    opponent = team_lookup.get(opponent_id)
                    opponent_name = opponent.computed_display_name if opponent else 'Unknown'
                    games_missing.append(GameNeedingData(
                        game_id=game_id,
                        team_id=team_id,
                        game_date=game_date,
                        opponent_name=opponent_name
                    ))
                # Sort by game date
                games_missing.sort(key=lambda g: g.game_date)

            # Include team if it has pitchers OR games without reports
            if pitchers or games_without_reports:
                result.append(TeamPitchingSummary(
                    team=team,
                    pitchers=pitchers,
                    has_incomplete_strike_data=has_incomplete,
                    games_missing_strikes=games_missing,
                    games_without_reports=games_without_reports
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
    def format_strike_pct(pct: Optional[float]) -> str:
        """Format strike percentage for display.

        Args:
            pct: Strike percentage (0-100)

        Returns:
            Formatted string with % symbol
        """
        if pct is None:
            return '-'
        return f"{pct:.0f}%"
