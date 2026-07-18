"""Season management tests"""

import pytest


class TestSeasonsList:
    """Tests for seasons list view"""

    def test_seasons_page_requires_login(self, client):
        """Test that seasons page requires authentication"""
        response = client.get('/seasons/')
        # Should redirect to login
        assert response.status_code == 302 or response.status_code == 401

    def test_seasons_page_loads_when_authenticated(self, authenticated_client):
        """Test that seasons page loads for authenticated users"""
        response = authenticated_client.get('/seasons/')
        assert response.status_code == 200


class TestSeasonView:
    """Tests for individual season view"""

    def test_season_view_requires_login(self, client):
        """Test that season view requires authentication"""
        response = client.get('/seasons/2025/0')  # Fall 2025
        assert response.status_code == 302 or response.status_code == 401


class TestSeasonCopy:
    """Tests for season copy wizard"""

    def test_copy_wizard_requires_login(self, client):
        """Test that copy wizard requires authentication"""
        response = client.get('/seasons/copy')
        assert response.status_code == 302 or response.status_code == 401

    def test_copy_wizard_loads_for_scheduler(self, authenticated_client):
        """Test that copy wizard loads for scheduler users"""
        response = authenticated_client.get('/seasons/copy')
        # Should either load (200) or redirect if no permission
        assert response.status_code in [200, 302]


class TestTeamSeasonModel:
    """Tests for TeamSeason model"""

    def test_season_name_property(self, app):
        """Test season_name property"""
        from app.models.team import TeamSeason

        with app.app_context():
            fall_team = TeamSeason(year=2025, is_spring=0)
            spring_team = TeamSeason(year=2025, is_spring=1)

            assert fall_team.season_name == 'Fall'
            assert spring_team.season_name == 'Spring'

    def test_full_season_name(self, app):
        """Test full_season_name property"""
        from app.models.team import TeamSeason

        with app.app_context():
            team = TeamSeason(year=2025, is_spring=0)
            assert team.full_season_name == 'Fall 2025'

    def test_get_by_season(self, app, sample_teams):
        """Test getting teams by season"""
        from app.models.team import TeamSeason

        with app.app_context():
            teams = TeamSeason.get_by_season(2025, 0)  # Fall 2025
            assert len(teams) >= 3  # At least our sample teams


class TestGameModel:
    """Tests for Game model"""

    def test_season_name_property(self, app):
        """Test season_name property"""
        from app.models.game import Game

        with app.app_context():
            fall_game = Game(year=2025, is_spring=0)
            spring_game = Game(year=2025, is_spring=1)

            assert fall_game.season_name == 'Fall'
            assert spring_game.season_name == 'Spring'

    def test_is_upcoming(self, app):
        """Test is_upcoming property"""
        from app.models.game import Game
        from datetime import datetime, timedelta

        with app.app_context():
            future_game = Game(game_date=datetime.utcnow() + timedelta(days=1))
            past_game = Game(game_date=datetime.utcnow() - timedelta(days=1))

            assert future_game.is_upcoming
            assert not past_game.is_upcoming

    def test_needs_umpire(self, app):
        """Test needs_umpire property"""
        from app.models.game import Game

        with app.app_context():
            regular_game = Game(status='scheduled', is_scrimmage=0)
            scrimmage = Game(status='scheduled', is_scrimmage=1)
            completed = Game(status='completed', is_scrimmage=0)

            assert regular_game.needs_umpire
            assert not scrimmage.needs_umpire
            assert not completed.needs_umpire
