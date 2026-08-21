"""Umpire Portal routes - self-service interface for umpires.

This is the Assignr replacement - umpires can:
- View available games to claim
- Claim games they want to work
- View their claimed/upcoming games
- Release games they can no longer work
- View pay history
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date, timedelta

from app.extensions import db
from app.models.umpire_profile import UmpireProfile
from app.models.game_umpire import GameUmpire
from app.models.game import Game
from app.models.league import League
from app.models.team import TeamSeason
from app.models.umpire_payment import UmpirePayment
from app.utils.logging import SDLLLogger

umpire_portal_bp = Blueprint('umpire_portal', __name__)
logger = SDLLLogger('umpire_portal')


def umpire_required(f):
    """Decorator to require umpire role with profile."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.has_umpire_profile():
            flash('You do not have an umpire profile. Please contact the coordinator.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_profile():
    """Get the current user's umpire profile."""
    return UmpireProfile.get_by_user_id(current_user.ID)


# =============================================================================
# Dashboard
# =============================================================================

@umpire_portal_bp.route('/')
@login_required
@umpire_required
def dashboard():
    """Umpire dashboard - overview of available and claimed games."""
    profile = get_current_profile()

    # Get upcoming claimed games
    my_games = GameUmpire.query.filter_by(
        umpire_profile_id=profile.id
    ).filter(
        GameUmpire.status.notin_(['cancelled', 'no_show'])
    ).join(Game).filter(
        Game.game_date > datetime.utcnow(),
        Game.active == 1
    ).order_by(Game.game_date).limit(10).all()

    # Get count of available games
    available_count = _get_available_games_query(profile).count()

    # Get recent pay info
    pending_payment = UmpirePayment.query.filter_by(
        umpire_profile_id=profile.id,
        status='pending'
    ).first()

    return render_template(
        'umpire_portal/dashboard.html',
        profile=profile,
        my_games=my_games,
        available_count=available_count,
        pending_payment=pending_payment
    )


# =============================================================================
# Available Games
# =============================================================================

def _get_available_games_query(profile):
    """Build query for games available for this umpire to claim.

    Games are available if:
    1. In the future
    2. Active and scheduled
    3. Needs umpires (not tee-ball, has umpire_count > 0)
    4. No current umpire assigned (or unfilled slot)
    5. Umpire is eligible (kid-pitch certification if required)
    """
    # Get leagues that need umpires and umpire is eligible for
    eligible_leagues = []
    for league in League.get_all_active():
        if not league.needs_umpires:
            continue
        # Check kid-pitch eligibility
        if league.requires_kid_pitch and not profile.is_kid_pitch_eligible:
            continue
        # Check if SDLL umpires can work this league
        if not league.can_use_sdll_umpires():
            continue
        eligible_leagues.append(league.display_name)

    # Games needing umpires
    return Game.query.filter(
        Game.game_date > datetime.utcnow(),
        Game.active == 1,
        Game.status == 'scheduled',
        Game.game_type.in_(['regular', 'playoff']),
        Game.league.in_(eligible_leagues) if eligible_leagues else False,
        # No current umpire assignment
        ~Game.ID.in_(
            db.session.query(GameUmpire.game_id).filter(
                GameUmpire.status.notin_(['cancelled']),
                GameUmpire.umpire_profile_id.isnot(None)  # Has SDLL umpire
            )
        )
    )


@umpire_portal_bp.route('/available')
@login_required
@umpire_required
def available():
    """View available games to claim."""
    profile = get_current_profile()

    # Date filter
    date_filter = request.args.get('date', '')
    league_filter = request.args.get('league', '')

    query = _get_available_games_query(profile)

    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Game.game_date) == filter_date)
        except ValueError:
            pass

    if league_filter:
        query = query.filter(Game.league == league_filter)

    games = query.order_by(Game.game_date).limit(50).all()

    # Get unique leagues for filter dropdown
    all_leagues = League.get_all_active()
    eligible_leagues = [l for l in all_leagues if l.needs_umpires and l.can_use_sdll_umpires()]

    return render_template(
        'umpire_portal/available.html',
        games=games,
        leagues=eligible_leagues,
        date_filter=date_filter,
        league_filter=league_filter
    )


# =============================================================================
# My Games
# =============================================================================

@umpire_portal_bp.route('/my-games')
@login_required
@umpire_required
def my_games():
    """View claimed/upcoming games."""
    profile = get_current_profile()

    # Upcoming games
    upcoming = GameUmpire.query.filter_by(
        umpire_profile_id=profile.id
    ).filter(
        GameUmpire.status.notin_(['cancelled', 'no_show'])
    ).join(Game).filter(
        Game.game_date > datetime.utcnow(),
        Game.active == 1
    ).order_by(Game.game_date).all()

    # Today's games
    today = date.today()
    today_games = [a for a in upcoming if a.game.game_date.date() == today]

    # Future games (after today)
    future_games = [a for a in upcoming if a.game.game_date.date() > today]

    return render_template(
        'umpire_portal/my_games.html',
        today_games=today_games,
        future_games=future_games
    )


# =============================================================================
# Claim/Release Games
# =============================================================================

@umpire_portal_bp.route('/claim/<int:game_id>', methods=['POST'])
@login_required
@umpire_required
def claim(game_id):
    """Claim an available game."""
    profile = get_current_profile()
    game = Game.query.get_or_404(game_id)

    # Verify game is claimable
    if game.game_date <= datetime.utcnow():
        flash('Cannot claim past games.', 'error')
        return redirect(url_for('umpire_portal.available'))

    # Check if already claimed by an SDLL umpire
    existing = GameUmpire.query.filter(
        GameUmpire.game_id == game_id,
        GameUmpire.umpire_profile_id.isnot(None),
        GameUmpire.status.notin_(['cancelled'])
    ).first()

    if existing:
        flash('This game has already been claimed.', 'error')
        return redirect(url_for('umpire_portal.available'))

    # Check eligibility
    league = League.get_by_name(game.league)
    if league and league.requires_kid_pitch and not profile.is_kid_pitch_eligible:
        flash('You are not certified for kid-pitch games.', 'error')
        return redirect(url_for('umpire_portal.available'))

    # Check for time conflict with other claimed games
    conflict = GameUmpire.query.filter(
        GameUmpire.umpire_profile_id == profile.id,
        GameUmpire.status.notin_(['cancelled'])
    ).join(Game).filter(
        Game.game_date == game.game_date,
        Game.active == 1
    ).first()

    if conflict:
        flash('You already have a game at this time.', 'error')
        return redirect(url_for('umpire_portal.available'))

    # Check if this was previously cancelled (emergency fill)
    was_emergency = GameUmpire.query.filter(
        GameUmpire.game_id == game_id,
        GameUmpire.was_previously_cancelled == True
    ).first() is not None

    try:
        # Create assignment
        assignment = GameUmpire.assign_umpire(
            game_id=game_id,
            umpire_profile_id=profile.id,
            role='umpire',
            assigned_by=current_user.ID
        )

        # Auto-confirm since umpire is claiming
        assignment.confirm(method='app')

        db.session.commit()

        logger.info(f'Umpire {profile.full_name} claimed game {game_id}')
        flash(f'Successfully claimed game on {game.game_date.strftime("%b %d")}!', 'success')

        # TODO: If was_emergency, send notification to coordinator

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error claiming game: {e}')
        flash(f'Error claiming game: {str(e)}', 'error')

    return redirect(url_for('umpire_portal.my_games'))


@umpire_portal_bp.route('/release/<int:game_id>', methods=['POST'])
@login_required
@umpire_required
def release(game_id):
    """Release a claimed game."""
    profile = get_current_profile()

    assignment = GameUmpire.query.filter(
        GameUmpire.game_id == game_id,
        GameUmpire.umpire_profile_id == profile.id,
        GameUmpire.status.notin_(['cancelled'])
    ).first()

    if not assignment:
        flash('You do not have this game claimed.', 'error')
        return redirect(url_for('umpire_portal.my_games'))

    game = assignment.game

    # Check if game is within 24 hours
    hours_until = (game.game_date - datetime.utcnow()).total_seconds() / 3600
    if hours_until < 24:
        flash('Cannot release games within 24 hours. Please contact the coordinator.', 'warning')
        # TODO: Show coordinator contact info
        return redirect(url_for('umpire_portal.my_games'))

    try:
        assignment.cancel(current_user.ID)
        db.session.commit()

        logger.info(f'Umpire {profile.full_name} released game {game_id}')
        flash('Game released successfully.', 'success')

        # TODO: Send notification to coordinator about cancellation

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error releasing game: {e}')
        flash(f'Error releasing game: {str(e)}', 'error')

    return redirect(url_for('umpire_portal.my_games'))


# =============================================================================
# History and Pay
# =============================================================================

@umpire_portal_bp.route('/history')
@login_required
@umpire_required
def history():
    """View past games worked."""
    profile = get_current_profile()

    # Get past completed assignments
    past = GameUmpire.query.filter_by(
        umpire_profile_id=profile.id,
        status='completed'
    ).join(Game).filter(
        Game.game_date <= datetime.utcnow()
    ).order_by(Game.game_date.desc()).limit(50).all()

    return render_template(
        'umpire_portal/history.html',
        assignments=past
    )


@umpire_portal_bp.route('/pay')
@login_required
@umpire_required
def pay():
    """View pay history."""
    profile = get_current_profile()

    # Get all payments
    payments = UmpirePayment.get_for_umpire(profile.id)

    # Calculate unpaid totals
    unpaid_assignments = GameUmpire.query.filter_by(
        umpire_profile_id=profile.id,
        status='completed'
    ).all()

    unpaid_total = sum(
        (float(a.base_pay or 0) * float(a.bonus_multiplier or 1))
        for a in unpaid_assignments
        if a.base_pay  # Only count if pay is set
    )

    return render_template(
        'umpire_portal/pay.html',
        payments=payments,
        unpaid_total=unpaid_total
    )


# =============================================================================
# Profile
# =============================================================================

@umpire_portal_bp.route('/profile')
@login_required
@umpire_required
def profile():
    """View own profile (read-only for umpires)."""
    profile = get_current_profile()

    return render_template(
        'umpire_portal/profile.html',
        profile=profile
    )


# =============================================================================
# API Endpoints for AJAX
# =============================================================================

@umpire_portal_bp.route('/api/available-dates')
@login_required
@umpire_required
def api_available_dates():
    """Get dates with available games (for calendar view)."""
    profile = get_current_profile()

    # Get next 30 days
    start = date.today()
    end = start + timedelta(days=30)

    games = _get_available_games_query(profile).filter(
        Game.game_date >= datetime.combine(start, datetime.min.time()),
        Game.game_date <= datetime.combine(end, datetime.max.time())
    ).all()

    # Group by date
    dates = {}
    for game in games:
        date_str = game.game_date.strftime('%Y-%m-%d')
        if date_str not in dates:
            dates[date_str] = 0
        dates[date_str] += 1

    return jsonify(dates)
