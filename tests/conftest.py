"""Pytest fixtures for SDLL tests"""

import os
import pytest
from cryptography.fernet import Fernet

# Set test configuration before importing app
os.environ['FLASK_CONFIG'] = 'testing'
os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from app import create_app, db
from app.models.user import User
from app.models.team import TeamSeason
from app.models.game import Game


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
