"""Standings service - calculate league standings from completed games."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import func
from app.extensions import db
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.post_game_report import PostGameReport
from app.models.league import League
from app.utils.league_helpers import get_league_id_from_param


@dataclass
class TeamStanding:
    """Represents a team's standing in the league."""
    team: TeamSeason
    wins: int
    losses: int
    ties: int
    win_pct: float
    runs_scored: int
    runs_allowed: int
    run_diff: int
    innings_fielded: Optional[float]
    runs_allowed_per_inning: Optional[float]


class StandingsService:
    """Service for calculating league standings."""

    @staticmethod
    def get_league_standings(year: int, is_spring: int, league_param) -> List[TeamStanding]:
        """Calculate league standings from completed games.

        Args:
            year: Season year
            is_spring: 1 for spring, 0 for fall
            league_param: League name or ID

        Returns:
            List of TeamStanding objects sorted by win_pct desc, wins desc, run_diff desc
        """
        # Convert league name to ID
        league_id = get_league_id_from_param(league_param)
        if not league_id:
            return []

        # Get all completed regular/playoff games for this league
        games = Game.query.filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.league_id == league_id,
            Game.active == 1,
            Game.status == 'completed',
            Game.game_type.in_(['regular', 'playoff']),
            Game.home_score.isnot(None),
            Game.away_score.isnot(None),
            Game.home_ID.isnot(None),
            Game.away_ID.isnot(None)
        ).all()

        if not games:
            return []

        # Get all teams in this league for the season
        teams = TeamSeason.query.filter(
            TeamSeason.year == year,
            TeamSeason.is_spring == is_spring,
            TeamSeason.league_id == league_id,
            TeamSeason.is_placeholder == 0,
            TeamSeason.active == 1
        ).all()

        # Build team lookup
        team_ids = {t.team_ID for t in teams}

        # Initialize stats for each team
        stats: Dict[int, dict] = {}
        for team in teams:
            stats[team.team_ID] = {
                'team': team,
                'wins': 0,
                'losses': 0,
                'ties': 0,
                'runs_scored': 0,
                'runs_allowed': 0,
            }

        # Calculate wins/losses/ties and runs from completed games
        for game in games:
            home_id = game.home_ID
            away_id = game.away_ID
            home_score = game.home_score
            away_score = game.away_score

            # Update home team stats
            if home_id in stats:
                stats[home_id]['runs_scored'] += home_score
                stats[home_id]['runs_allowed'] += away_score
                if home_score > away_score:
                    stats[home_id]['wins'] += 1
                elif away_score > home_score:
                    stats[home_id]['losses'] += 1
                else:
                    stats[home_id]['ties'] += 1

            # Update away team stats
            if away_id in stats:
                stats[away_id]['runs_scored'] += away_score
                stats[away_id]['runs_allowed'] += home_score
                if away_score > home_score:
                    stats[away_id]['wins'] += 1
                elif home_score > away_score:
                    stats[away_id]['losses'] += 1
                else:
                    stats[away_id]['ties'] += 1

        # Get innings fielded from post-game reports
        innings_by_team = StandingsService._get_innings_fielded(year, is_spring, league_id, team_ids)

        # Build standings list
        standings: List[TeamStanding] = []
        for team_id, data in stats.items():
            total_games = data['wins'] + data['losses'] + data['ties']
            win_pct = data['wins'] / total_games if total_games > 0 else 0.0

            innings = innings_by_team.get(team_id)
            ra_per_inn = None
            if innings and innings > 0:
                ra_per_inn = data['runs_allowed'] / innings

            standings.append(TeamStanding(
                team=data['team'],
                wins=data['wins'],
                losses=data['losses'],
                ties=data['ties'],
                win_pct=round(win_pct, 3),
                runs_scored=data['runs_scored'],
                runs_allowed=data['runs_allowed'],
                run_diff=data['runs_scored'] - data['runs_allowed'],
                innings_fielded=innings,
                runs_allowed_per_inning=round(ra_per_inn, 2) if ra_per_inn is not None else None
            ))

        # Sort by win_pct desc, wins desc, run_diff desc
        standings.sort(key=lambda s: (-s.win_pct, -s.wins, -s.run_diff))

        return standings

    @staticmethod
    def _get_innings_fielded(year: int, is_spring: int, league_id: int, team_ids: set) -> Dict[int, float]:
        """Get total innings fielded for each team from post-game reports.

        Args:
            year: Season year
            is_spring: 1 for spring, 0 for fall
            league_id: League ID
            team_ids: Set of team IDs to include

        Returns:
            Dict mapping team_id -> total innings fielded
        """
        # Query post-game reports for completed games in this league
        results = db.session.query(
            PostGameReport.team_id,
            func.sum(PostGameReport.innings_fielded).label('total_innings')
        ).join(
            Game, PostGameReport.game_id == Game.ID
        ).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.league_id == league_id,
            Game.active == 1,
            Game.status == 'completed',
            PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
            PostGameReport.innings_fielded.isnot(None),
            PostGameReport.team_id.in_(team_ids)
        ).group_by(PostGameReport.team_id).all()

        return {team_id: float(total) if total else 0.0 for team_id, total in results}

    @staticmethod
    def has_ties(standings: List[TeamStanding]) -> bool:
        """Check if any team has ties."""
        return any(s.ties > 0 for s in standings)
