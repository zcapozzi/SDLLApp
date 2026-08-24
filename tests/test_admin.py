"""Tests for admin user management"""

import pytest
from flask import url_for
from app.models.user import User
from app import db


class TestAdminAccess:
    """Test admin access controls"""

    def test_users_page_requires_login(self, client):
        """Non-authenticated users should be redirected to login"""
        response = client.get('/admin/users')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_users_page_requires_admin(self, client, app):
        """Non-admin users should be redirected with error"""
        with app.app_context():
            # Create a regular user
            existing = User.get_by_email('viewer@test.com')
            if not existing:
                regular_user = User.create_user(
                    email='viewer@test.com',
                    password='testpass123',
                    name='Test Viewer',
                    role='viewer'
                )
            else:
                regular_user = existing

            # Log in as regular user (viewer role)
            client.post('/auth/login', data={
                'email': 'viewer@test.com',
                'password': 'testpass123'
            })

            response = client.get('/admin/users', follow_redirects=True)
            assert b'Admin access required' in response.data

    def test_users_page_accessible_to_admin(self, client, app):
        """Admin users should be able to access users page"""
        with app.app_context():
            # Create admin user
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                admin_user = User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            # Log in as admin
            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.get('/admin/users')
            assert response.status_code == 200
            assert b'User Management' in response.data

    def test_add_user_page_accessible_to_admin(self, client, app):
        """Admin users should be able to access add user page"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.get('/admin/users/add')
            assert response.status_code == 200
            assert b'Add User' in response.data


class TestUserCreation:
    """Test creating users"""

    def test_create_user_success(self, client, app):
        """Admin should be able to create a new user"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            import uuid
            unique_email = f'newuser-{uuid.uuid4().hex[:8]}@example.com'

            response = client.post('/admin/users', data={
                'action': 'add',
                'first_name': 'Test',
                'last_name': 'NewUser',
                'email': unique_email,
                'phone': '555-1234',
                'role': 'viewer',
                'send_welcome': ''  # Don't send email in test
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'created successfully' in response.data

            # Verify user was created
            new_user = User.get_by_email(unique_email)
            assert new_user is not None
            assert new_user.name == 'Test NewUser'
            assert new_user.role == 'viewer'

    def test_create_user_duplicate_email(self, client, app):
        """Should not allow duplicate emails"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            import uuid
            unique_email = f'duplicate-{uuid.uuid4().hex[:8]}@example.com'

            # Create first user
            client.post('/admin/users', data={
                'action': 'add',
                'first_name': 'Test',
                'last_name': 'User',
                'email': unique_email,
                'role': 'viewer'
            })

            # Try to create user with same email
            response = client.post('/admin/users', data={
                'action': 'add',
                'first_name': 'Another',
                'last_name': 'User',
                'email': unique_email,
                'role': 'viewer'
            }, follow_redirects=True)

            assert b'already exists' in response.data


class TestUserEditing:
    """Test editing users"""

    def test_edit_user_role(self, client, app):
        """Admin should be able to change user roles"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            import uuid
            unique_email = f'editme-{uuid.uuid4().hex[:8]}@test.com'
            target_user = User.create_user(
                email=unique_email,
                password='testpass123',
                name='Edit Target',
                role='viewer'
            )

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.post('/admin/users', data={
                'action': 'edit',
                'user_id': target_user.ID,
                'role': 'scheduler',
                'name': target_user.name
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'updated successfully' in response.data

            # Verify role was updated
            db.session.refresh(target_user)
            assert target_user.role == 'scheduler'

    def test_cannot_edit_self(self, client, app):
        """Admin should not be able to edit themselves via this form"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                admin_user = User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )
            else:
                admin_user = existing

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.post('/admin/users', data={
                'action': 'edit',
                'user_id': admin_user.ID,
                'role': 'viewer'
            }, follow_redirects=True)

            assert b'cannot edit your own' in response.data

            # Verify role was NOT changed
            db.session.refresh(admin_user)
            assert admin_user.role == 'admin'


class TestUserActivation:
    """Test activating/deactivating users"""

    def test_deactivate_user(self, client, app):
        """Admin should be able to deactivate users"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )

            import uuid
            unique_email = f'deactivate-{uuid.uuid4().hex[:8]}@test.com'
            target_user = User.create_user(
                email=unique_email,
                password='testpass123',
                name='Deactivate Target',
                role='viewer'
            )

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.post('/admin/users', data={
                'action': 'toggle_active',
                'user_id': target_user.ID
            }, follow_redirects=True)

            assert response.status_code == 200
            assert b'deactivated' in response.data

            db.session.refresh(target_user)
            assert target_user.active == 0

    def test_cannot_deactivate_self(self, client, app):
        """Admin should not be able to deactivate themselves"""
        with app.app_context():
            # Ensure admin user exists
            existing = User.get_by_email('admintest@test.com')
            if not existing:
                admin_user = User.create_user(
                    email='admintest@test.com',
                    password='testpass123',
                    name='Test Admin',
                    role='admin'
                )
            else:
                admin_user = existing

            client.post('/auth/login', data={
                'email': 'admintest@test.com',
                'password': 'testpass123'
            })

            response = client.post('/admin/users', data={
                'action': 'toggle_active',
                'user_id': admin_user.ID
            }, follow_redirects=True)

            assert b'cannot deactivate your own' in response.data

            db.session.refresh(admin_user)
            assert admin_user.active == 1
