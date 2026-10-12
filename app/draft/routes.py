"""Draft routes for managing player drafts."""

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.draft import draft_bp
from app.utils.auth import role_required
from app.models.org_season import OrgSeason
from app.models.league import League
from app.models.draft import DraftSession, DraftPick, DraftOrder, DraftProtection
from app.services.draft_service import DraftService
from app.extensions import db


@draft_bp.route('/')
@draft_bp.route('/<int:org_season_id>')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def index(org_season_id=None):
    """Draft dashboard - list all draft sessions."""
    # Default to current season
    if org_season_id is None:
        current_season = OrgSeason.get_current_season()
        if current_season:
            org_season_id = current_season.ID
        else:
            flash('No current season found.', 'error')
            return redirect(url_for('main.dashboard'))

    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Get all draft sessions for this season
    sessions = DraftService.get_sessions_for_season(org_season_id)

    # Get available seasons
    seasons = OrgSeason.query.order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).limit(10).all()

    return render_template('draft/index.html',
                           org_season=org_season,
                           sessions=sessions,
                           seasons=seasons)


@draft_bp.route('/create', methods=['GET', 'POST'])
@draft_bp.route('/create/<int:org_season_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def create(org_season_id=None):
    """Create a new draft session."""
    # Default to current season
    if org_season_id is None:
        current_season = OrgSeason.get_current_season()
        if current_season:
            org_season_id = current_season.ID
        else:
            flash('No current season found.', 'error')
            return redirect(url_for('draft.index'))

    org_season = OrgSeason.query.get_or_404(org_season_id)

    if request.method == 'POST':
        league_id = request.form.get('league_id', type=int)
        name = request.form.get('name', '').strip()
        draft_order_type = request.form.get('draft_order_type', 'snake')
        rounds = request.form.get('rounds', type=int, default=12)

        if not league_id:
            flash('Please select a league.', 'error')
            return redirect(url_for('draft.create', org_season_id=org_season_id))

        if not name:
            league = League.query.get(league_id)
            name = f"{league.get_seasonal_name(org_season.is_spring)} Draft"

        session = DraftService.create_session(
            org_season_id=org_season_id,
            league_id=league_id,
            name=name,
            draft_order_type=draft_order_type,
            rounds=rounds,
            created_by=current_user.ID
        )

        flash(f'Draft session "{session.name}" created successfully.', 'success')
        return redirect(url_for('draft.setup', session_id=session.id))

    # Get leagues for dropdown
    leagues = League.get_all_active()

    return render_template('draft/create.html',
                           org_season=org_season,
                           leagues=leagues)


@draft_bp.route('/<int:session_id>/setup', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def setup(session_id):
    """Setup draft order for a session."""
    session = DraftService.get_session(session_id)
    if not session:
        flash('Draft session not found.', 'error')
        return redirect(url_for('draft.index'))

    if session.status != DraftSession.STATUS_PENDING:
        flash('Draft order can only be set for pending drafts.', 'error')
        return redirect(url_for('draft.board', session_id=session_id))

    # Get teams for this league/season
    teams = DraftService.get_teams_for_draft(session.org_season_id, session.league_id)

    # Get existing order
    existing_order = DraftService.get_draft_order(session_id)
    ordered_team_ids = [o.team_id for o in existing_order]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_order':
            # Get team order from form
            team_order = request.form.getlist('team_order')
            team_ids = [int(t) for t in team_order if t]

            if len(team_ids) < 2:
                flash('Please select at least 2 teams.', 'error')
                return redirect(url_for('draft.setup', session_id=session_id))

            DraftService.set_draft_order(session_id, team_ids)
            flash('Draft order saved.', 'success')
            return redirect(url_for('draft.setup', session_id=session_id))

        elif action == 'generate_picks':
            # Generate pick slots
            if not existing_order:
                flash('Please set draft order first.', 'error')
                return redirect(url_for('draft.setup', session_id=session_id))

            try:
                count = DraftService.generate_picks(session)
                flash(f'Generated {count} picks.', 'success')
            except ValueError as e:
                flash(str(e), 'error')

            return redirect(url_for('draft.setup', session_id=session_id))

        elif action == 'start_draft':
            try:
                DraftService.start_draft(session_id)
                flash('Draft started!', 'success')
                return redirect(url_for('draft.board', session_id=session_id))
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('draft.setup', session_id=session_id))

    # Get pick count
    pick_count = session.picks.count()

    # Get protections and available players for protection
    protections = DraftService.get_protections(session_id)
    available_players = DraftService.get_players_for_protection(session)

    return render_template('draft/setup.html',
                           session=session,
                           teams=teams,
                           existing_order=existing_order,
                           ordered_team_ids=ordered_team_ids,
                           pick_count=pick_count,
                           protections=protections,
                           available_players=available_players)


@draft_bp.route('/<int:session_id>/board')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def board(session_id):
    """Live draft board view."""
    session = DraftService.get_session(session_id)
    if not session:
        flash('Draft session not found.', 'error')
        return redirect(url_for('draft.index'))

    # Get available players
    available_players = DraftService.get_available_players(session)

    # Get current pick
    current_pick = DraftService.get_current_pick(session_id)

    # Check if current pick has a protection
    current_protection = None
    if current_pick:
        current_protection = DraftService.get_protection_for_pick(
            session_id, current_pick.team_id, current_pick.round_number
        )

    # Get all picks for results display
    all_picks = DraftService.get_draft_results(session_id)

    # Get draft order for reference
    draft_order = DraftService.get_draft_order(session_id)

    # Get all protections for display
    protections = DraftService.get_protections(session_id)

    return render_template('draft/board.html',
                           session=session,
                           available_players=available_players,
                           current_pick=current_pick,
                           current_protection=current_protection,
                           all_picks=all_picks,
                           draft_order=draft_order,
                           protections=protections)


@draft_bp.route('/<int:session_id>/pick', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def make_pick(session_id):
    """Make a draft pick."""
    player_id = request.form.get('player_id', type=int)

    if not player_id:
        flash('Please select a player.', 'error')
        return redirect(url_for('draft.board', session_id=session_id))

    try:
        pick = DraftService.make_pick(session_id, player_id)
        session = DraftSession.query.get(session_id)

        if session.is_completed:
            flash('Draft complete!', 'success')
        else:
            flash(f'Pick #{pick.pick_number} made successfully.', 'success')
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('draft.board', session_id=session_id))


@draft_bp.route('/<int:session_id>/status')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def status(session_id):
    """AJAX endpoint for draft status."""
    session = DraftService.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    current_pick = DraftService.get_current_pick(session_id)

    return jsonify({
        'status': session.status,
        'current_round': session.current_round,
        'current_pick_number': session.current_pick_number,
        'current_team': session.current_team.scheduler_display_name if session.current_team else None,
        'total_picks': session.total_picks,
        'is_completed': session.is_completed
    })


@draft_bp.route('/<int:session_id>/pause', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def pause(session_id):
    """Pause a draft."""
    session = DraftSession.query.get_or_404(session_id)
    try:
        session.pause()
        flash('Draft paused.', 'info')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('draft.board', session_id=session_id))


@draft_bp.route('/<int:session_id>/resume', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def resume(session_id):
    """Resume a paused draft."""
    session = DraftSession.query.get_or_404(session_id)
    try:
        session.resume()
        flash('Draft resumed.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('draft.board', session_id=session_id))


@draft_bp.route('/<int:session_id>/results')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def results(session_id):
    """View draft results."""
    session = DraftService.get_session(session_id)
    if not session:
        flash('Draft session not found.', 'error')
        return redirect(url_for('draft.index'))

    # Get all picks
    all_picks = DraftService.get_draft_results(session_id)

    # Group picks by round
    picks_by_round = {}
    for pick in all_picks:
        if pick.round_number not in picks_by_round:
            picks_by_round[pick.round_number] = []
        picks_by_round[pick.round_number].append(pick)

    # Get draft order
    draft_order = DraftService.get_draft_order(session_id)

    return render_template('draft/results.html',
                           session=session,
                           all_picks=all_picks,
                           picks_by_round=picks_by_round,
                           draft_order=draft_order)


# =============================================================================
# Protected Picks (Coach's Children)
# =============================================================================

@draft_bp.route('/<int:session_id>/protection', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def add_protection(session_id):
    """Add a protected pick (coach's child)."""
    team_id = request.form.get('team_id', type=int)
    player_id = request.form.get('player_id', type=int)
    round_number = request.form.get('round_number', type=int)
    reason = request.form.get('reason', "Coach's child").strip()

    if not all([team_id, player_id, round_number]):
        flash('Please fill in all fields.', 'error')
        return redirect(url_for('draft.setup', session_id=session_id))

    try:
        protection = DraftService.add_protection(
            session_id=session_id,
            team_id=team_id,
            player_id=player_id,
            round_number=round_number,
            reason=reason or "Coach's child"
        )
        flash(f'Protected pick added: {protection.player_display_name} must be drafted by {protection.team_display_name} in round {round_number}.', 'success')
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('draft.setup', session_id=session_id))


@draft_bp.route('/<int:session_id>/protection/<int:protection_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def remove_protection(session_id, protection_id):
    """Remove a protected pick."""
    DraftService.remove_protection(protection_id)
    flash('Protected pick removed.', 'success')
    return redirect(url_for('draft.setup', session_id=session_id))
