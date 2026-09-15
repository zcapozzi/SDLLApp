"""Umpire Game Reapportionment Service.

Provides logic to redistribute Academy umpire games - taking games from
umpires with many assignments and giving them to umpires who need more games.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict

from app.services.assignr_service import get_assignr_service
from app.utils.logging import SDLLLogger

logger = SDLLLogger('reapportionment')


class ReapportionmentService:
    """Service for managing umpire game reapportionment."""

    # Academy group name in Assignr
    ACADEMY_GROUP_NAME = "SDLL Academy"

    def __init__(self):
        self.assignr = get_assignr_service()
        self._academy_official_ids = None

    def _get_academy_official_ids(self) -> set:
        """Get set of official IDs that belong to the Academy group.

        Caches the result for the lifetime of the service instance.
        """
        if self._academy_official_ids is not None:
            return self._academy_official_ids

        officials = self.assignr.get_officials_by_group_name(self.ACADEMY_GROUP_NAME)
        self._academy_official_ids = {o.get('id') for o in officials if o.get('id')}
        logger.info(f"Found {len(self._academy_official_ids)} Academy officials")
        return self._academy_official_ids

    def get_academy_games(
        self,
        sport: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Get assigned Academy games for a sport and date range.

        Only includes games where the assigned umpire is an Academy member.

        Args:
            sport: 'baseball' or 'softball'
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of game dicts with assignment info
        """
        # Get all games in the range
        all_games = self.assignr.get_all_games(start_date, end_date)

        # Enrich with local data (league info)
        all_games = self.assignr.enrich_games_with_local_data(all_games)

        # Get Academy official IDs
        academy_ids = self._get_academy_official_ids()

        # Filter to Academy-assigned games for the specified sport
        academy_games = []
        for game in all_games:
            # Check sport via league name
            local = game.get('_local')
            if not local:
                continue

            league = local.get('league', '')
            if not league:
                continue

            # Determine sport from league name
            game_sport = 'softball' if 'SB' in league or 'Softball' in league.lower() else 'baseball'
            if game_sport != sport:
                continue

            # Check if assigned umpire is Academy member
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            academy_assignment = None

            for assignment in assignments:
                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}
                official_id = official.get('id')

                if official_id and official_id in academy_ids:
                    academy_assignment = {
                        'assignment': assignment,
                        'official': official,
                        'official_id': official_id,
                        'official_name': f"{official.get('first_name', '')} {official.get('last_name', '')}".strip(),
                        'accepted': assignment.get('accepted') in [True, 'True']
                    }
                    break

            if academy_assignment:
                game['_academy_assignment'] = academy_assignment
                academy_games.append(game)

        logger.info(f"Found {len(academy_games)} Academy {sport} games")
        return academy_games

    def get_umpire_game_counts(self, games: List[Dict]) -> Dict[int, Dict]:
        """Count games per umpire from a list of games.

        Args:
            games: List of games with _academy_assignment

        Returns:
            Dict mapping official_id -> {count, name, games}
        """
        counts: Dict[int, Dict] = {}

        for game in games:
            assignment = game.get('_academy_assignment', {})
            official_id = assignment.get('official_id')
            official_name = assignment.get('official_name', 'Unknown')

            if official_id:
                if official_id not in counts:
                    counts[official_id] = {
                        'official_id': official_id,
                        'name': official_name,
                        'count': 0,
                        'games': []
                    }
                counts[official_id]['count'] += 1
                counts[official_id]['games'].append(game)

        return counts

    def score_candidates(
        self,
        games: List[Dict],
        umpire_counts: Dict[int, Dict]
    ) -> List[Dict]:
        """Score games by reassignment value.

        Higher scores mean the game is a better candidate for reassignment
        (i.e., assigned to an umpire with many games).

        Score = umpire_game_count / avg_game_count

        Args:
            games: List of games with _academy_assignment
            umpire_counts: Dict from get_umpire_game_counts

        Returns:
            Games sorted by score (descending), with score added
        """
        if not umpire_counts:
            return games

        # Calculate average game count
        total_games = sum(u['count'] for u in umpire_counts.values())
        num_umpires = len(umpire_counts)
        avg_count = total_games / num_umpires if num_umpires > 0 else 1

        # Score each game
        scored_games = []
        for game in games:
            assignment = game.get('_academy_assignment', {})
            official_id = assignment.get('official_id')

            if official_id and official_id in umpire_counts:
                umpire_count = umpire_counts[official_id]['count']
                score = umpire_count / avg_count if avg_count > 0 else 0
            else:
                score = 0

            game['_score'] = round(score, 2)
            game['_umpire_game_count'] = umpire_counts.get(official_id, {}).get('count', 0)
            scored_games.append(game)

        # Sort by score descending
        scored_games.sort(key=lambda g: g.get('_score', 0), reverse=True)
        return scored_games

    def get_unassigned_games(
        self,
        sport: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Find unassigned games that could be offered as replacements.

        Args:
            sport: 'baseball' or 'softball'
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of unassigned games for the sport
        """
        # Get all games in the range
        all_games = self.assignr.get_all_games(start_date, end_date)

        # Enrich with local data
        all_games = self.assignr.enrich_games_with_local_data(all_games)

        # Filter to unassigned games for the specified sport
        unassigned_games = []
        for game in all_games:
            # Check sport via league name
            local = game.get('_local')
            if not local:
                continue

            league = local.get('league', '')
            if not league:
                continue

            game_sport = 'softball' if 'SB' in league or 'Softball' in league.lower() else 'baseball'
            if game_sport != sport:
                continue

            # Check if unassigned (no accepted assignments)
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            has_accepted = any(a.get('accepted') in [True, 'True'] for a in assignments)

            if not has_accepted:
                unassigned_games.append(game)

        logger.info(f"Found {len(unassigned_games)} unassigned {sport} games")
        return unassigned_games

    def execute_unassign(self, game_assignr_id: int) -> Tuple[bool, str]:
        """Unassign a game (remove all officials).

        Args:
            game_assignr_id: Assignr game ID

        Returns:
            Tuple of (success, message)
        """
        success, error = self.assignr.unassign_game(game_assignr_id)
        if success:
            return True, f"Successfully unassigned game {game_assignr_id}"
        else:
            return False, f"Failed to unassign game: {error}"

    def execute_reassign(
        self,
        game_assignr_id: int,
        new_official_id: int
    ) -> Tuple[bool, str]:
        """Reassign a game to a new official.

        First unassigns the game, then assigns to the new official.

        Args:
            game_assignr_id: Assignr game ID
            new_official_id: Assignr official ID to assign to

        Returns:
            Tuple of (success, message)
        """
        # First unassign
        success, error = self.assignr.unassign_game(game_assignr_id)
        if not success:
            return False, f"Failed to unassign game: {error}"

        # Then assign to new official
        success, error = self.assignr.assign_official_to_game(game_assignr_id, new_official_id)
        if not success:
            return False, f"Game unassigned but failed to assign to new official: {error}"

        return True, f"Successfully reassigned game {game_assignr_id} to official {new_official_id}"

    def send_notification(
        self,
        official_id: int,
        subject: str,
        body: str
    ) -> Tuple[bool, str]:
        """Send a notification message to an official.

        Args:
            official_id: Assignr official ID
            subject: Message subject
            body: Message body

        Returns:
            Tuple of (success, message)
        """
        success, error = self.assignr.send_message([official_id], subject, body)
        if success:
            return True, "Message sent successfully"
        else:
            return False, f"Failed to send message: {error}"

    def get_academy_umpires_summary(
        self,
        sport: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Get summary of Academy umpires and their game counts.

        Args:
            sport: 'baseball' or 'softball'
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of umpire summaries sorted by game count
        """
        games = self.get_academy_games(sport, start_date, end_date)
        counts = self.get_umpire_game_counts(games)

        # Convert to list and sort by count
        umpires = list(counts.values())
        umpires.sort(key=lambda u: u['count'], reverse=True)

        return umpires

    def get_reapportionment_dashboard_data(
        self,
        sport: str,
        year: int,
        is_spring: bool,
        days_ahead: int = 30
    ) -> Dict[str, Any]:
        """Get all data needed for the reapportionment dashboard.

        Args:
            sport: 'baseball' or 'softball'
            year: Season year
            is_spring: True for spring, False for fall
            days_ahead: Number of days ahead to look for games

        Returns:
            Dict with dashboard data
        """
        # Calculate date range
        today = datetime.now()
        start_date = today
        end_date = today + timedelta(days=days_ahead)

        # Get Academy games with counts and scores
        academy_games = self.get_academy_games(sport, start_date, end_date)
        umpire_counts = self.get_umpire_game_counts(academy_games)
        scored_games = self.score_candidates(academy_games, umpire_counts)

        # Get unassigned games
        unassigned_games = self.get_unassigned_games(sport, start_date, end_date)

        # Get umpire summary
        umpires = list(umpire_counts.values())
        umpires.sort(key=lambda u: u['count'], reverse=True)

        # Calculate stats
        total_games = len(scored_games)
        avg_games = total_games / len(umpires) if umpires else 0

        return {
            'sport': sport,
            'year': year,
            'is_spring': is_spring,
            'start_date': start_date,
            'end_date': end_date,
            'days_ahead': days_ahead,
            'assigned_games': scored_games,
            'unassigned_games': unassigned_games,
            'umpires': umpires,
            'umpire_counts': umpire_counts,
            'total_assigned': total_games,
            'total_unassigned': len(unassigned_games),
            'avg_games_per_umpire': round(avg_games, 1)
        }


# Singleton instance
_reapportionment_service = None


def get_reapportionment_service() -> ReapportionmentService:
    """Get the singleton ReapportionmentService instance."""
    global _reapportionment_service
    if _reapportionment_service is None:
        _reapportionment_service = ReapportionmentService()
    return _reapportionment_service
