"""Tests for umpire delegation rules and assignment logic.

TDD: Write tests first, then implement delegation service.
Includes CRITICAL Tier I constraint tests for back-to-back field continuity.
"""

import pytest
import uuid
from datetime import datetime, date, time


def unique_keyword(prefix='TEST'):
    """Generate unique keyword for override tests."""
    return f'{prefix}_{uuid.uuid4().hex[:6]}'


def unique_short_code(prefix='T'):
    """Generate unique short code for partner tests."""
    return f'{prefix}{uuid.uuid4().hex[:2].upper()}'


class TestDelegationRuleModel:
    """Test UmpireDelegationRule model."""

    def test_create_delegation_rule(self, app, db_session, league_factory):
        """Delegation rule with allocation objects can be created."""
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.models.umpire_partner import UmpirePartner

        # Create a test league
        league = league_factory(f'Rule Test League {uuid.uuid4().hex[:6]}')

        # Get or create partner records for SDL, DIA, DYN
        sdl_partner = UmpirePartner.get_by_code('SDL')
        if not sdl_partner:
            sdl_partner = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl_partner)
        dia_partner = UmpirePartner.get_by_code('DIA')
        if not dia_partner:
            dia_partner = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia_partner)
        dyn_partner = UmpirePartner.get_by_code('DYN')
        if not dyn_partner:
            dyn_partner = UmpirePartner(org_id=1, name='Dynamic', short_code='DYN')
            db_session.add(dyn_partner)
        db_session.flush()

        rule = UmpireDelegationRule(
            org_id=1,
            league_id=league.ID,
            year=None,  # Default for all seasons
            is_spring=None,
            active=True
        )
        db_session.add(rule)
        db_session.flush()  # Get rule.id

        # Add allocations
        sdl_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=sdl_partner.id, percentage=50)
        dia_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dia_partner.id, percentage=25)
        dyn_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dyn_partner.id, percentage=25)
        db_session.add_all([sdl_alloc, dia_alloc, dyn_alloc])
        db_session.commit()

        assert rule.id is not None
        assert rule.total_pct == 100
        assert rule.get_allocation_for_partner(sdl_partner.id) == 50

    @pytest.mark.quick
    def test_percentages_must_sum_to_100(self, app, db_session):
        """validate_percentages() ensures allocations sum to 100."""
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.models.umpire_partner import UmpirePartner

        # Get or create partners
        sdl_partner = UmpirePartner.get_by_code('SDL')
        if not sdl_partner:
            sdl_partner = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl_partner)
        dia_partner = UmpirePartner.get_by_code('DIA')
        if not dia_partner:
            dia_partner = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia_partner)
        dyn_partner = UmpirePartner.get_by_code('DYN')
        if not dyn_partner:
            dyn_partner = UmpirePartner(org_id=1, name='Dynamic', short_code='DYN')
            db_session.add(dyn_partner)
        db_session.flush()

        rule = UmpireDelegationRule(org_id=1, league_id=1)
        db_session.add(rule)
        db_session.flush()

        # Add allocations that sum to 100
        sdl_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=sdl_partner.id, percentage=50)
        dia_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dia_partner.id, percentage=25)
        dyn_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dyn_partner.id, percentage=25)
        rule.allocations = [sdl_alloc, dia_alloc, dyn_alloc]

        assert rule.validate_percentages() is True

        # Modify to exceed 100
        dyn_alloc.percentage = 30
        assert rule.validate_percentages() is False

    def test_get_for_league_with_season_fallback(self, app, db_session, league_factory):
        """get_for_league() falls back to default when no season-specific rule."""
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.models.umpire_partner import UmpirePartner

        league = league_factory(f'Fallback Test League {uuid.uuid4().hex[:6]}')

        # Get or create partner
        sdl_partner = UmpirePartner.get_by_code('SDL')
        if not sdl_partner:
            sdl_partner = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl_partner)
            db_session.flush()

        # Create default rule (no season)
        default_rule = UmpireDelegationRule(
            org_id=1,
            league_id=league.ID,
            year=None,
            is_spring=None,
            active=True
        )
        db_session.add(default_rule)
        db_session.flush()

        # Add allocation
        sdl_alloc = UmpireDelegationAllocation(rule_id=default_rule.id, partner_id=sdl_partner.id, percentage=100)
        db_session.add(sdl_alloc)
        db_session.commit()

        # Query for 2026 Spring - should fall back to default
        result = UmpireDelegationRule.get_for_league(league.ID, year=2026, is_spring=True)
        assert result is not None
        assert result.get_allocation_for_partner(sdl_partner.id) == 100

    def test_get_for_league_season_specific(self, app, db_session, league_factory):
        """get_for_league() returns season-specific rule when available."""
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.models.umpire_partner import UmpirePartner

        league = league_factory(f'Season Test League {uuid.uuid4().hex[:6]}')

        # Get or create partner
        sdl_partner = UmpirePartner.get_by_code('SDL')
        if not sdl_partner:
            sdl_partner = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl_partner)
            db_session.flush()

        # Create season-specific rule
        season_rule = UmpireDelegationRule(
            org_id=1,
            league_id=league.ID,
            year=2026,
            is_spring=True,
            active=True
        )
        db_session.add(season_rule)
        db_session.flush()

        # Add 100% Academy allocation
        sdl_alloc = UmpireDelegationAllocation(rule_id=season_rule.id, partner_id=sdl_partner.id, percentage=100)
        db_session.add(sdl_alloc)
        db_session.commit()

        result = UmpireDelegationRule.get_for_league(league.ID, year=2026, is_spring=True)
        assert result is not None
        assert result.get_allocation_for_partner(sdl_partner.id) == 100


class TestDelegationOverrideModel:
    """Test UmpireDelegationOverride keyword routing."""

    def test_create_override_keyword(self, app, db_session):
        """Override keyword can be created for routing."""
        from app.models.umpire_delegation import UmpireDelegationOverride

        keyword = unique_keyword('Academy')
        override = UmpireDelegationOverride(
            org_id=1,
            keyword=keyword,
            target_type='academy',
            partner_id=None,
            description='Test override for SDLL youth umpire',
            active=True
        )
        db_session.add(override)
        db_session.commit()

        assert override.id is not None
        assert override.keyword == keyword
        assert override.target_type == 'academy'

    def test_override_to_partner(self, app, db_session):
        """Override can route to specific partner."""
        from app.models.umpire_delegation import UmpireDelegationOverride
        from app.models.umpire_partner import UmpirePartner

        code = unique_short_code('P')
        partner = UmpirePartner(org_id=1, name=f'Test Partner {code}', short_code=code)
        db_session.add(partner)
        db_session.commit()

        keyword = unique_keyword('Partner')
        override = UmpireDelegationOverride(
            org_id=1,
            keyword=keyword,
            target_type='partner',
            partner_id=partner.id,
            description='Test override for partner routing',
            active=True
        )
        db_session.add(override)
        db_session.commit()

        assert override.partner_id == partner.id


class TestLeagueUmpireConfig:
    """Test League model umpire configuration fields."""

    @pytest.mark.quick
    def test_league_umpire_count(self, app, db_session, league_factory):
        """League has umpire_count field (0, 1, or 2)."""
        league = league_factory(f'Count Test {uuid.uuid4().hex[:6]}', umpire_count=2)

        assert hasattr(league, 'umpire_count')
        assert league.umpire_count == 2

    @pytest.mark.quick
    def test_league_umpire_source(self, app, db_session, league_factory):
        """League has umpire_source field (sdll, partner, either)."""
        league = league_factory(f'Source Test {uuid.uuid4().hex[:6]}', umpire_source='partner')

        assert hasattr(league, 'umpire_source')
        assert league.umpire_source == 'partner'

    @pytest.mark.quick
    def test_league_requires_kid_pitch(self, app, db_session, league_factory):
        """League has requires_kid_pitch flag for eligibility filtering."""
        league = league_factory(f'KidPitch Test {uuid.uuid4().hex[:6]}', requires_kid_pitch=True)

        assert hasattr(league, 'requires_kid_pitch')
        assert league.requires_kid_pitch is True


# =============================================================================
# TIER I CONSTRAINT TESTS - CRITICAL
# These tests MUST pass. Back-to-back partner games at same field
# must be assigned to the SAME partner.
# =============================================================================

@pytest.mark.critical
class TestTierIBackToBackConstraint:
    """CRITICAL: Test Tier I back-to-back field continuity constraint.

    When partner games are scheduled back-to-back at the same field,
    they MUST be assigned to the SAME partner. This allows one umpire
    to cover multiple games.
    """

    def test_back_to_back_same_field_same_partner(self, app, db_session, game_factory, field_factory, league_factory):
        """TIER I: Back-to-back games at same field must go to same partner."""
        from app.services.umpire_delegation_service import apply_single_game_delegation
        from app.models.game_umpire import GameUmpire
        from app.models.umpire_partner import UmpirePartner
        from app.models.game import Game

        # Create a league that allows partner umpires
        league = league_factory(f'Tier1 Test League {uuid.uuid4().hex[:6]}', umpire_source='either', umpire_count=1)

        # Create unique partners for this test
        code1 = unique_short_code('D')
        code2 = unique_short_code('Y')
        diamond = UmpirePartner(org_id=1, name=f'Diamond {code1}', short_code=code1)
        dynamic = UmpirePartner(org_id=1, name=f'Dynamic {code2}', short_code=code2)
        db_session.add_all([diamond, dynamic])
        db_session.commit()

        # Create field with unique name
        field = field_factory(f'Test Field B2B {uuid.uuid4().hex[:6]}')

        # Create first game at 10:00 AM assigned to our test partner
        game1 = game_factory(
            game_date=datetime(2026, 4, 15, 10, 0),
            field_id=field.ID,
            league=league.display_name
        )

        # Manually assign game1 to our test partner
        game1_obj = db_session.get(Game, game1.ID)
        game1_obj.umpire_override = code1.lower()
        assignment1 = GameUmpire(
            game_id=game1.ID,
            partner_id=diamond.id,
            status='assigned'
        )
        db_session.add(assignment1)
        db_session.commit()

        # Create second game at 12:00 PM at SAME field (back-to-back)
        game2 = game_factory(
            game_date=datetime(2026, 4, 15, 12, 0),
            field_id=field.ID,
            league=league.display_name
        )

        # Apply delegation to game2
        game2_obj = db_session.get(Game, game2.ID)
        apply_single_game_delegation(game2_obj)
        db_session.commit()

        # CRITICAL: Game2 MUST be assigned to same partner as game1
        # because they are back-to-back at the same field
        assert game2_obj.umpire_override == code1.lower(), \
            f"Tier I violation: Back-to-back game at same field assigned to different partner. Expected {code1.lower()}, got {game2_obj.umpire_override}"

    def test_non_adjacent_games_can_differ(self, app, db_session, game_factory, field_factory):
        """Non-adjacent games (>30 min gap) CAN go to different partners."""
        from app.services.umpire_delegation_service import apply_single_game_delegation
        from app.models.umpire_partner import UmpirePartner
        from app.models.game_umpire import GameUmpire
        from app.models.game import Game

        code1 = unique_short_code('N')
        code2 = unique_short_code('M')
        diamond = UmpirePartner(org_id=1, name=f'Partner {code1}', short_code=code1)
        dynamic = UmpirePartner(org_id=1, name=f'Partner {code2}', short_code=code2)
        db_session.add_all([diamond, dynamic])
        db_session.commit()

        field = field_factory(f'Test Field Gap {uuid.uuid4().hex[:6]}')

        # Game at 10:00 AM assigned to first partner
        game1 = game_factory(
            game_date=datetime(2026, 4, 15, 10, 0),
            field_id=field.ID,
            league='BB Majors'
        )
        game1_obj = db_session.get(Game, game1.ID)
        game1_obj.umpire_override = code1.lower()
        assignment1 = GameUmpire(game_id=game1.ID, partner_id=diamond.id, status='assigned')
        db_session.add(assignment1)
        db_session.commit()

        # Game at 2:00 PM - NOT back-to-back (>30 min gap from ~12:00 end)
        game2 = game_factory(
            game_date=datetime(2026, 4, 15, 14, 0),
            field_id=field.ID,
            league='BB Majors'
        )

        # Apply delegation - this one CAN go to different partner
        game2_obj = db_session.get(Game, game2.ID)
        apply_single_game_delegation(game2_obj)
        db_session.commit()

        # The key is that delegation happened (some source was assigned)
        # It's ALLOWED to differ from game1's partner (unlike back-to-back)
        assert game2_obj.umpire_override is not None, "Game should have been assigned a source"

    def test_different_fields_can_differ(self, app, db_session, game_factory, field_factory):
        """Games at different fields CAN go to different partners."""
        from app.services.umpire_delegation_service import apply_single_game_delegation
        from app.models.umpire_partner import UmpirePartner
        from app.models.game_umpire import GameUmpire
        from app.models.game import Game

        code1 = unique_short_code('F')
        code2 = unique_short_code('G')
        partner1 = UmpirePartner(org_id=1, name=f'Partner {code1}', short_code=code1)
        partner2 = UmpirePartner(org_id=1, name=f'Partner {code2}', short_code=code2)
        db_session.add_all([partner1, partner2])
        db_session.commit()

        field1 = field_factory(f'Field A {uuid.uuid4().hex[:6]}')
        field2 = field_factory(f'Field B {uuid.uuid4().hex[:6]}')

        # Game at Field A, 10:00 AM assigned to first partner
        game1 = game_factory(
            game_date=datetime(2026, 4, 15, 10, 0),
            field_id=field1.ID,
            league='BB Majors'
        )
        game1_obj = db_session.get(Game, game1.ID)
        game1_obj.umpire_override = code1.lower()
        assignment1 = GameUmpire(game_id=game1.ID, partner_id=partner1.id, status='assigned')
        db_session.add(assignment1)
        db_session.commit()

        # Game at Field B, 12:00 PM - DIFFERENT field
        game2 = game_factory(
            game_date=datetime(2026, 4, 15, 12, 0),
            field_id=field2.ID,
            league='BB Majors'
        )

        game2_obj = db_session.get(Game, game2.ID)
        apply_single_game_delegation(game2_obj)
        db_session.commit()

        # The key is that delegation happened - it CAN differ since different fields
        assert game2_obj.umpire_override is not None, "Game should have been assigned a source"


@pytest.mark.critical
class TestBatchDelegationTierI:
    """CRITICAL: Test batch delegation respects Tier I constraints."""

    def test_batch_groups_field_sequences(self, app, db_session, game_factory, field_factory):
        """Batch delegation groups same-field sequences to same partner."""
        from app.services.umpire_delegation_service import delegate_games_for_season
        from app.models.umpire_partner import UmpirePartner
        from app.models.game import Game
        from app.models.league import League

        # Ensure we have partners (use existing or create)
        diamond = UmpirePartner.get_by_code('DIA') or UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
        dynamic = UmpirePartner.get_by_code('DYN') or UmpirePartner(org_id=1, name='Dynamic', short_code='DYN')
        if not diamond.id:
            db_session.add(diamond)
        if not dynamic.id:
            db_session.add(dynamic)
        db_session.commit()

        field = field_factory(f'Batch Test Field {uuid.uuid4().hex[:6]}')

        # Get a league that uses partner umpires
        league = League.query.filter_by(active=1).first()
        league_name = league.display_name if league else 'BB Majors'

        # Create 3 back-to-back games at same field
        games = []
        for hour in [10, 12, 14]:
            game = game_factory(
                game_date=datetime(2026, 4, 15, hour, 0),
                field_id=field.ID,
                league=league_name,
                year=2026,
                is_spring=1
            )
            games.append(game)

        # Run batch delegation
        delegate_games_for_season(2026, True)
        db_session.commit()

        # All 3 games must be same partner (or all academy/unassigned)
        sources = set()
        for game in games:
            game_obj = db_session.get(Game, game.ID)
            if game_obj.umpire_override:
                sources.add(game_obj.umpire_override)

        # If any games were assigned to partners, they should all be same partner
        # (filtering out 'academy' as that's not a partner)
        partner_sources = {s for s in sources if s not in ['academy', None]}
        assert len(partner_sources) <= 1, \
            f"Tier I violation: Field sequence split across partners: {partner_sources}"


class TestDelegationAllocation:
    """Test percentage-based allocation."""

    def test_allocation_respects_percentages(self, app, db_session, game_factory, field_factory, league_factory):
        """Delegation allocates games approximately matching target percentages."""
        from app.services.umpire_delegation_service import delegate_games_for_season
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.models.umpire_partner import UmpirePartner
        from app.models.game import Game

        # This test verifies that over many games, allocation roughly matches rules
        # Exact matching isn't expected due to constraints

        # Use existing partners or create
        diamond = UmpirePartner.get_by_code('DIA') or UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
        dynamic = UmpirePartner.get_by_code('DYN') or UmpirePartner(org_id=1, name='Dynamic', short_code='DYN')
        if not diamond.id:
            db_session.add(diamond)
        if not dynamic.id:
            db_session.add(dynamic)
        db_session.flush()

        # Create a league that uses partner umpires
        league = league_factory(f'Alloc Test League {uuid.uuid4().hex[:6]}', umpire_source='either')

        # Set 50/50 split using allocations
        rule = UmpireDelegationRule(
            org_id=1,
            league_id=league.ID,
            active=True
        )
        db_session.add(rule)
        db_session.flush()

        # Add 50/50 split allocations for Diamond and Dynamic
        dia_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=diamond.id, percentage=50)
        dyn_alloc = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dynamic.id, percentage=50)
        db_session.add_all([dia_alloc, dyn_alloc])
        db_session.commit()

        # Create 10 games at different DATES (no back-to-back constraint)
        # Use different fields to avoid field continuity constraints
        games = []
        for day in range(10):
            field = field_factory(f'Alloc Field {day} {uuid.uuid4().hex[:4]}')
            game = game_factory(
                game_date=datetime(2026, 4, day + 1, 10, 0),
                field_id=field.ID,
                league=league.display_name,
                year=2026,
                is_spring=1
            )
            games.append(game)

        delegate_games_for_season(2026, True)
        db_session.commit()

        # Count allocations
        diamond_count = 0
        dynamic_count = 0
        for game in games:
            game_obj = db_session.get(Game, game.ID)
            if game_obj.umpire_override == 'dia' or game_obj.umpire_override == 'diamond':
                diamond_count += 1
            elif game_obj.umpire_override == 'dyn' or game_obj.umpire_override == 'dynamic':
                dynamic_count += 1

        # Should be roughly 50/50 (allow some variance)
        total = diamond_count + dynamic_count
        if total > 0:
            diamond_pct = (diamond_count / total) * 100
            # Allow 30% variance from target (testing is approximate)
            assert 20 <= diamond_pct <= 80, \
                f"Allocation too skewed: Diamond {diamond_pct}%"


class TestOverrideKeywordRouting:
    """Test keyword-based override routing."""

    def test_keyword_routes_to_academy(self, app, db_session, game_factory):
        """Game with override keyword in notes routes to Academy."""
        from app.services.umpire_delegation_service import check_override_keywords
        from app.models.umpire_delegation import UmpireDelegationOverride
        from app.models.game import Game

        keyword = unique_keyword('YouthUmp')
        override = UmpireDelegationOverride(
            org_id=1,
            keyword=keyword,
            target_type='academy',
            active=True
        )
        db_session.add(override)
        db_session.commit()

        game = game_factory()
        game_obj = db_session.get(Game, game.ID)
        game_obj.umpire_override = keyword  # Simulating notes field

        result = check_override_keywords(game_obj)
        assert result is not None
        assert result.target_type == 'academy'
