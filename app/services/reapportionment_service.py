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
        self._managed_partner_codes = None  # Cache for managed partner short_codes

    def _get_managed_partner_codes(self) -> set:
        """Get set of short_codes for partners managed by the org.

        Only games with umpire_override matching these codes should appear
        in reapportionment.
        Caches the result for the lifetime of the service instance.
        """
        if self._managed_partner_codes is not None:
            return self._managed_partner_codes

        from app.models.umpire_partner import UmpirePartner

        # Get partners where is_managed_by_org is True
        partners = UmpirePartner.query.filter(UmpirePartner.is_managed_by_org == True).all()

        # Collect short_codes
        managed_codes = set()
        for partner in partners:
            if partner.short_code:
                managed_codes.add(partner.short_code)

        logger.info(f"Found {len(managed_codes)} managed partner codes: {managed_codes}")
        self._managed_partner_codes = managed_codes
        return self._managed_partner_codes

    def _is_managed_game(self, game: Dict) -> bool:
        """Check if a game is managed by checking its umpire_override field.

        A game is managed if its umpire_override matches a partner with
        is_managed_by_org=True.
        """
        local = game.get('_local')
        if not local:
            return False

        umpire_override = local.get('umpire_override')
        if not umpire_override:
            return False

        managed_codes = self._get_managed_partner_codes()
        return umpire_override in managed_codes

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
        """Get assigned games for a sport and date range.

        Filters to Academy members if the group exists, otherwise shows all assigned games.

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

        # Get Academy official IDs (may be empty if group doesn't exist)
        academy_ids = self._get_academy_official_ids()
        filter_by_academy = len(academy_ids) > 0

        if not filter_by_academy:
            logger.warning("No Academy officials found - showing all assigned games")

        # Filter to assigned games for the specified sport
        filtered_games = []
        for game in all_games:
            # Check sport via league name from local data or Assignr league_name
            local = game.get('_local')
            league = ''
            if local:
                league = local.get('league', '')
            if not league:
                # Fall back to Assignr league_name
                league = game.get('league_name', '')

            if not league:
                continue

            # Determine sport from league name
            league_lower = league.lower()
            if 'sb' in league_lower or 'softball' in league_lower:
                game_sport = 'softball'
            elif 'bb' in league_lower or 'baseball' in league_lower:
                game_sport = 'baseball'
            else:
                # Can't determine sport, skip
                continue

            if game_sport != sport:
                continue

            # Only include games where umpire_override matches a managed partner
            if not self._is_managed_game(game):
                continue

            # Check if game has an assignment
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            game_assignment = None

            for assignment in assignments:
                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}
                official_id = official.get('id')

                if not official_id:
                    continue

                # Only include ACCEPTED assignments to avoid duplicates with unassigned list
                is_accepted = assignment.get('accepted') in [True, 'True']
                if not is_accepted:
                    continue

                # If filtering by Academy, check membership
                if filter_by_academy and official_id not in academy_ids:
                    continue

                game_assignment = {
                    'assignment': assignment,
                    'official': official,
                    'official_id': official_id,
                    'official_name': f"{official.get('first_name', '')} {official.get('last_name', '')}".strip(),
                    'accepted': True,  # We only get here if accepted
                    'is_academy': official_id in academy_ids if filter_by_academy else None
                }
                break

            if game_assignment:
                game['_academy_assignment'] = game_assignment
                filtered_games.append(game)

        logger.info(f"Found {len(filtered_games)} {sport} games (Academy filter: {filter_by_academy})")
        return filtered_games

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

        Higher scores mean the game is a better candidate for reassignment.

        Factors:
        - Base score: umpire_game_count / avg_game_count (more games = higher score)
        - Back-to-back penalty: -0.5 if umpire has another game same day/field

        Single games at a field are better candidates because taking them
        doesn't disrupt a back-to-back schedule.

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

        # Build index of games by umpire, date, and field for back-to-back detection
        umpire_day_field_games = defaultdict(list)
        for game in games:
            assignment = game.get('_academy_assignment', {})
            official_id = assignment.get('official_id')
            if not official_id:
                continue

            # Get date and field
            game_date = game.get('localized_date', '')[:10]  # YYYY-MM-DD
            venue = game.get('_embedded', {}).get('venue', {})
            field_id = venue.get('id') if venue else None

            if game_date and field_id:
                key = (official_id, game_date, field_id)
                umpire_day_field_games[key].append(game.get('id'))

        # Score each game
        scored_games = []
        for game in games:
            assignment = game.get('_academy_assignment', {})
            official_id = assignment.get('official_id')

            if official_id and official_id in umpire_counts:
                umpire_count = umpire_counts[official_id]['count']
                base_score = umpire_count / avg_count if avg_count > 0 else 0
            else:
                base_score = 0

            # Check for back-to-back games (same umpire, same day, same field)
            game_date = game.get('localized_date', '')[:10]
            venue = game.get('_embedded', {}).get('venue', {})
            field_id = venue.get('id') if venue else None

            is_back_to_back = False
            if official_id and game_date and field_id:
                key = (official_id, game_date, field_id)
                games_at_location = umpire_day_field_games.get(key, [])
                is_back_to_back = len(games_at_location) > 1

            # Apply back-to-back penalty (reduce score by 0.5)
            # Single games are better candidates for reassignment
            if is_back_to_back:
                score = max(0, base_score - 0.5)
            else:
                score = base_score

            game['_score'] = round(score, 2)
            game['_umpire_game_count'] = umpire_counts.get(official_id, {}).get('count', 0)
            game['_is_back_to_back'] = is_back_to_back
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
            # Check sport via league name from local data or Assignr league_name
            local = game.get('_local')
            league = ''
            if local:
                league = local.get('league', '')
            if not league:
                # Fall back to Assignr league_name
                league = game.get('league_name', '')

            if not league:
                continue

            # Determine sport from league name
            league_lower = league.lower()
            if 'sb' in league_lower or 'softball' in league_lower:
                game_sport = 'softball'
            elif 'bb' in league_lower or 'baseball' in league_lower:
                game_sport = 'baseball'
            else:
                # Can't determine sport, skip
                continue

            if game_sport != sport:
                continue

            # Only include games where umpire_override matches a managed partner
            if not self._is_managed_game(game):
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
        org_season
    ) -> Dict[str, Any]:
        """Get all data needed for the reapportionment dashboard.

        Args:
            sport: 'baseball' or 'softball'
            org_season: OrgSeason object

        Returns:
            Dict with dashboard data
        """
        # Use season date range
        start_date = org_season.get_opening_day_date()
        end_date = org_season.get_season_end_date()

        # Fallback if dates not set
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = datetime.now() + timedelta(days=90)

        # Convert date to datetime if needed
        if hasattr(start_date, 'year') and not hasattr(start_date, 'hour'):
            start_date = datetime.combine(start_date, datetime.min.time())
        if hasattr(end_date, 'year') and not hasattr(end_date, 'hour'):
            end_date = datetime.combine(end_date, datetime.max.time())

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
            'org_season': org_season,
            'start_date': start_date,
            'end_date': end_date,
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
