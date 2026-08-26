"""Functional tests for game management."""

import pytest
import json
from datetime import datetime
from app.models.game import Game
from app.models.field import Field
from app.extensions import db


class TestGameIndex:
    """Tests for game listing page."""

    def test_index_requires_login(self, client):
        """Game index redirects to login when not authenticated."""
        response = client.get('/games/', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    def test_index_loads_when_authenticated(self, authenticated_client):
        """Game index loads successfully when logged in."""
        response = authenticated_client.get('/games/')
        assert response.status_code == 200


class TestGameUpcoming:
    """Tests for upcoming games page."""

    def test_upcoming_page_loads(self, authenticated_client):
        """Upcoming games page loads successfully."""
        response = authenticated_client.get('/games/upcoming')
        assert response.status_code == 200


class TestGameCalendar:
    """Tests for game calendar view."""

    def test_calendar_page_loads(self, authenticated_client):
        """Calendar page loads successfully."""
        response = authenticated_client.get('/games/2026/0/calendar')
        assert response.status_code == 200


class TestGameManagement:
    """Tests for game management page."""

    def test_manage_page_loads(self, scheduler_client):
        """Game management page loads successfully."""
        response = scheduler_client.get('/games/2026/0/manage')
        assert response.status_code == 200

    def test_create_game(self, scheduler_client, team_factory, field_factory, app):
        """Creating a game adds it to the database."""
        with app.app_context():
            home_team = team_factory('Home Team Create')
            away_team = team_factory('Away Team Create')
            field = field_factory('Create Game Field')

            response = scheduler_client.post('/games/2026/0/manage', data={
                'action': 'create_game',
                'league': 'BB Majors',
                'game_type': 'regular',
                'game_date': '2026-09-15',
                'game_time': '18:00',
                'field_id': field.ID,
                'home_id': home_team.team_ID,
                'away_id': away_team.team_ID
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'Game created' in response.data

            # Verify in database
            game = Game.query.filter_by(
                home_ID=home_team.team_ID,
                away_ID=away_team.team_ID,
                active=1
            ).first()
            assert game is not None
            assert game.field_id == field.ID

            # Cleanup
            game.active = 0

    def test_create_game_missing_fields(self, scheduler_client):
        """Creating a game without required fields shows error."""
        response = scheduler_client.post('/games/2026/0/manage', data={
            'action': 'create_game',
            'league': '',
            'game_date': '',
            'game_time': '',
            'field_id': ''
        }, follow_redirects=True)

        assert response.status_code == 200
        # Should show an error for missing required fields
        assert b'required' in response.data.lower()

    def test_update_game(self, scheduler_client, game_factory, field_factory, app):
        """Updating a game changes its values in database."""
        with app.app_context():
            game = game_factory()
            game_id = game.ID
            new_field = field_factory('Updated Field')

            response = scheduler_client.post('/games/2026/0/manage', data={
                'action': 'update_game',
                'game_id': game_id,
                'game_date': '2026-09-20',
                'game_time': '19:00',
                'field_id': new_field.ID,
                'home_id': game.home_ID,
                'away_id': game.away_ID,
                'game_type': 'regular',
                'status': 'scheduled'
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'Game updated' in response.data

            # Verify database
            updated_game = Game.query.get(game_id)
            assert updated_game.field_id == new_field.ID

    def test_delete_game(self, scheduler_client, game_factory, app):
        """Deleting a game soft-deletes it."""
        with app.app_context():
            game = game_factory()
            game_id = game.ID

            response = scheduler_client.post('/games/2026/0/manage', data={
                'action': 'delete_game',
                'game_id': game_id
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'deleted' in response.data.lower()

            # Verify soft delete
            deleted_game = Game.query.get(game_id)
            assert deleted_game.active == 0


class TestGameAPI:
    """Tests for game API endpoints."""

    def test_api_get_game(self, scheduler_client, game_factory, app):
        """API returns game details."""
        with app.app_context():
            game = game_factory()

            response = scheduler_client.get(f'/games/api/game/{game.ID}')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data['success'] is True
            assert data['game']['id'] == game.ID

    def test_api_get_nonexistent_game(self, scheduler_client):
        """API returns 404 for nonexistent game."""
        response = scheduler_client.get('/games/api/game/999999')
        assert response.status_code == 404

    def test_api_move_game(self, scheduler_client, game_factory, app):
        """API moves game to new date/time/field."""
        with app.app_context():
            game = game_factory()
            new_field = Field.query.filter_by(active=1).first()
            if not new_field:
                from app.models.field import Field as FieldModel
                new_field = FieldModel(location_title='New Field Location', active=1)
                db.session.add(new_field)
                db.session.commit()

            response = scheduler_client.post('/games/api/move-game',
                data=json.dumps({
                    'game_id': game.ID,
                    'new_date': '2026-09-22',
                    'new_time': '19:30',
                    'new_field': str(new_field.ID)
                }),
                content_type='application/json'
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True

            # Verify database
            updated = Game.query.get(game.ID)
            assert updated.field_id == new_field.ID
            assert updated.game_date.strftime('%Y-%m-%d') == '2026-09-22'

    def test_api_move_game_permission_denied(self, authenticated_client, game_factory, app):
        """API denies game move without scheduler role."""
        # This test checks that non-scheduler users can't move games
        # The authenticated_client uses test_user which has scheduler role
        # So this test needs a viewer user
        pass  # TODO: Create viewer_client fixture

    def test_api_cancel_game(self, scheduler_client, game_factory, app):
        """API cancels game."""
        with app.app_context():
            game = game_factory()

            response = scheduler_client.post('/games/api/cancel-game',
                data=json.dumps({
                    'game_id': game.ID,
                    'reason': 'Test cancellation'
                }),
                content_type='application/json'
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True

            # Verify database
            cancelled = Game.query.get(game.ID)
            assert cancelled.status == 'cancelled'

    def test_api_add_event(self, scheduler_client, team_factory, field_factory, app):
        """API adds new event (practice/game)."""
        with app.app_context():
            team = team_factory('API Event Team')
            field = field_factory('API Event Field')

            response = scheduler_client.post('/games/api/2026/0/add-event',
                data=json.dumps({
                    'event_type': 'practice',
                    'league': 'BB Majors',
                    'game_date': '2026-09-10',
                    'game_time': '18:00',
                    'field_name': field.location_title,
                    'home_team_id': team.team_ID
                }),
                content_type='application/json'
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True


class TestRainoutManagement:
    """Tests for rainout handling."""

    def test_rainout_page_loads(self, scheduler_client):
        """Rainout page loads successfully."""
        response = scheduler_client.get('/games/2026/0/rainout')
        assert response.status_code == 200


class TestGameModel:
    """Tests for Game model methods."""

    @pytest.mark.quick
    def test_season_name(self, app):
        """Test season_name property."""
        with app.app_context():
            game = Game(is_spring=1)
            assert game.season_name == 'Spring'

            game.is_spring = 0
            assert game.season_name == 'Fall'

    @pytest.mark.quick
    def test_duration_minutes_regular(self, app):
        """Test duration_minutes for regular games."""
        with app.app_context():
            game = Game(game_type='regular', away_ID=1)
            assert game.duration_minutes == 120

    @pytest.mark.quick
    def test_duration_minutes_no_time_limit(self, app):
        """Test duration_minutes for no-time-limit games."""
        with app.app_context():
            game = Game(game_type='regular', away_ID=1, no_time_limit=1)
            assert game.duration_minutes == 180

    @pytest.mark.quick
    def test_duration_minutes_practice(self, app):
        """Test duration_minutes for practices."""
        with app.app_context():
            game = Game(game_type='practice', home_ID=1, away_ID=None)
            assert game.duration_minutes == 90

    @pytest.mark.quick
    def test_display_type_regular(self, app):
        """Test display_type for regular games."""
        with app.app_context():
            game = Game(game_type='regular', away_ID=1, is_scrimmage=0)
            assert game.display_type == 'regular'

    @pytest.mark.quick
    def test_display_type_scrimmage(self, app):
        """Test display_type for scrimmages."""
        with app.app_context():
            game = Game(game_type='regular', away_ID=1, is_scrimmage=1)
            assert game.display_type == 'scrimmage'

    @pytest.mark.quick
    def test_display_type_practice(self, app):
        """Test display_type for practices."""
        with app.app_context():
            game = Game(game_type='practice', home_ID=1, away_ID=None)
            assert game.display_type == 'practice'

    @pytest.mark.quick
    def test_display_type_playoff(self, app):
        """Test display_type for playoff games."""
        with app.app_context():
            game = Game(game_type='playoff', away_ID=1, is_scrimmage=0)
            assert game.display_type == 'playoff'

    @pytest.mark.quick
    def test_has_score(self, app):
        """Test has_score property."""
        with app.app_context():
            game = Game(home_score=5, away_score=3)
            assert game.has_score is True

            game = Game(home_score=None, away_score=None)
            assert game.has_score is False

    @pytest.mark.quick
    def test_score_display(self, app):
        """Test score_display property."""
        with app.app_context():
            game = Game(home_score=5, away_score=3)
            assert game.score_display == '5-3'

            game = Game(home_score=None, away_score=None)
            assert game.score_display is None
