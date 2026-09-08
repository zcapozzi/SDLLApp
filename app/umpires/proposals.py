"""Delegation proposal workflow routes.

Handles:
- Listing delegation proposals
- Generating new proposals
- Reviewing proposals (with game reassignment)
- Accepting/rejecting proposals
- API for updating game assignments
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from collections import defaultdict

from app.extensions import db
from app.models.umpire_partner import UmpirePartner
from app.models.umpire_delegation import UmpireDelegationRule
from app.models.league import League
from app.models.game import Game

from . import umpires_bp, umpire_coordinator_required, logger


@umpires_bp.route('/delegation/proposals')
@umpires_bp.route('/delegation/proposals/<int:year>/<int:is_spring>')
@login_required
@umpire_coordinator_required
def delegation_proposals(year=None, is_spring=None):
    """List delegation proposals for a season."""
    from app.models.delegation_proposal import DelegationProposal
    from app.services.delegation_proposal_service import get_undelegated_games

    if year is None:
        year = datetime.now().year
    if is_spring is None:
        is_spring = 1 if datetime.now().month < 7 else 0

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get all proposals for this season
    proposals = DelegationProposal.get_for_season(year, is_spring)

    # Get undelegated games count
    undelegated_games = get_undelegated_games(year, is_spring)
    undelegated_count = len(undelegated_games)

    # Check if there's a pending proposal
    pending_proposal = DelegationProposal.get_pending_for_season(year, is_spring)

    return render_template(
        'umpires/delegation_proposals.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        proposals=proposals,
        undelegated_count=undelegated_count,
        pending_proposal=pending_proposal
    )


@umpires_bp.route('/delegation/proposals/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_delegation_proposal():
    """Generate a new delegation proposal."""
    from app.services.delegation_proposal_service import generate_proposal

    year = int(request.form.get('year', datetime.now().year))
    is_spring = int(request.form.get('is_spring', 0))

    proposal, message = generate_proposal(year, is_spring, created_by=current_user.ID)

    if proposal:
        flash(f'Generated proposal with {proposal.game_count} games', 'success')
        return redirect(url_for('umpires.delegation_proposal_review', id=proposal.id))
    else:
        flash(message, 'error')
        return redirect(url_for('umpires.delegation_proposals', year=year, is_spring=is_spring))


@umpires_bp.route('/delegation/proposals/<int:id>')
@login_required
@umpire_coordinator_required
def delegation_proposal_review(id):
    """Review a delegation proposal with ability to modify assignments."""
    from app.models.delegation_proposal import DelegationProposal
    from app.services.delegation_proposal_service import validate_tier1, validate_tier2

    proposal = DelegationProposal.query.get_or_404(id)
    season_name = f'{"Spring" if proposal.is_spring else "Fall"} {proposal.year}'

    # Get active partners for reassignment dropdown
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()
    partner_lookup = {p.id: p for p in partners}

    # Group games by partner
    games_by_partner = proposal.get_games_by_partner()

    # Get sequences for Tier I display
    sequences = proposal.get_sequences()

    # Re-validate to show current status
    tier1_valid, tier1_violations = validate_tier1(proposal)
    tier2_valid, tier2_violations = validate_tier2(proposal)

    # Build allocation data for dynamic preview
    # 1. Get all leagues in this proposal
    leagues_in_proposal = set()
    for pg in proposal.games:
        if pg.game and pg.game.league:
            leagues_in_proposal.add(pg.game.league)

    # 2. Get current season allocation stats (existing delegated games)
    # This counts ALL games with umpire_override set (not in this proposal)
    current_stats = defaultdict(lambda: defaultdict(int))  # {league: {partner_code: count}}
    existing_games = Game.query.filter(
        Game.year == proposal.year,
        Game.is_spring == proposal.is_spring,
        Game.active == 1,
        Game.game_type.in_(['regular', 'playoff', 'scrimmage']),
        Game.umpire_override.isnot(None),
        Game.umpire_override != ''
    ).all()

    for game in existing_games:
        if game.league:
            code = game.umpire_override.lower()
            current_stats[game.league][code] += 1

    # 3. Get delegation rules for each league
    allocation_rules = {}  # {league: {partner_code: target_pct}}
    for league_name in leagues_in_proposal:
        league_obj = League.get_by_name(league_name)
        if league_obj:
            rule = UmpireDelegationRule.get_for_league(league_obj.ID, proposal.year, proposal.is_spring)
            if rule and rule.allocations:
                allocation_rules[league_name] = {
                    alloc.partner.short_code.lower(): alloc.percentage
                    for alloc in rule.allocations if alloc.percentage > 0
                }

    # 4. Build proposal counts by league/partner (current assignments in proposal)
    proposal_counts = defaultdict(lambda: defaultdict(int))  # {league: {partner_code: count}}
    for pg in proposal.games:
        if pg.game and pg.game.league and pg.assigned_partner:
            code = pg.assigned_partner.short_code.lower()
            proposal_counts[pg.game.league][code] += 1

    # Convert to regular dicts for JSON serialization
    current_stats = {k: dict(v) for k, v in current_stats.items()}
    proposal_counts = {k: dict(v) for k, v in proposal_counts.items()}

    # Build partner info for JS
    partners_json = [{'id': p.id, 'code': p.short_code.lower(), 'name': p.name} for p in partners]

    return render_template(
        'umpires/delegation_proposal_review.html',
        proposal=proposal,
        season_name=season_name,
        partners=partners,
        partners_json=partners_json,
        games_by_partner=games_by_partner,
        sequences=sequences,
        tier1_valid=tier1_valid,
        tier1_violations=tier1_violations,
        tier2_valid=tier2_valid,
        tier2_violations=tier2_violations,
        current_stats=current_stats,
        proposal_counts=proposal_counts,
        allocation_rules=allocation_rules,
        leagues_in_proposal=sorted(leagues_in_proposal)
    )


@umpires_bp.route('/delegation/proposals/<int:id>/accept', methods=['POST'])
@login_required
@umpire_coordinator_required
def accept_delegation_proposal(id):
    """Accept a delegation proposal and apply all assignments."""
    from app.services.delegation_proposal_service import accept_proposal

    success, message, notifications = accept_proposal(id, user_id=current_user.ID)

    if success:
        flash(f'Proposal accepted. {message}', 'success')
        # Could trigger email notifications here if notifications returned
        return redirect(url_for('umpires.delegation_proposals'))
    else:
        flash(f'Failed to accept proposal: {message}', 'error')
        return redirect(url_for('umpires.delegation_proposal_review', id=id))


@umpires_bp.route('/delegation/proposals/<int:id>/reject', methods=['POST'])
@login_required
@umpire_coordinator_required
def reject_delegation_proposal(id):
    """Reject a delegation proposal."""
    from app.services.delegation_proposal_service import reject_proposal

    success, message = reject_proposal(id, user_id=current_user.ID)

    if success:
        flash('Proposal rejected', 'success')
    else:
        flash(f'Failed to reject proposal: {message}', 'error')

    return redirect(url_for('umpires.delegation_proposals'))


@umpires_bp.route('/api/delegation-proposals/<int:id>/update-game', methods=['POST'])
@login_required
@umpire_coordinator_required
def update_proposal_game_assignment(id):
    """Update a game's partner assignment in a proposal.

    If the game is part of a back-to-back sequence, all games in the
    sequence will be updated to maintain Tier I compliance.

    Special case: partner_id=0 means "No Umpire" - sets umpire_count_override=0
    and removes the game from the proposal.
    """
    from app.services.delegation_proposal_service import update_game_assignment, mark_game_no_umpire

    data = request.get_json()
    game_id = data.get('game_id')
    new_partner_id = data.get('partner_id')

    if not game_id:
        return jsonify({'success': False, 'error': 'Missing game_id'}), 400

    if new_partner_id is None:
        return jsonify({'success': False, 'error': 'Missing partner_id'}), 400

    # Handle "No Umpire" case (partner_id = 0)
    if new_partner_id == 0:
        success, message, removed_games = mark_game_no_umpire(id, game_id)
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'removed_games': removed_games,
                'action': 'removed'
            })
        else:
            return jsonify({'success': False, 'error': message}), 400

    # Normal partner assignment
    success, message, updated_games = update_game_assignment(id, game_id, new_partner_id)

    if success:
        return jsonify({
            'success': True,
            'message': message,
            'updated_games': updated_games
        })
    else:
        return jsonify({'success': False, 'error': message}), 400
