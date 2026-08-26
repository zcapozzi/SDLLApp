"""Tests for the Delegation Proposal System.

Tests cover:
- Back-to-back sequence detection
- Tier I validation (back-to-back same partner)
- Tier II validation (10% deviation)
- Proposal generation
- Proposal acceptance
"""

import pytest
from datetime import datetime, timedelta
import uuid


class TestBackToBackDetection:
    """Test back-to-back sequence identification."""

    @pytest.mark.quick
    def test_same_field_consecutive_games_are_back_to_back(self):
        """Games at same field within 30 min of each other are back-to-back."""
        from app.services.delegation_proposal_service import _is_back_to_back

        # Create mock games
        class MockGame:
            def __init__(self, location, game_date, duration=120):
                self.location = location
                self.game_date = game_date
                self.duration_minutes = duration

        game1 = MockGame('Field A', datetime(2026, 9, 15, 17, 0))  # 5:00 PM, 2 hour game
        game2 = MockGame('Field A', datetime(2026, 9, 15, 19, 0))  # 7:00 PM (right after)

        assert _is_back_to_back(game1, game2) is True

    @pytest.mark.quick
    def test_different_fields_not_back_to_back(self):
        """Games at different fields are never back-to-back."""
        from app.services.delegation_proposal_service import _is_back_to_back

        class MockGame:
            def __init__(self, location, game_date, duration=120):
                self.location = location
                self.game_date = game_date
                self.duration_minutes = duration

        game1 = MockGame('Field A', datetime(2026, 9, 15, 17, 0))
        game2 = MockGame('Field B', datetime(2026, 9, 15, 19, 0))

        assert _is_back_to_back(game1, game2) is False

    @pytest.mark.quick
    def test_large_gap_not_back_to_back(self):
        """Games with >30 min gap are not back-to-back."""
        from app.services.delegation_proposal_service import _is_back_to_back

        class MockGame:
            def __init__(self, location, game_date, duration=120):
                self.location = location
                self.game_date = game_date
                self.duration_minutes = duration

        game1 = MockGame('Field A', datetime(2026, 9, 15, 17, 0))  # 5:00 PM, 2 hour game
        game2 = MockGame('Field A', datetime(2026, 9, 15, 20, 0))  # 8:00 PM (1 hour gap)

        assert _is_back_to_back(game1, game2) is False

    @pytest.mark.quick
    def test_different_days_not_back_to_back(self):
        """Games on different days are never back-to-back."""
        from app.services.delegation_proposal_service import _is_back_to_back

        class MockGame:
            def __init__(self, location, game_date, duration=120):
                self.location = location
                self.game_date = game_date
                self.duration_minutes = duration

        game1 = MockGame('Field A', datetime(2026, 9, 15, 17, 0))
        game2 = MockGame('Field A', datetime(2026, 9, 16, 17, 0))  # Next day

        assert _is_back_to_back(game1, game2) is False

    @pytest.mark.quick
    def test_identify_sequences(self):
        """identify_back_to_back_sequences groups consecutive games correctly."""
        from app.services.delegation_proposal_service import identify_back_to_back_sequences

        class MockGame:
            def __init__(self, id, location, game_date, duration=120):
                self.ID = id
                self.location = location
                self.game_date = game_date
                self.duration_minutes = duration

        games = [
            MockGame(1, 'Field A', datetime(2026, 9, 15, 17, 0)),  # 5 PM
            MockGame(2, 'Field A', datetime(2026, 9, 15, 19, 0)),  # 7 PM - back-to-back with 1
            MockGame(3, 'Field B', datetime(2026, 9, 15, 17, 0)),  # Different field
            MockGame(4, 'Field A', datetime(2026, 9, 15, 21, 0)),  # 9 PM - back-to-back with 2
        ]

        sequences, games_in_seq = identify_back_to_back_sequences(games)

        # Should have one sequence with games 1, 2, 4 at Field A
        assert len(sequences) == 1
        seq_ids = list(sequences.values())[0]
        assert 1 in seq_ids
        assert 2 in seq_ids
        assert 4 in seq_ids
        assert 3 not in seq_ids


class TestTier1Validation:
    """Test Tier I constraint: back-to-back games must use same partner."""

    def test_sequence_same_partner_passes(self, app, db_session, game_factory, field_factory):
        """Sequence with all games assigned to same partner has no violations."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.services.delegation_proposal_service import validate_tier1

        partner = UmpirePartner.get_by_code('SDL')
        if not partner:
            partner = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(partner)
            db_session.flush()

        field = field_factory('Tier1 Test Field')
        game1 = game_factory(game_date=datetime(2026, 9, 15, 17, 0), location=field.location_title)
        game2 = game_factory(game_date=datetime(2026, 9, 15, 19, 0), location=field.location_title)

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=2)
        db_session.add(proposal)
        db_session.flush()

        pg1 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game1.ID,
            suggested_partner_id=partner.id, is_back_to_back=True, sequence_id=0
        )
        pg2 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game2.ID,
            suggested_partner_id=partner.id, is_back_to_back=True, sequence_id=0
        )
        db_session.add_all([pg1, pg2])
        db_session.commit()

        is_valid, violations = validate_tier1(proposal)
        assert is_valid is True
        assert len(violations) == 0

    def test_sequence_different_partners_fails(self, app, db_session, game_factory, field_factory):
        """Sequence with games assigned to different partners has violations."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.services.delegation_proposal_service import validate_tier1

        sdl = UmpirePartner.get_by_code('SDL')
        dia = UmpirePartner.get_by_code('DIA')
        if not sdl:
            sdl = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl)
        if not dia:
            dia = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia)
        db_session.flush()

        field = field_factory('Tier1 Fail Field')
        game1 = game_factory(game_date=datetime(2026, 9, 15, 17, 0), location=field.location_title)
        game2 = game_factory(game_date=datetime(2026, 9, 15, 19, 0), location=field.location_title)

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=2)
        db_session.add(proposal)
        db_session.flush()

        # Assign to DIFFERENT partners - this is a violation
        pg1 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game1.ID,
            suggested_partner_id=sdl.id, is_back_to_back=True, sequence_id=0
        )
        pg2 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game2.ID,
            suggested_partner_id=dia.id,  # Different partner!
            final_partner_id=dia.id,  # Override
            is_back_to_back=True, sequence_id=0
        )
        db_session.add_all([pg1, pg2])
        db_session.commit()

        is_valid, violations = validate_tier1(proposal)
        assert is_valid is False
        assert len(violations) == 1
        assert violations[0]['type'] == 'tier1_back_to_back'


class TestTier2Validation:
    """Test Tier II constraint: allocations within 10% of targets."""

    def test_within_tolerance_passes(self, app, db_session, league_factory):
        """Allocations within 10% of target have no violations."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.services.delegation_proposal_service import validate_tier2

        # Set up 50/50 rule
        league = league_factory('Tier2 Test League')
        sdl = UmpirePartner.get_by_code('SDL')
        dia = UmpirePartner.get_by_code('DIA')
        if not sdl:
            sdl = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl)
        if not dia:
            dia = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia)
        db_session.flush()

        rule = UmpireDelegationRule(org_id=1, league_id=league.ID, active=True)
        db_session.add(rule)
        db_session.flush()

        alloc1 = UmpireDelegationAllocation(rule_id=rule.id, partner_id=sdl.id, percentage=50)
        alloc2 = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dia.id, percentage=50)
        db_session.add_all([alloc1, alloc2])
        db_session.commit()

        # Create proposal with 55/45 split (within 10% tolerance)
        proposal = DelegationProposal(year=2026, is_spring=0, game_count=0)
        db_session.add(proposal)
        db_session.commit()

        # Mock the stats and counts for 55/45 split
        rules_by_league = {league.display_name: rule}
        stats_by_league = {league.display_name: {'total': 0, 'sdl': {'count': 0, 'pct': 0}, 'dia': {'count': 0, 'pct': 0}}}
        proposal_counts = {league.display_name: {'sdl': 55, 'dia': 45}}

        is_valid, violations = validate_tier2(proposal, rules_by_league, stats_by_league, proposal_counts)
        assert is_valid is True
        assert len(violations) == 0

    def test_exceeds_tolerance_fails(self, app, db_session, league_factory):
        """Allocations exceeding 10% of target have violations."""
        from app.models.delegation_proposal import DelegationProposal
        from app.models.umpire_partner import UmpirePartner
        from app.models.umpire_delegation import UmpireDelegationRule
        from app.models.umpire_delegation_allocation import UmpireDelegationAllocation
        from app.services.delegation_proposal_service import validate_tier2

        league = league_factory('Tier2 Fail League')
        sdl = UmpirePartner.get_by_code('SDL')
        dia = UmpirePartner.get_by_code('DIA')
        if not sdl:
            sdl = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl)
        if not dia:
            dia = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia)
        db_session.flush()

        rule = UmpireDelegationRule(org_id=1, league_id=league.ID, active=True)
        db_session.add(rule)
        db_session.flush()

        alloc1 = UmpireDelegationAllocation(rule_id=rule.id, partner_id=sdl.id, percentage=50)
        alloc2 = UmpireDelegationAllocation(rule_id=rule.id, partner_id=dia.id, percentage=50)
        db_session.add_all([alloc1, alloc2])
        db_session.commit()

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=0)
        db_session.add(proposal)
        db_session.commit()

        # Mock 70/30 split (20% deviation - exceeds 10% tolerance)
        rules_by_league = {league.display_name: rule}
        stats_by_league = {league.display_name: {'total': 0, 'sdl': {'count': 0, 'pct': 0}, 'dia': {'count': 0, 'pct': 0}}}
        proposal_counts = {league.display_name: {'sdl': 70, 'dia': 30}}

        is_valid, violations = validate_tier2(proposal, rules_by_league, stats_by_league, proposal_counts)
        assert is_valid is False
        assert len(violations) >= 1
        assert any(v['type'] == 'tier2_deviation' for v in violations)


class TestProposalAcceptance:
    """Test proposal acceptance workflow."""

    def test_accept_updates_games(self, app, db_session, game_factory, field_factory):
        """Accepting a proposal updates game umpire_override fields."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.models.game import Game
        from app.services.delegation_proposal_service import accept_proposal

        partner = UmpirePartner.get_by_code('DIA')
        if not partner:
            partner = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(partner)
            db_session.flush()

        field = field_factory('Accept Test Field')
        game_data = game_factory(game_date=datetime(2026, 9, 15, 17, 0), location=field.location_title)

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=1, status='pending')
        db_session.add(proposal)
        db_session.flush()

        pg = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game_data.ID,
            suggested_partner_id=partner.id
        )
        db_session.add(pg)
        db_session.commit()

        # Accept
        success, message, notifications = accept_proposal(proposal.id, user_id=1)
        assert success is True

        # Verify proposal status was updated
        db_session.refresh(proposal)
        assert proposal.status == 'accepted'

        # Verify game was updated - use raw SQL to bypass session issues
        with app.app_context():
            game_obj = Game.query.get(game_data.ID)
            assert game_obj is not None, f"Game {game_data.ID} not found"
            assert game_obj.umpire_override == 'dia', f"Expected 'dia' but got '{game_obj.umpire_override}'"

    def test_cannot_accept_with_tier1_violations(self, app, db_session, game_factory, field_factory):
        """Cannot accept a proposal that has Tier I violations."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.services.delegation_proposal_service import accept_proposal

        sdl = UmpirePartner.get_by_code('SDL')
        dia = UmpirePartner.get_by_code('DIA')
        if not sdl:
            sdl = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl)
        if not dia:
            dia = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia)
        db_session.flush()

        field = field_factory('Reject Test Field')
        game1 = game_factory(game_date=datetime(2026, 9, 15, 17, 0), location=field.location_title)
        game2 = game_factory(game_date=datetime(2026, 9, 15, 19, 0), location=field.location_title)

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=2, status='pending')
        db_session.add(proposal)
        db_session.flush()

        # Create Tier I violation: same sequence, different partners
        pg1 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game1.ID,
            suggested_partner_id=sdl.id, is_back_to_back=True, sequence_id=0
        )
        pg2 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game2.ID,
            suggested_partner_id=sdl.id,
            final_partner_id=dia.id,  # Override to different partner
            is_back_to_back=True, sequence_id=0
        )
        db_session.add_all([pg1, pg2])
        db_session.commit()

        # Should fail to accept
        success, message, notifications = accept_proposal(proposal.id, user_id=1)
        assert success is False
        assert 'Tier I' in message


class TestUpdateGameAssignment:
    """Test updating individual game assignments."""

    def test_update_sequence_updates_all(self, app, db_session, game_factory, field_factory):
        """Updating a game in a sequence updates all games in that sequence."""
        from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
        from app.models.umpire_partner import UmpirePartner
        from app.services.delegation_proposal_service import update_game_assignment

        sdl = UmpirePartner.get_by_code('SDL')
        dia = UmpirePartner.get_by_code('DIA')
        if not sdl:
            sdl = UmpirePartner(org_id=1, name='SDLL Academy', short_code='SDL')
            db_session.add(sdl)
        if not dia:
            dia = UmpirePartner(org_id=1, name='Diamond', short_code='DIA')
            db_session.add(dia)
        db_session.flush()

        field = field_factory('Update Seq Field')
        game1 = game_factory(game_date=datetime(2026, 9, 15, 17, 0), location=field.location_title)
        game2 = game_factory(game_date=datetime(2026, 9, 15, 19, 0), location=field.location_title)

        proposal = DelegationProposal(year=2026, is_spring=0, game_count=2, status='pending')
        db_session.add(proposal)
        db_session.flush()

        pg1 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game1.ID,
            suggested_partner_id=sdl.id, is_back_to_back=True, sequence_id=0
        )
        pg2 = DelegationProposalGame(
            proposal_id=proposal.id, game_id=game2.ID,
            suggested_partner_id=sdl.id, is_back_to_back=True, sequence_id=0
        )
        db_session.add_all([pg1, pg2])
        db_session.commit()

        # Update just game1 to Diamond
        success, message, updated_ids = update_game_assignment(proposal.id, game1.ID, dia.id)
        assert success is True
        assert len(updated_ids) == 2  # Both games should be updated

        # Both should now be assigned to Diamond
        db_session.refresh(pg1)
        db_session.refresh(pg2)
        assert pg1.final_partner_id == dia.id
        assert pg2.final_partner_id == dia.id
