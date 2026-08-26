"""Pytest fixtures for SDLL tests"""

import os
import uuid
import pytest
from datetime import datetime, date, time
from pathlib import Path
from cryptography.fernet import Fernet

# Load .env file for database credentials BEFORE setting test config
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Set test configuration before importing app
os.environ['FLASK_CONFIG'] = 'testing'
# Use encryption key from .env or generate a new one for tests
if not os.environ.get('ENCRYPTION_KEY'):
    os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from app import create_app, db
from app.models.user import User
from app.models.team import TeamSeason
from app.models.game import Game
from app.models.field import Field
from app.models.field_slot import FieldSlot


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    app = create_app('testing')

    # Create test database tables
    with app.app_context():
        # For testing, we might use SQLite or the test MySQL database
        # If the test database doesn't exist, this will fail
        # Make sure to run scripts/create_users_table.sql first
        pass

    yield app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Create application context"""
    with app.app_context():
        yield


@pytest.fixture
def db_session(app):
    """Create database session for tests"""
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def test_user(app):
    """Create a test user"""
    with app.app_context():
        # Check if user already exists
        existing = User.get_by_email('test@example.com')
        if existing:
            return existing

        user = User.create_user(
            email='test@example.com',
            password='testpassword123',
            name='Test User',
            phone='555-555-5555',
            role='scheduler'
        )
        return user


@pytest.fixture
def scheduler_user(app):
    """Create a scheduler test user"""
    with app.app_context():
        existing = User.get_by_email('scheduler@example.com')
        if existing:
            return existing

        return User.create_user(
            email='scheduler@example.com',
            password='scheduler123',
            name='Test Scheduler',
            role='scheduler'
        )


@pytest.fixture
def admin_user(app):
    """Create an admin test user"""
    with app.app_context():
        existing = User.get_by_email('admin@example.com')
        if existing:
            return existing

        return User.create_user(
            email='admin@example.com',
            password='admin12345',
            name='Test Admin',
            role='admin'
        )


@pytest.fixture
def authenticated_client(client, test_user, app):
    """Create an authenticated test client"""
    with app.app_context():
        # Login the test user
        client.post('/auth/login', data={
            'email': 'test@example.com',
            'password': 'testpassword123'
        })
    return client


@pytest.fixture
def sample_teams(app):
    """Create sample teams for testing"""
    with app.app_context():
        teams = []
        leagues = ['BB Majors', 'BB AAA', 'SB Majors']

        for i, league in enumerate(leagues):
            team = TeamSeason(
                active=1,
                year=2025,
                league=league,
                display_name=f'Test Team {i+1}',
                is_placeholder=0,
                is_spring=0  # Fall
            )
            db.session.add(team)
            teams.append(team)

        db.session.commit()
        yield teams

        # Cleanup
        for team in teams:
            db.session.delete(team)
        db.session.commit()


# =============================================================================
# Factory Fixtures for Functional Testing
# =============================================================================

@pytest.fixture
def scheduler_client(client, scheduler_user, app):
    """Create a client authenticated as scheduler user."""
    with app.app_context():
        client.post('/auth/login', data={
            'email': 'scheduler@example.com',
            'password': 'scheduler123'
        })
    return client


@pytest.fixture
def admin_client(client, admin_user, app):
    """Create a client authenticated as admin user."""
    with app.app_context():
        client.post('/auth/login', data={
            'email': 'admin@example.com',
            'password': 'admin12345'
        })
    return client


@pytest.fixture
def field_factory(app):
    """Factory for creating test fields.

    Usage:
        field = field_factory('Test Field')
        field = field_factory('Another Field', is_owned=0)
    """
    created = []

    def _create(name=None, **kwargs):
        with app.app_context():
            if name is None:
                name = f'Test Field {uuid.uuid4().hex[:8]}'

            defaults = {
                'active': 1,
                'location_title': name,
                'is_owned': 1,
                'restriction_type': 'anyone',
                'usage_type': 'both',
                'practice_capacity': 1
            }
            defaults.update(kwargs)

            field = Field(**defaults)
            db.session.add(field)
            db.session.commit()

            # Refresh to get the ID
            db.session.refresh(field)
            field_id = field.ID
            field_name = field.location_title
            created.append(field_id)

            # Return a simple object with the data we need
            return type('FieldData', (), {
                'ID': field_id,
                'location_title': field_name
            })()

    yield _create

    # Cleanup - soft delete all created fields
    with app.app_context():
        try:
            for field_id in created:
                field = Field.query.get(field_id)
                if field:
                    field.active = 0
            db.session.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def team_factory(app):
    """Factory for creating test teams.

    Usage:
        team = team_factory('Test Team', league='BB Majors')
        team = team_factory()  # uses defaults
    """
    created = []

    def _create(name=None, **kwargs):
        with app.app_context():
            if name is None:
                name = f'Test Team {uuid.uuid4().hex[:8]}'

            defaults = {
                'active': 1,
                'year': 2026,
                'is_spring': 0,
                'league': 'BB Majors',
                'display_name': name,
                'is_placeholder': 0
            }
            defaults.update(kwargs)

            team = TeamSeason(**defaults)
            db.session.add(team)
            db.session.commit()

            # Refresh to get the ID
            db.session.refresh(team)
            team_id = team.team_ID
            team_name = team.display_name
            team_league = team.league
            created.append(team_id)

            return type('TeamData', (), {
                'team_ID': team_id,
                'display_name': team_name,
                'league': team_league
            })()

    yield _create

    # Cleanup - soft delete all created teams
    with app.app_context():
        try:
            for team_id in created:
                team = TeamSeason.query.get(team_id)
                if team:
                    team.active = 0
            db.session.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def game_factory(app, team_factory, field_factory):
    """Factory for creating test games.

    Usage:
        game = game_factory()  # creates with auto-generated teams and field
        game = game_factory(home_team=team, away_team=away_team, field=field)
    """
    created = []

    def _create(home_team=None, away_team=None, field=None, **kwargs):
        with app.app_context():
            # Create teams if not provided
            if home_team is None:
                home_team = team_factory('Home Team')
            if away_team is None:
                away_team = team_factory('Away Team')
            if field is None:
                field = field_factory('Game Field')

            defaults = {
                'active': 1,
                'year': 2026,
                'is_spring': 0,
                'league': home_team.league,
                'game_type': 'regular',
                'status': 'scheduled',
                'game_date': datetime(2026, 9, 15, 18, 0),
                'field_id': field.ID,
                'home_ID': home_team.team_ID,
                'away_ID': away_team.team_ID
            }
            defaults.update(kwargs)

            game = Game(**defaults)
            db.session.add(game)
            db.session.commit()

            # Refresh to get the ID
            db.session.refresh(game)
            game_id = game.ID
            created.append(game_id)

            return type('GameData', (), {
                'ID': game_id,
                'home_ID': defaults['home_ID'],
                'away_ID': defaults['away_ID'],
                'field_id': defaults['field_id'],
                'game_date': defaults['game_date'],
                'league': defaults['league']
            })()

    yield _create

    # Cleanup - soft delete all created games
    with app.app_context():
        try:
            for game_id in created:
                game = Game.query.get(game_id)
                if game:
                    game.active = 0
            db.session.commit()
        except Exception:
            # Silently ignore cleanup errors (lock timeouts, etc.)
            db.session.rollback()


@pytest.fixture
def field_slot_factory(app, field_factory):
    """Factory for creating field slots (allocations).

    Usage:
        slot = field_slot_factory(field=my_field, day_of_week=1)
    """
    created = []

    def _create(field=None, **kwargs):
        with app.app_context():
            if field is None:
                field = field_factory('Slot Field')

            defaults = {
                'active': 1,
                'field_ID': field.ID,
                'year': 2026,
                'is_spring': 0,
                'day_of_week': 1,  # Tuesday
                'start_time': time(17, 30),
                'end_time': time(20, 30),
                'is_owned': 1
            }
            defaults.update(kwargs)

            slot = FieldSlot(**defaults)
            db.session.add(slot)
            db.session.commit()

            db.session.refresh(slot)
            slot_id = slot.slot_ID
            created.append(slot_id)

            return type('SlotData', (), {
                'slot_ID': slot_id,
                'field_ID': defaults['field_ID'],
                'day_of_week': defaults['day_of_week']
            })()

    yield _create

    # Cleanup
    with app.app_context():
        try:
            for slot_id in created:
                slot = FieldSlot.query.get(slot_id)
                if slot:
                    slot.active = 0
            db.session.commit()
        except Exception:
            db.session.rollback()


# =============================================================================
# Quick Test Marker Support
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "quick: mark test as quick (no DB required)"
    )
    config.addinivalue_line(
        "markers", "critical: mark test as critical (must pass for push)"
    )


# =============================================================================
# Umpire System Fixtures
# =============================================================================

@pytest.fixture
def umpire_profile_factory(app):
    """Factory for creating test umpire profiles.

    Usage:
        profile = umpire_profile_factory('Test Umpire')
        profile = umpire_profile_factory(is_kid_pitch_eligible=True)
    """
    created_users = []
    created_profiles = []

    def _create(name=None, **kwargs):
        with app.app_context():
            from app.models.umpire_profile import UmpireProfile

            if name is None:
                name = f'Test Umpire {uuid.uuid4().hex[:8]}'

            email = f'{name.lower().replace(" ", "_")}_{uuid.uuid4().hex[:6]}@test.com'

            # Create user with umpire role
            user = User.create_user(
                email=email,
                password='testpass123',
                name=name,
                role='umpire'
            )
            created_users.append(user.ID)

            # Create profile with defaults
            profile_defaults = {
                'user_id': user.ID,
                'is_kid_pitch_eligible': True,
                'status': 'active'
            }
            profile_defaults.update(kwargs)

            profile = UmpireProfile(**profile_defaults)
            db.session.add(profile)
            db.session.commit()

            db.session.refresh(profile)
            created_profiles.append(profile.id)

            return type('ProfileData', (), {
                'id': profile.id,
                'user_id': user.ID,
                'full_name': name,
                'is_kid_pitch_eligible': profile.is_kid_pitch_eligible
            })()

    yield _create

    # Cleanup
    with app.app_context():
        try:
            from app.models.umpire_profile import UmpireProfile
            for profile_id in created_profiles:
                profile = UmpireProfile.query.get(profile_id)
                if profile:
                    db.session.delete(profile)
            for user_id in created_users:
                user = User.query.get(user_id)
                if user:
                    user.active = 0
            db.session.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def umpire_partner_factory(app):
    """Factory for creating test umpire partners.

    Usage:
        partner = umpire_partner_factory('Diamond', 'DIA')
        partner = umpire_partner_factory()  # uses defaults
    """
    created = []

    def _create(name=None, short_code=None, **kwargs):
        with app.app_context():
            from app.models.umpire_partner import UmpirePartner

            if name is None:
                name = f'Test Partner {uuid.uuid4().hex[:8]}'
            if short_code is None:
                short_code = name[:3].upper()

            defaults = {
                'org_id': 1,
                'name': name,
                'short_code': short_code,
                'active': True
            }
            defaults.update(kwargs)

            partner = UmpirePartner(**defaults)
            db.session.add(partner)
            db.session.commit()

            db.session.refresh(partner)
            created.append(partner.id)

            return type('PartnerData', (), {
                'id': partner.id,
                'name': name,
                'short_code': short_code
            })()

    yield _create

    # Cleanup
    with app.app_context():
        try:
            from app.models.umpire_partner import UmpirePartner
            for partner_id in created:
                partner = UmpirePartner.query.get(partner_id)
                if partner:
                    partner.active = False
            db.session.commit()
        except Exception:
            db.session.rollback()


@pytest.fixture
def umpire_user(app):
    """Create a test umpire user."""
    with app.app_context():
        existing = User.get_by_email('testumpire@example.com')
        if existing:
            return existing

        return User.create_user(
            email='testumpire@example.com',
            password='umpire12345',
            name='Test Umpire',
            role='umpire'
        )


@pytest.fixture
def umpire_client(client, umpire_user, app):
    """Create a client authenticated as umpire user."""
    with app.app_context():
        client.post('/auth/login', data={
            'email': 'testumpire@example.com',
            'password': 'umpire12345'
        })
    return client


@pytest.fixture
def league_factory(app):
    """Factory for creating test leagues.

    Usage:
        league = league_factory('Test League')
        league = league_factory('Majors', umpire_source='either')
    """
    created = []

    def _create(name=None, **kwargs):
        with app.app_context():
            from app.models.league import League
            import random

            if name is None:
                name = f'Test League {uuid.uuid4().hex[:8]}'

            # Generate a unique ID in the test range (900000+)
            test_id = random.randint(900000, 999999)

            defaults = {
                'ID': test_id,
                'active': 1,
                'display_name': name,
                'pitch_type': 'kid_pitch',
                'sort_order': 100,
                'umpire_count': 1,
                'umpire_source': 'either',  # Default to allowing partner umpires
            }
            defaults.update(kwargs)

            league = League(**defaults)
            db.session.add(league)
            db.session.commit()

            db.session.refresh(league)
            created.append(league.ID)

            return league

    yield _create

    # Cleanup
    with app.app_context():
        try:
            from app.models.league import League
            for league_id in created:
                league = League.query.get(league_id)
                if league:
                    league.active = 0
            db.session.commit()
        except Exception:
            db.session.rollback()
