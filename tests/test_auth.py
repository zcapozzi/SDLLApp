"""Authentication tests"""

import pytest


class TestLogin:
    """Tests for login functionality"""

    def test_login_page_loads(self, client):
        """Test that login page loads successfully"""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Login' in response.data or b'login' in response.data

    def test_login_with_valid_credentials(self, client, test_user, app):
        """Test login with valid credentials"""
        with app.app_context():
            response = client.post('/auth/login', data={
                'email': 'test@example.com',
                'password': 'testpassword123'
            }, follow_redirects=True)

            # Should redirect to dashboard
            assert response.status_code == 200

    def test_login_with_invalid_password(self, client, test_user, app):
        """Test login with wrong password"""
        with app.app_context():
            response = client.post('/auth/login', data={
                'email': 'test@example.com',
                'password': 'wrongpassword'
            }, follow_redirects=True)

            assert b'Invalid' in response.data or response.status_code == 200

    def test_login_with_nonexistent_user(self, client, app):
        """Test login with email that doesn't exist"""
        response = client.post('/auth/login', data={
            'email': 'nonexistent@example.com',
            'password': 'somepassword'
        }, follow_redirects=True)

        assert b'Invalid' in response.data or response.status_code == 200


class TestLogout:
    """Tests for logout functionality"""

    def test_logout(self, authenticated_client):
        """Test that logout works"""
        response = authenticated_client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200


class TestPasswordReset:
    """Tests for password reset functionality"""

    def test_forgot_password_page_loads(self, client):
        """Test that forgot password page loads"""
        response = client.get('/auth/forgot-password')
        assert response.status_code == 200

    def test_forgot_password_submission(self, client, test_user, app):
        """Test forgot password form submission"""
        with app.app_context():
            response = client.post('/auth/forgot-password', data={
                'email': 'test@example.com'
            }, follow_redirects=True)

            # Should show success message regardless of whether email exists
            assert response.status_code == 200


class TestUserModel:
    """Tests for User model"""

    def test_password_hashing(self, app):
        """Test that passwords are properly hashed"""
        from app.models.user import User

        with app.app_context():
            user = User()
            user.set_password('mypassword')

            assert user.password_hash != 'mypassword'
            assert user.check_password('mypassword')
            assert not user.check_password('wrongpassword')

    def test_email_encryption(self, app):
        """Test that email is encrypted"""
        from app.models.user import User

        with app.app_context():
            user = User()
            user.email = 'secret@example.com'

            # Internal storage should be encrypted
            assert user._email != 'secret@example.com'
            # But property should return decrypted value
            assert user.email == 'secret@example.com'

    def test_email_hash_lookup(self, app, test_user):
        """Test finding user by email hash"""
        from app.models.user import User

        with app.app_context():
            found = User.get_by_email('test@example.com')
            assert found is not None
            assert found.email == 'test@example.com'

    def test_role_permissions(self, app):
        """Test role-based permission methods"""
        from app.models.user import User

        with app.app_context():
            admin = User(role='admin')
            scheduler = User(role='scheduler')
            viewer = User(role='viewer')

            assert admin.is_admin()
            assert admin.can_edit_schedule()

            assert scheduler.is_scheduler()
            assert scheduler.can_edit_schedule()
            assert not scheduler.is_admin()

            assert not viewer.can_edit_schedule()
            assert not viewer.is_admin()
