"""Tests for UmpireProfile model and umpire user workflow.

TDD: Write tests first, then implement models to make them pass.
"""

import pytest
import uuid
from datetime import date, datetime


def unique_email(prefix='test'):
    """Generate a unique email for tests."""
    return f'{prefix}_{uuid.uuid4().hex[:8]}@test.com'


class TestUmpireProfileModel:
    """Test UmpireProfile model behavior."""

    @pytest.mark.quick
    def test_umpire_profile_created_with_user(self, app, db_session):
        """UmpireProfile requires a linked User account."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile

        # Create user with umpire role
        user = User.create_user(
            email=unique_email('umpire1'),
            password='testpass123',
            name='Test Umpire',
            role='umpire'
        )

        # Create umpire profile linked to user
        profile = UmpireProfile(
            user_id=user.ID,
            is_kid_pitch_eligible=True,
            status='active'
        )
        db_session.add(profile)
        db_session.commit()

        # Verify relationship
        assert profile.user_id == user.ID
        assert profile.user.name == 'Test Umpire'
        assert user.umpire_profile is not None
        assert user.umpire_profile.id == profile.id

    @pytest.mark.quick
    def test_umpire_age_calculation(self, app, db_session):
        """UmpireProfile.age property calculates age from birth_date."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile

        user = User.create_user(
            email=unique_email('umpire_age'),
            password='testpass123',
            name='Young Umpire',
            role='umpire'
        )

        # Set birth date to make umpire 14 years old
        today = date.today()
        birth_date = date(today.year - 14, today.month, today.day)

        profile = UmpireProfile(
            user_id=user.ID,
            birth_date=birth_date
        )
        db_session.add(profile)
        db_session.commit()

        assert profile.age == 14

    @pytest.mark.quick
    def test_umpire_age_none_when_no_birthdate(self, app, db_session):
        """UmpireProfile.age returns None when birth_date not set."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile

        user = User.create_user(
            email=unique_email('umpire_noage'),
            password='testpass123',
            name='No Age Umpire',
            role='umpire'
        )

        profile = UmpireProfile(user_id=user.ID)
        db_session.add(profile)
        db_session.commit()

        assert profile.age is None

    @pytest.mark.quick
    def test_umpire_full_name_from_user(self, app, db_session):
        """UmpireProfile.full_name returns the linked user's name."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile

        user = User.create_user(
            email=unique_email('umpire_name'),
            password='testpass123',
            name='John Umpire',
            role='umpire'
        )

        profile = UmpireProfile(user_id=user.ID)
        db_session.add(profile)
        db_session.commit()

        assert profile.full_name == 'John Umpire'


class TestUserUmpireRole:
    """Test User model umpire role helpers."""

    @pytest.mark.quick
    def test_is_umpire_role(self, app, db_session):
        """User.is_umpire() returns True for umpire role."""
        from app.models.user import User

        user = User.create_user(
            email=unique_email('ump_role'),
            password='testpass123',
            role='umpire'
        )

        assert user.is_umpire() is True
        assert user.role == 'umpire'

    @pytest.mark.quick
    def test_has_umpire_profile_without_profile(self, app, db_session):
        """User.has_umpire_profile() returns False when no profile exists."""
        from app.models.user import User

        user = User.create_user(
            email=unique_email('no_profile'),
            password='testpass123',
            role='umpire'
        )

        # User has umpire role but no profile yet
        assert user.has_umpire_profile() is False

    @pytest.mark.quick
    def test_has_umpire_profile_with_profile(self, app, db_session):
        """User.has_umpire_profile() returns True when profile exists."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile

        user = User.create_user(
            email=unique_email('with_profile'),
            password='testpass123',
            role='umpire'
        )

        profile = UmpireProfile(user_id=user.ID)
        db_session.add(profile)
        db_session.commit()

        # Refresh user to load relationship
        db_session.refresh(user)

        assert user.has_umpire_profile() is True

    @pytest.mark.quick
    def test_umpire_role_in_roles_list(self, app):
        """'umpire' role is in the valid ROLES list."""
        from app.models.user import User

        assert 'umpire' in User.ROLES

    @pytest.mark.quick
    def test_new_roles_in_list(self, app):
        """All new roles are in the valid ROLES list."""
        from app.models.user import User

        expected_roles = [
            'admin', 'scheduler', 'umpire_coordinator', 'treasurer',
            'umpire', 'coach', 'parent', 'partner_contact', 'viewer'
        ]
        for role in expected_roles:
            assert role in User.ROLES, f"Role '{role}' should be in User.ROLES"


class TestUserRoleHelpers:
    """Test User model role helper methods."""

    @pytest.mark.quick
    def test_is_treasurer(self, app, db_session):
        """User.is_treasurer() returns True for treasurer role."""
        from app.models.user import User

        user = User.create_user(
            email=unique_email('treasurer'),
            password='testpass123',
            role='treasurer'
        )

        assert user.is_treasurer() is True

    @pytest.mark.quick
    def test_admin_is_treasurer(self, app, db_session):
        """Admin users are also treasurers."""
        from app.models.user import User

        user = User.create_user(
            email=unique_email('admin_treas'),
            password='testpass123',
            role='admin'
        )

        assert user.is_treasurer() is True

    @pytest.mark.quick
    def test_can_process_payments(self, app, db_session):
        """Only admin and treasurer can process payments."""
        from app.models.user import User

        treasurer = User.create_user(
            email=unique_email('pay_treas'),
            password='testpass123',
            role='treasurer'
        )
        assert treasurer.can_process_payments() is True

        admin = User.create_user(
            email=unique_email('pay_admin'),
            password='testpass123',
            role='admin'
        )
        assert admin.can_process_payments() is True

    @pytest.mark.quick
    def test_umpire_cannot_process_payments(self, app, db_session):
        """Umpires cannot process payments."""
        from app.models.user import User

        user = User.create_user(
            email=unique_email('ump_nopay'),
            password='testpass123',
            role='umpire'
        )

        assert user.can_process_payments() is False

    @pytest.mark.quick
    def test_can_manage_umpires(self, app, db_session):
        """Admin and umpire_coordinator can manage umpires."""
        from app.models.user import User

        coordinator = User.create_user(
            email=unique_email('coord'),
            password='testpass123',
            role='umpire_coordinator'
        )
        assert coordinator.can_manage_umpires() is True

        admin = User.create_user(
            email=unique_email('admin_ump'),
            password='testpass123',
            role='admin'
        )
        assert admin.can_manage_umpires() is True


class TestUmpirePartnerModel:
    """Test UmpirePartner model (Dynamic, Diamond, etc.)."""

    def test_create_umpire_partner(self, app, db_session):
        """UmpirePartner can be created."""
        from app.models.umpire_partner import UmpirePartner

        # Use unique short code
        code = f'D{uuid.uuid4().hex[:2].upper()}'
        partner = UmpirePartner(
            org_id=1,
            name=f'Diamond Umpires {code}',
            short_code=code,
            notification_preference='weekly',
            active=True
        )
        db_session.add(partner)
        db_session.commit()

        assert partner.id is not None
        assert partner.name == f'Diamond Umpires {code}'
        assert partner.short_code == code
        assert partner.notification_preference == 'weekly'

    def test_partner_short_codes(self, app, db_session):
        """Partners have unique short codes for quick reference."""
        from app.models.umpire_partner import UmpirePartner

        code1 = f'X{uuid.uuid4().hex[:2].upper()}'
        code2 = f'Y{uuid.uuid4().hex[:2].upper()}'

        diamond = UmpirePartner(org_id=1, name=f'Diamond {code1}', short_code=code1)
        dynamic = UmpirePartner(org_id=1, name=f'Dynamic {code2}', short_code=code2)

        db_session.add_all([diamond, dynamic])
        db_session.commit()

        assert diamond.short_code == code1
        assert dynamic.short_code == code2


class TestGameUmpireModel:
    """Test GameUmpire assignment model."""

    def test_assign_sdll_umpire_to_game(self, app, db_session, game_factory):
        """SDLL umpire can be assigned to a game via profile."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile
        from app.models.game_umpire import GameUmpire

        # Create umpire with profile
        user = User.create_user(
            email=unique_email('game_ump'),
            password='testpass123',
            role='umpire'
        )
        profile = UmpireProfile(user_id=user.ID)
        db_session.add(profile)
        db_session.commit()

        # Create game
        game = game_factory()

        # Assign umpire to game
        assignment = GameUmpire(
            game_id=game.ID,
            umpire_profile_id=profile.id,
            role='plate',
            status='assigned'
        )
        db_session.add(assignment)
        db_session.commit()

        assert assignment.id is not None
        assert assignment.umpire_profile_id == profile.id
        assert assignment.partner_id is None  # Not a partner assignment

    def test_assign_partner_to_game(self, app, db_session, game_factory):
        """Partner company can be assigned to a game."""
        from app.models.umpire_partner import UmpirePartner
        from app.models.game_umpire import GameUmpire

        code = f'P{uuid.uuid4().hex[:2].upper()}'
        partner = UmpirePartner(org_id=1, name=f'Partner {code}', short_code=code)
        db_session.add(partner)
        db_session.commit()

        game = game_factory()

        assignment = GameUmpire(
            game_id=game.ID,
            partner_id=partner.id,
            role='umpire',
            status='assigned'
        )
        db_session.add(assignment)
        db_session.commit()

        assert assignment.partner_id == partner.id
        assert assignment.umpire_profile_id is None  # Not an SDLL umpire

    def test_cancel_assignment(self, app, db_session, game_factory):
        """Cancelling assignment sets status and marks for notification."""
        from app.models.user import User
        from app.models.umpire_profile import UmpireProfile
        from app.models.game_umpire import GameUmpire

        user = User.create_user(
            email=unique_email('cancel_ump'),
            password='testpass123',
            role='umpire'
        )
        profile = UmpireProfile(user_id=user.ID)
        db_session.add(profile)
        db_session.commit()

        game = game_factory()
        assignment = GameUmpire(
            game_id=game.ID,
            umpire_profile_id=profile.id,
            status='assigned'
        )
        db_session.add(assignment)
        db_session.commit()

        # Cancel the assignment
        assignment.cancel(user.ID)
        db_session.commit()

        assert assignment.status == 'cancelled'
        assert assignment.cancelled_at is not None
        assert assignment.was_previously_cancelled is True
