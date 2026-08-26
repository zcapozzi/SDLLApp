"""Delegation Proposal Service - generate and manage umpire delegation proposals.

This service handles the workflow for reviewing and accepting umpire delegations:
1. Identify games that need delegation (no umpire_override set)
2. Detect back-to-back sequences (Tier I constraint)
3. Generate optimal allocation suggestions based on rules
4. Validate Tier I (back-to-back) and Tier II (10% deviation) rules
5. Accept proposals and update games
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict

from app.extensions import db
from app.models.game import Game
from app.models.delegation_proposal import DelegationProposal, DelegationProposalGame
from app.models.umpire_partner import UmpirePartner
from app.models.umpire_delegation import UmpireDelegationRule
from app.models.league import League
from app.services.umpire_delegation_service import get_allocation_stats


def get_undelegated_games(year, is_spring):
    """Get games that need delegation (no umpire_override set).

    Filters:
    - Active games for the season
    - Game types that need umpires (regular, playoff, scrimmage - not practice)
    - No umpire_override already set
    - Not explicitly set to 0 umpires via override
    - At SDLL-owned fields

    Args:
        year: Season year
        is_spring: Whether spring season (1) or fall (0)

    Returns:
        List of Game objects needing delegation
    """
    from app.models.field import Field

    # Base query with field join for ownership check
    query = Game.query.join(
        Field, Game.field_id == Field.ID
    ).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage']),
        (Game.umpire_override.is_(None)) | (Game.umpire_override == ''),
        # Exclude games explicitly set to 0 umpires
        (Game.umpire_count_override.is_(None)) | (Game.umpire_count_override > 0),
        # Only SDLL-owned fields
        Field.is_owned == 1
    ).order_by(Game.game_date, Game.location)

    games = query.all()

    # Filter out games where the league requires 0 umpires
    # (unless game has explicit override > 0)
    result = []
    for game in games:
        if game.umpire_count_override is not None and game.umpire_count_override > 0:
            # Explicit override > 0, include it
            result.append(game)
        elif game.umpire_count_override is None:
            # Check league's umpire count via the game's umpire_count property
            # which handles the league lookup internally
            if game.umpire_count and game.umpire_count > 0:
                result.append(game)

    return result


def identify_back_to_back_sequences(games):
    """Group games into back-to-back sequences at same field.

    Two games are back-to-back if:
    1. Same field (location)
    2. Second game starts within 30 min of first game's expected end

    Args:
        games: List of Game objects

    Returns:
        dict: {sequence_id: [game_id, ...]} for sequences with 2+ games
        Also returns set of all game IDs that are in sequences
    """
    if not games:
        return {}, set()

    # Sort by field, then datetime
    sorted_games = sorted(games, key=lambda g: (g.location or '', g.game_date or datetime.min))

    sequences = {}
    game_to_sequence = {}
    sequence_id = 0

    prev_game = None
    current_seq_games = []

    for game in sorted_games:
        if prev_game and _is_back_to_back(prev_game, game):
            # Continue current sequence
            if prev_game.ID not in game_to_sequence:
                current_seq_games.append(prev_game.ID)
            current_seq_games.append(game.ID)
        else:
            # End previous sequence if it had 2+ games
            if len(current_seq_games) >= 2:
                sequences[sequence_id] = current_seq_games
                for gid in current_seq_games:
                    game_to_sequence[gid] = sequence_id
                sequence_id += 1
            current_seq_games = []

        prev_game = game

    # Don't forget last sequence
    if len(current_seq_games) >= 2:
        sequences[sequence_id] = current_seq_games
        for gid in current_seq_games:
            game_to_sequence[gid] = sequence_id

    return sequences, set(game_to_sequence.keys())


def _is_back_to_back(game1, game2):
    """Check if two games are back-to-back at the same field.

    Args:
        game1: First game (earlier)
        game2: Second game (later)

    Returns:
        bool: True if games are back-to-back
    """
    # Must be same field
    if not game1.location or not game2.location:
        return False
    if game1.location.strip().lower() != game2.location.strip().lower():
        return False

    # Must be same day
    if not game1.game_date or not game2.game_date:
        return False
    if game1.game_date.date() != game2.game_date.date():
        return False

    # Get game1's expected end time
    duration = game1.duration_minutes or 120  # Default 2 hours
    game1_end = game1.game_date + timedelta(minutes=duration)

    # Game2 must start within 30 minutes of game1's end
    gap = (game2.game_date - game1_end).total_seconds() / 60
    return -15 <= gap <= 30  # Allow some overlap or up to 30 min gap


def generate_proposal(year, is_spring, created_by=None):
    """Generate a new delegation proposal for undelegated games.

    Args:
        year: Season year
        is_spring: Whether spring season
        created_by: User ID who generated the proposal

    Returns:
        Tuple of (DelegationProposal, message) or (None, error_message)
    """
    # Get undelegated games
    games = get_undelegated_games(year, is_spring)
    if not games:
        return None, 'No undelegated games found'

    # Identify back-to-back sequences
    sequences, games_in_sequences = identify_back_to_back_sequences(games)

    # Get active partners
    partners = UmpirePartner.get_active()
    partner_by_code = {p.short_code.lower(): p for p in partners}

    # Get current allocation stats by league
    leagues_in_games = set(g.league for g in games if g.league)
    stats_by_league = {}
    rules_by_league = {}
    for league_name in leagues_in_games:
        league = League.get_by_name(league_name)
        if league:
            stats_by_league[league_name] = get_allocation_stats(league_name, year, is_spring)
            rules_by_league[league_name] = UmpireDelegationRule.get_for_league(league.ID, year, is_spring)

    # Create proposal
    proposal = DelegationProposal(
        year=year,
        is_spring=is_spring,
        created_by=created_by,
        game_count=len(games),
        status='pending'
    )
    db.session.add(proposal)
    db.session.flush()  # Get proposal.id

    # Track assignments for allocation balancing
    proposal_counts = defaultdict(lambda: defaultdict(int))  # {league: {partner_code: count}}

    # First pass: assign back-to-back sequences
    # All games in a sequence must go to the same partner
    sequence_partners = {}
    for seq_id, game_ids in sequences.items():
        # Find best partner for this sequence based on allocation needs
        seq_games = [g for g in games if g.ID in game_ids]
        league_name = seq_games[0].league if seq_games else None
        partner = _find_best_partner_for_games(
            seq_games, rules_by_league.get(league_name),
            stats_by_league.get(league_name, {}), proposal_counts, partners
        )
        sequence_partners[seq_id] = partner

        # Create proposal games for sequence
        for game in seq_games:
            pg = DelegationProposalGame(
                proposal_id=proposal.id,
                game_id=game.ID,
                suggested_partner_id=partner.id,
                is_back_to_back=True,
                sequence_id=seq_id
            )
            db.session.add(pg)
            proposal_counts[game.league][partner.short_code.lower()] += 1

    # Second pass: assign non-sequence games
    for game in games:
        if game.ID in games_in_sequences:
            continue  # Already assigned

        rule = rules_by_league.get(game.league)
        stats = stats_by_league.get(game.league, {})
        partner = _find_best_partner_for_games(
            [game], rule, stats, proposal_counts, partners
        )

        pg = DelegationProposalGame(
            proposal_id=proposal.id,
            game_id=game.ID,
            suggested_partner_id=partner.id,
            is_back_to_back=False,
            sequence_id=None
        )
        db.session.add(pg)
        proposal_counts[game.league][partner.short_code.lower()] += 1

    # Validate and store violations
    _, tier1_violations = validate_tier1(proposal)
    _, tier2_violations = validate_tier2(proposal, rules_by_league, stats_by_league, proposal_counts)
    proposal.tier1_violations = len(tier1_violations)
    proposal.tier2_violations = len(tier2_violations)

    # Build summary
    summary = {
        'by_partner': {},
        'by_league': {},
        'tier1_violations': tier1_violations,
        'tier2_violations': tier2_violations
    }
    for partner in partners:
        code = partner.short_code.lower()
        count = sum(proposal_counts[league].get(code, 0) for league in proposal_counts)
        summary['by_partner'][code] = {
            'count': count,
            'name': partner.name
        }
    for league, counts in proposal_counts.items():
        summary['by_league'][league] = dict(counts)
    proposal.summary = summary

    db.session.commit()
    return proposal, f'Generated proposal with {len(games)} games'


def _find_best_partner_for_games(games, rule, current_stats, proposal_counts, partners):
    """Find the best partner for a set of games based on allocation targets.

    Args:
        games: List of Game objects to assign
        rule: UmpireDelegationRule for the league (or None)
        current_stats: Current allocation stats for the league
        proposal_counts: Counts already assigned in this proposal
        partners: List of active UmpirePartner objects

    Returns:
        UmpirePartner to assign
    """
    if not rule or not rule.allocations:
        # No rules - default to SDL (Academy)
        for p in partners:
            if p.short_code == 'SDL':
                return p
        return partners[0] if partners else None

    league_name = games[0].league if games else None

    # Calculate current + proposal totals
    total_existing = current_stats.get('total', 0)
    total_in_proposal = sum(proposal_counts.get(league_name, {}).values())
    total = total_existing + total_in_proposal + len(games)

    # Find partner with largest deficit from target
    best_partner = None
    best_deficit = float('-inf')

    for alloc in rule.allocations:
        if alloc.percentage <= 0:
            continue

        partner = alloc.partner
        code = partner.short_code.lower()

        # Current count from existing games
        existing_count = current_stats.get(code, {}).get('count', 0) if isinstance(current_stats.get(code), dict) else 0
        # Count from this proposal so far
        proposal_count = proposal_counts.get(league_name, {}).get(code, 0)
        # Total count after assigning these games
        would_have = existing_count + proposal_count + len(games)

        # Target percentage
        target_pct = alloc.percentage
        # Actual percentage if assigned to this partner
        actual_pct = (would_have / total * 100) if total > 0 else 0

        # Deficit = how far below target we are
        deficit = target_pct - actual_pct

        if deficit > best_deficit:
            best_deficit = deficit
            best_partner = partner

    return best_partner or partners[0]


def validate_tier1(proposal):
    """Validate Tier I: back-to-back games must use same partner.

    This should never have violations if generate_proposal() works correctly,
    but we check anyway for manual overrides.

    Returns:
        Tuple of (is_valid, violations_list)
    """
    violations = []
    sequences = proposal.get_sequences()

    for seq_id, games in sequences.items():
        partners_in_seq = set()
        for pg in games:
            partners_in_seq.add(pg.assigned_partner_id)

        if len(partners_in_seq) > 1:
            # Get field name from first game in sequence
            field = games[0].game.location if games and games[0].game else 'Unknown'
            violations.append({
                'type': 'tier1_back_to_back',
                'sequence_id': seq_id,
                'games': games,
                'field': field,
                'partners': list(partners_in_seq),
                'message': f'Sequence {seq_id} has games assigned to different partners'
            })

    return len(violations) == 0, violations


def validate_tier2(proposal, rules_by_league=None, stats_by_league=None, proposal_counts=None):
    """Validate Tier II: allocations should not deviate >10% from targets.

    Args:
        proposal: DelegationProposal object
        rules_by_league: Dict of {league_name: UmpireDelegationRule}
        stats_by_league: Dict of {league_name: stats_dict}
        proposal_counts: Dict of {league_name: {partner_code: count}}

    Returns:
        Tuple of (is_valid, violations_list)
    """
    violations = []

    # If not provided, we need to recalculate
    if rules_by_league is None or stats_by_league is None or proposal_counts is None:
        # Group proposal games by league
        proposal_counts = defaultdict(lambda: defaultdict(int))
        leagues_in_proposal = set()
        for pg in proposal.games:
            game = pg.game
            if game and game.league:
                leagues_in_proposal.add(game.league)
                partner = pg.assigned_partner
                if partner:
                    proposal_counts[game.league][partner.short_code.lower()] += 1

        # Get stats and rules
        stats_by_league = {}
        rules_by_league = {}
        for league_name in leagues_in_proposal:
            league = League.get_by_name(league_name)
            if league:
                stats_by_league[league_name] = get_allocation_stats(league_name, proposal.year, proposal.is_spring)
                rules_by_league[league_name] = UmpireDelegationRule.get_for_league(league.ID, proposal.year, proposal.is_spring)

    # Check each league
    for league_name, rule in rules_by_league.items():
        if not rule or not rule.allocations:
            continue

        current_stats = stats_by_league.get(league_name, {})
        league_proposal = proposal_counts.get(league_name, {})

        # Calculate totals
        total_existing = current_stats.get('total', 0)
        total_in_proposal = sum(league_proposal.values())
        total = total_existing + total_in_proposal

        if total == 0:
            continue

        # Check each allocation
        for alloc in rule.allocations:
            if alloc.percentage <= 0:
                continue

            partner = alloc.partner
            code = partner.short_code.lower()

            # Count for this partner
            existing_count = current_stats.get(code, {}).get('count', 0) if isinstance(current_stats.get(code), dict) else 0
            proposal_count = league_proposal.get(code, 0)
            total_count = existing_count + proposal_count

            # Percentages
            target_pct = alloc.percentage
            actual_pct = (total_count / total * 100) if total > 0 else 0
            deviation = abs(actual_pct - target_pct)

            if deviation > 10:
                violations.append({
                    'type': 'tier2_deviation',
                    'league': league_name,
                    'partner': partner.name,
                    'partner_code': code,
                    'target_pct': target_pct,
                    'actual_pct': round(actual_pct, 1),
                    'deviation': round(deviation, 1),
                    'message': f'{league_name}: {partner.name} is {round(deviation, 1)}% off target ({round(actual_pct, 1)}% vs {target_pct}%)'
                })

    return len(violations) == 0, violations


def accept_proposal(proposal_id, user_id):
    """Accept a proposal and update all game umpire_override fields.

    Args:
        proposal_id: ID of proposal to accept
        user_id: ID of user accepting

    Returns:
        (success: bool, message: str, partner_notifications: dict)
    """
    proposal = DelegationProposal.query.get(proposal_id)
    if not proposal:
        return False, 'Proposal not found', {}

    if proposal.status != 'pending':
        return False, f'Proposal is already {proposal.status}', {}

    # Check for Tier I violations - should not accept if any exist
    tier1_valid, tier1_violations = validate_tier1(proposal)
    if not tier1_valid:
        return False, f'Cannot accept: {len(tier1_violations)} Tier I violation(s)', {}

    # Update each game
    partner_notifications = defaultdict(list)  # {partner_id: [game_ids]}

    for pg in proposal.games:
        game = pg.game
        if not game:
            continue

        partner = pg.assigned_partner
        if not partner:
            continue

        # Update game's umpire_override
        game.umpire_override = partner.short_code.lower()

        # Track for notifications (non-SDL partners)
        if partner.short_code != 'SDL':
            partner_notifications[partner.id].append(game.ID)

    # Mark proposal as accepted
    proposal.status = 'accepted'
    proposal.accepted_at = datetime.utcnow()
    proposal.accepted_by = user_id

    db.session.commit()

    return True, f'Accepted: {proposal.game_count} games delegated', dict(partner_notifications)


def update_game_assignment(proposal_id, game_id, new_partner_id):
    """Update a single game's assignment in a proposal.

    Enforces Tier I constraint: if game is in a sequence, all sequence games
    must be updated together.

    Args:
        proposal_id: Proposal ID
        game_id: Game ID to update
        new_partner_id: New partner ID to assign

    Returns:
        (success: bool, message: str, updated_game_ids: list)
    """
    proposal = DelegationProposal.query.get(proposal_id)
    if not proposal or proposal.status != 'pending':
        return False, 'Invalid or non-pending proposal', []

    # Find the proposal game
    pg = DelegationProposalGame.query.filter_by(
        proposal_id=proposal_id,
        game_id=game_id
    ).first()

    if not pg:
        return False, 'Game not found in proposal', []

    updated_ids = []

    # If game is in a sequence, update all games in that sequence
    if pg.sequence_id is not None:
        sequence_games = DelegationProposalGame.query.filter_by(
            proposal_id=proposal_id,
            sequence_id=pg.sequence_id
        ).all()

        for seq_pg in sequence_games:
            seq_pg.final_partner_id = new_partner_id
            updated_ids.append(seq_pg.game_id)
    else:
        pg.final_partner_id = new_partner_id
        updated_ids.append(game_id)

    # Re-validate
    tier1_violations = validate_tier1(proposal)
    tier2_violations = validate_tier2(proposal)
    proposal.tier1_violations = len(tier1_violations)
    proposal.tier2_violations = len(tier2_violations)

    # Update summary
    summary = proposal.summary or {}
    summary['tier1_violations'] = tier1_violations
    summary['tier2_violations'] = tier2_violations
    proposal.summary = summary

    db.session.commit()

    return True, f'Updated {len(updated_ids)} game(s)', updated_ids


def reject_proposal(proposal_id, user_id):
    """Reject a proposal without applying changes.

    Args:
        proposal_id: ID of proposal to reject
        user_id: ID of user rejecting

    Returns:
        (success: bool, message: str)
    """
    proposal = DelegationProposal.query.get(proposal_id)
    if not proposal:
        return False, 'Proposal not found'

    if proposal.status != 'pending':
        return False, f'Proposal is already {proposal.status}'

    proposal.status = 'rejected'
    db.session.commit()

    return True, 'Proposal rejected'
