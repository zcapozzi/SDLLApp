"""Assignr API integration service.

Provides methods to fetch games and umpire assignments from the Assignr API.
"""

import os
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple

from app.extensions import db
from app.models.game import Game
from app.utils.logging import SDLLLogger

logger = SDLLLogger('assignr')


class AssignrService:
    """Service for interacting with the Assignr API."""

    BASE_URL = "https://api.assignr.com/api/v2"

    def __init__(self):
        # Support both uppercase and lowercase env var names
        self.client_id = os.environ.get('ASSIGNR_CLIENT_ID') or os.environ.get('assignr_client_id')
        self.client_secret = os.environ.get('ASSIGNR_CLIENT_SECRET') or os.environ.get('assignr_client_secret')
        self.site_id = os.environ.get('ASSIGNR_SITE_ID') or os.environ.get('assignr_site_id')
        self._access_token = None
        self._token_expires_at = None

    def is_configured(self) -> bool:
        """Check if Assignr credentials are configured."""
        return all([self.client_id, self.client_secret, self.site_id])

    def _get_access_token(self) -> Optional[str]:
        """Get or refresh the OAuth2 access token."""
        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        if not self.client_id or not self.client_secret:
            logger.error("Assignr credentials not configured")
            return None

        try:
            response = requests.post(
                "https://app.assignr.com/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "read"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.info(f"Obtained Assignr access token, expires in {expires_in}s")
            return self._access_token

        except requests.RequestException as e:
            logger.error(f"Failed to obtain Assignr access token: {e}")
            return None

    def _request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Make an authenticated request to the Assignr API."""
        token = self._get_access_token()
        if not token:
            return None

        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Assignr API request failed: {e}")
            # Log response body for debugging
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response body: {e.response.text[:500]}")
            return None

    def get_games(
        self,
        start_date: datetime,
        end_date: datetime,
        page: int = 1,
        limit: int = 50  # Assignr API max is 50
    ) -> Tuple[List[Dict], int, int]:
        """Fetch games from Assignr for a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            page: Page number (1-indexed)
            limit: Number of results per page

        Returns:
            Tuple of (games list, total count, total pages)
        """
        if not self.site_id:
            logger.error("Assignr site ID not configured")
            return [], 0, 0

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        url = f"{self.BASE_URL}/sites/{self.site_id}/games"
        params = {
            'page': page,
            'limit': limit,
            'search[start_date]': start_str,
            'search[end_date]': end_str
        }

        data = self._request(url, params=params)
        if not data:
            return [], 0, 0

        games = data.get('_embedded', {}).get('games', [])
        page_info = data.get('page', {})
        total_count = page_info.get('records', len(games))
        total_pages = page_info.get('pages', 1)

        return games, total_count, total_pages

    def get_all_games(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Fetch all games for a date range (handles pagination).

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of all games
        """
        all_games = []
        page = 1
        limit = 50  # Assignr API max is 50

        while True:
            games, total_count, total_pages = self.get_games(
                start_date, end_date, page=page, limit=limit
            )
            all_games.extend(games)

            if page >= total_pages:
                break
            page += 1

        logger.info(f"Fetched {len(all_games)} games from Assignr for {start_date} to {end_date}")
        return all_games

    def get_game_officials(self, game_id: int) -> List[Dict]:
        """Fetch officials (umpires) assigned to a specific game.

        Args:
            game_id: Assignr game ID

        Returns:
            List of official assignments
        """
        url = f"{self.BASE_URL}/games/{game_id}/assignments"
        data = self._request(url)
        if not data:
            return []

        return data.get('_embedded', {}).get('assignments', [])

    def enrich_games_with_local_data(self, assignr_games: List[Dict]) -> List[Dict]:
        """Link Assignr games to local sdll_games records and add info.

        Args:
            assignr_games: List of games from Assignr API

        Returns:
            Enriched games list with local_game data added
        """
        # Get all assignr_ids from the games
        assignr_ids = [str(g.get('id')) for g in assignr_games if g.get('id')]

        if not assignr_ids:
            return assignr_games

        # Fetch matching local games in one query
        local_games = Game.query.filter(
            Game.assignr_id.in_(assignr_ids),
            Game.active == 1
        ).all()

        # Build lookup by assignr_id
        local_lookup = {g.assignr_id: g for g in local_games}

        # Enrich each game
        for game in assignr_games:
            assignr_id = str(game.get('id', ''))
            local_game = local_lookup.get(assignr_id)

            if local_game:
                game['_local'] = {
                    'game_id': local_game.ID,
                    'league': local_game.league,
                    'home_team': local_game.home_team.computed_display_name if local_game.home_team else None,
                    'away_team': local_game.away_team.computed_display_name if local_game.away_team else None,
                    'field': local_game.field_name,
                    'status': local_game.status,
                    'umpire_override': local_game.umpire_override,
                    'umpire_count_override': local_game.umpire_count_override
                }
            else:
                game['_local'] = None

            # Extract accepted umpire names for easy template access
            assignments = game.get('_embedded', {}).get('assignments', []) or []
            accepted_umpires = []
            for assignment in assignments:
                if assignment.get('accepted') in [True, 'True']:
                    embedded = assignment.get('_embedded', {}) or {}
                    official = embedded.get('official', {}) or {}
                    first_name = official.get('first_name', '')
                    last_name = official.get('last_name', '')
                    if first_name or last_name:
                        accepted_umpires.append(f"{first_name} {last_name}".strip())
            game['_accepted_umpires'] = accepted_umpires

        return assignr_games

    def get_umpire_summary(
        self,
        assignr_games: List[Dict]
    ) -> Dict[str, Any]:
        """Build summary statistics for umpire assignments.

        Args:
            assignr_games: List of games from Assignr API

        Returns:
            Dict with summary statistics
        """
        summary = {
            'total_games': len(assignr_games),
            'assigned_games': 0,
            'unassigned_games': 0,
            'by_league': defaultdict(lambda: {'games': 0, 'assigned': 0, 'unassigned': 0}),
            'umpires': defaultdict(lambda: {'games': 0, 'leagues': set()}),
            'by_date': defaultdict(lambda: {'games': 0, 'assigned': 0})
        }

        for game in assignr_games:
            # Parse game date
            game_date_str = game.get('localized_date', '')
            if game_date_str:
                try:
                    game_date = datetime.strptime(game_date_str[:10], '%Y-%m-%d').date()
                except ValueError:
                    game_date = None
            else:
                game_date = None

            # Get league from local data or Assignr
            local = game.get('_local')
            league = local['league'] if local else game.get('league_name', 'Unknown')

            # Count game
            summary['by_league'][league]['games'] += 1

            if game_date:
                summary['by_date'][game_date.isoformat()]['games'] += 1

            # Check assignments - use 'accepted' boolean field per Assignr API
            assignments = game.get('_embedded', {}).get('assignments', []) or []

            # Filter to only accepted assignments (accepted can be True or 'True')
            accepted_assignments = [
                a for a in assignments
                if a.get('accepted') in [True, 'True']
            ]

            has_assignment = len(accepted_assignments) > 0

            # Track umpire stats for accepted assignments
            for assignment in accepted_assignments:
                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}

                # Build name from first_name + last_name
                first_name = official.get('first_name', '')
                last_name = official.get('last_name', '')
                if first_name or last_name:
                    official_name = f"{first_name} {last_name}".strip()
                else:
                    official_name = official.get('name', 'Unknown')

                summary['umpires'][official_name]['games'] += 1
                summary['umpires'][official_name]['leagues'].add(league)

            if has_assignment:
                summary['assigned_games'] += 1
                summary['by_league'][league]['assigned'] += 1
                if game_date:
                    summary['by_date'][game_date.isoformat()]['assigned'] += 1
            else:
                summary['unassigned_games'] += 1
                summary['by_league'][league]['unassigned'] += 1

        # Convert sets to lists for JSON serialization
        for umpire_data in summary['umpires'].values():
            umpire_data['leagues'] = list(umpire_data['leagues'])

        # Convert defaultdicts to regular dicts
        summary['by_league'] = dict(summary['by_league'])
        summary['umpires'] = dict(summary['umpires'])
        summary['by_date'] = dict(summary['by_date'])

        return summary


# Singleton instance
_assignr_service = None


def get_assignr_service() -> AssignrService:
    """Get the singleton AssignrService instance."""
    global _assignr_service
    if _assignr_service is None:
        _assignr_service = AssignrService()
    return _assignr_service
