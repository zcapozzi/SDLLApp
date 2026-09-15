"""Service for post-game report management.

Handles:
- Token generation and validation for secure links
- Report submission and updates
- Email sending to coaches
- Score reconciliation between teams
- Flagging unusual feedback patterns
"""

import hmac
import hashlib
import os
from datetime import datetime, timedelta
from flask import url_for, current_app

from app.extensions import db
from app.models.post_game_report import PostGameReport
from app.models.game import Game
from app.models.team import TeamSeason
from app.models.coach import CoachSeason, CoachUser
from app.models.league_season import LeagueSeason
from app.models.user import User


def get_secret_key():
    """Get the secret key for HMAC token generation."""
    return os.environ.get('SECRET_KEY', 'default-secret-key-change-me')


def create_report_token(game_id, team_id):
    """Generate HMAC token for secure post-game report link.

    Args:
        game_id: Game ID
        team_id: Team ID

    Returns:
        str: HMAC token
    """
    message = f"{game_id}:{team_id}".encode('utf-8')
    secret = get_secret_key().encode('utf-8')
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]


def validate_report_token(token, game_id, team_id):
    """Verify token is valid for the given game and team.

    Args:
        token: The token to validate
        game_id: Game ID
        team_id: Team ID

    Returns:
        bool: True if token is valid
    """
    expected = create_report_token(game_id, team_id)
    return hmac.compare_digest(token, expected)


def get_report_url(game_id, team_id, external=True):
    """Generate the full URL for a post-game report.

    Args:
        game_id: Game ID
        team_id: Team ID
        external: If True, generate full external URL

    Returns:
        str: URL to the post-game report form
    """
    token = create_report_token(game_id, team_id)
    if external:
        return url_for('coach.postgame_entry', token=token, g=game_id, t=team_id, _external=True)
    return url_for('coach.postgame_entry', token=token, g=game_id, t=team_id)


def get_not_played_url(game_id, team_id, external=True):
    """Generate the URL for marking a game as not played.

    Args:
        game_id: Game ID
        team_id: Team ID
        external: If True, generate full external URL

    Returns:
        str: URL to the not-played form
    """
    token = create_report_token(game_id, team_id)
    if external:
        return url_for('coach.postgame_entry', token=token, g=game_id, t=team_id, not_played='1', _external=True)
    return url_for('coach.postgame_entry', token=token, g=game_id, t=team_id, not_played='1')


def can_user_submit(user_id, game_id, team_id):
    """Check if user is authorized to submit a report for this team.

    Args:
        user_id: User ID
        game_id: Game ID
        team_id: Team ID

    Returns:
        tuple: (can_submit: bool, role: str or None, error_message: str or None)
    """
    # Verify the game exists and team is a participant
    game = Game.query.get(game_id)
    if not game:
        return False, None, "Game not found"

    if team_id not in (game.home_ID, game.away_ID):
        return False, None, "Team is not part of this game"

    # Check if user is a coach for this team
    # First try direct coach assignment
    coach_season = CoachSeason.query.filter_by(team_id=team_id).join(
        CoachUser
    ).filter(CoachUser.user_id == user_id).first()

    if coach_season:
        return True, coach_season.role, None

    # Also check if user has admin/scheduler/DataManager role (can submit for any team)
    user = User.query.get(user_id)
    if user and user.has_role('admin', 'scheduler', 'DataManager'):
        return True, 'admin', None

    return False, None, "You are not a coach for this team"


def submit_report(game_id, team_id, user_id, data):
    """Save or update a post-game report.

    Args:
        game_id: Game ID
        team_id: Team ID
        user_id: Submitting user's ID
        data: Dict with report fields:
            - our_score: int
            - opponent_score: int
            - innings_batted: int
            - innings_fielded: int
            - umpire_name: str
            - umpire_rating: str (excellent/good/ok/poor)
            - umpire_comments: str (optional)

    Returns:
        tuple: (success: bool, report: PostGameReport or None, error: str or None)
    """
    can_submit, role, error = can_user_submit(user_id, game_id, team_id)
    if not can_submit:
        return False, None, error

    # Get or create the report
    report = PostGameReport.get_or_create(game_id, team_id)

    # Check if editable
    if not report.is_editable:
        return False, None, "Edit window has expired (24 hours after submission)"

    # Update fields
    report.our_score = data.get('our_score')
    report.opponent_score = data.get('opponent_score')
    report.innings_batted = data.get('innings_batted')
    report.innings_fielded = data.get('innings_fielded')
    report.umpire_name = data.get('umpire_name')
    report.umpire_rating = data.get('umpire_rating')
    report.umpire_comments = data.get('umpire_comments')

    report.status = PostGameReport.STATUS_SUBMITTED
    report.submitted_by_user_id = user_id
    report.submitted_by_role = role
    report.submitted_at = datetime.utcnow()

    # Clear any not-played fields
    report.not_played_reason = None
    report.not_played_notes = None

    # Check for unusual rating pattern (flag detection)
    check_and_flag_report(report, user_id)

    db.session.commit()

    # Try to reconcile scores if both teams have submitted
    reconcile_scores(game_id)

    return True, report, None


def mark_not_played(game_id, team_id, user_id, reason, notes=None):
    """Mark a game as not played for this team.

    Args:
        game_id: Game ID
        team_id: Team ID
        user_id: Submitting user's ID
        reason: One of: rainout, cancelled, forfeit, other
        notes: Optional additional notes

    Returns:
        tuple: (success: bool, report: PostGameReport or None, error: str or None)
    """
    can_submit, role, error = can_user_submit(user_id, game_id, team_id)
    if not can_submit:
        return False, None, error

    # Get or create the report
    report = PostGameReport.get_or_create(game_id, team_id)

    # Check if editable
    if not report.is_editable:
        return False, None, "Edit window has expired (24 hours after submission)"

    # Clear score/umpire fields
    report.our_score = None
    report.opponent_score = None
    report.innings_batted = None
    report.innings_fielded = None
    report.umpire_name = None
    report.umpire_rating = None
    report.umpire_comments = None

    # Set not-played fields
    report.status = PostGameReport.STATUS_NOT_PLAYED
    report.not_played_reason = reason
    report.not_played_notes = notes
    report.submitted_by_user_id = user_id
    report.submitted_by_role = role
    report.submitted_at = datetime.utcnow()

    db.session.commit()

    return True, report, None


def reconcile_scores(game_id):
    """Check if both teams submitted matching scores and update Game record.

    When both teams report matching scores:
    - Home team's our_score should match away team's opponent_score
    - Away team's our_score should match home team's opponent_score

    Args:
        game_id: Game ID

    Returns:
        tuple: (reconciled: bool, disputed: bool, message: str)
    """
    game = Game.query.get(game_id)
    if not game:
        return False, False, "Game not found"

    reports = PostGameReport.query.filter_by(game_id=game_id).all()
    submitted_reports = [r for r in reports if r.status == PostGameReport.STATUS_SUBMITTED]

    if len(submitted_reports) != 2:
        return False, False, "Both teams have not submitted yet"

    home_report = next((r for r in submitted_reports if r.team_id == game.home_ID), None)
    away_report = next((r for r in submitted_reports if r.team_id == game.away_ID), None)

    if not home_report or not away_report:
        return False, False, "Missing report from one team"

    # Check score agreement
    # Home's our_score should equal Away's opponent_score (home team's actual score)
    # Away's our_score should equal Home's opponent_score (away team's actual score)
    home_score_agrees = home_report.our_score == away_report.opponent_score
    away_score_agrees = away_report.our_score == home_report.opponent_score

    if home_score_agrees and away_score_agrees:
        # Scores match - update game
        game.home_score = home_report.our_score
        game.away_score = away_report.our_score
        game.status = 'completed'
        db.session.commit()
        return True, False, "Scores reconciled and game updated"
    else:
        # Scores don't match - flag for review
        # We don't auto-update when disputed
        return False, True, f"Score dispute: Home reported {home_report.our_score}-{home_report.opponent_score}, Away reported {away_report.our_score}-{away_report.opponent_score}"


def check_and_flag_report(report, user_id):
    """Check if this report should be flagged for unusual rating.

    Flags when a coach's rating deviates significantly from their historical average.

    Args:
        report: PostGameReport being submitted
        user_id: User submitting the report
    """
    if not report.umpire_rating:
        return

    rating_values = {
        PostGameReport.RATING_EXCELLENT: 4,
        PostGameReport.RATING_GOOD: 3,
        PostGameReport.RATING_OK: 2,
        PostGameReport.RATING_POOR: 1
    }

    current_value = rating_values.get(report.umpire_rating, 0)

    # Get coach's historical ratings (last 20 reports)
    historical = PostGameReport.query.filter(
        PostGameReport.submitted_by_user_id == user_id,
        PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
        PostGameReport.umpire_rating.isnot(None),
        PostGameReport.id != report.id  # Exclude current report
    ).order_by(PostGameReport.submitted_at.desc()).limit(20).all()

    if len(historical) < 3:
        # Not enough history to flag
        return

    # Calculate average
    total = sum(rating_values.get(r.umpire_rating, 0) for r in historical)
    avg = total / len(historical)

    # Flag if deviation is 2+ levels
    deviation = abs(current_value - avg)
    if deviation >= 2:
        report.is_flagged = True
        direction = "lower" if current_value < avg else "higher"
        report.flag_reason = f"Rating is {deviation:.1f} levels {direction} than coach's typical rating (avg: {avg:.1f})"


def get_games_needing_reports(year, is_spring):
    """Get completed games that need post-game reports.

    Returns games where:
    - Game is in the past
    - Game is regular or playoff type
    - League has postgame_enabled = True
    - At least one team hasn't submitted a report

    Args:
        year: Season year
        is_spring: Spring/Fall flag

    Returns:
        list: List of Game objects needing reports
    """
    from sqlalchemy.orm import joinedload

    # Get leagues with postgame enabled
    enabled_leagues = LeagueSeason.query.filter_by(
        year=year,
        is_spring=is_spring,
        active=1,
        postgame_enabled=True
    ).all()
    enabled_league_names = [ls.league for ls in enabled_leagues]

    if not enabled_league_names:
        return []

    # Get completed games
    games = Game.query.options(
        joinedload(Game.home_team),
        joinedload(Game.away_team)
    ).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        Game.active == 1,
        Game.game_date < datetime.utcnow(),
        Game.game_type.in_(['regular', 'playoff']),
        Game.league.in_(enabled_league_names),
        Game.home_ID.isnot(None),
        Game.away_ID.isnot(None)
    ).order_by(Game.game_date.desc()).all()

    # Filter to those needing reports
    needing_reports = []
    for game in games:
        reports = PostGameReport.query.filter_by(game_id=game.ID).all()
        submitted_team_ids = {r.team_id for r in reports if r.status != PostGameReport.STATUS_PENDING}

        # Check if either team hasn't submitted
        if game.home_ID not in submitted_team_ids or game.away_ID not in submitted_team_ids:
            needing_reports.append({
                'game': game,
                'home_submitted': game.home_ID in submitted_team_ids,
                'away_submitted': game.away_ID in submitted_team_ids
            })

    return needing_reports


def get_games_needing_emails(minutes_after_start=105):
    """Get games that need post-game emails sent.

    Finds games where:
    - Game start time + minutes_after_start < now
    - League has postgame_enabled = True
    - No PostGameReport record exists with email_sent_at set

    Args:
        minutes_after_start: Minutes after game start to send email

    Returns:
        list: List of (Game, team_id) tuples needing emails
    """
    cutoff = datetime.utcnow() - timedelta(minutes=minutes_after_start)

    # Get games that started before cutoff
    games = Game.query.filter(
        Game.active == 1,
        Game.game_date < cutoff,
        Game.game_type.in_(['regular', 'playoff']),
        Game.home_ID.isnot(None),
        Game.away_ID.isnot(None)
    ).all()

    results = []
    for game in games:
        # Check if league has postgame enabled
        league_season = LeagueSeason.query.filter_by(
            year=game.year,
            is_spring=game.is_spring,
            league=game.league,
            active=1
        ).first()

        if not league_season or not getattr(league_season, 'postgame_enabled', False):
            continue

        # Check if emails already sent for each team
        for team_id in [game.home_ID, game.away_ID]:
            report = PostGameReport.query.filter_by(
                game_id=game.ID,
                team_id=team_id
            ).first()

            if not report or not report.email_sent_at:
                results.append((game, team_id))

    return results


def send_postgame_email(game_id, team_id):
    """Send post-game report email to coaches for a team.

    Args:
        game_id: Game ID
        team_id: Team ID

    Returns:
        tuple: (success: bool, message: str)
    """
    from app.services.notification_service import GmailService

    game = Game.query.get(game_id)
    if not game:
        return False, "Game not found"

    team = TeamSeason.query.get(team_id)
    if not team:
        return False, "Team not found"

    # Get opponent
    opponent_id = game.away_ID if team_id == game.home_ID else game.home_ID
    opponent = TeamSeason.query.get(opponent_id)

    # Get coaches for this team
    coaches = CoachSeason.get_for_team(team_id)
    if not coaches:
        return False, "No coaches found for team"

    head_coach = next((c for c in coaches if c.is_head_coach), None)
    assistant_coaches = [c for c in coaches if not c.is_head_coach]

    if not head_coach:
        # Use first coach as head
        head_coach = coaches[0]
        assistant_coaches = coaches[1:]

    # Build email
    to_email = head_coach.email
    if not to_email:
        return False, "Head coach has no email"

    cc_emails = [c.email for c in assistant_coaches if c.email]

    # Generate secure URLs
    report_url = get_report_url(game_id, team_id, external=True)
    not_played_url = get_not_played_url(game_id, team_id, external=True)

    # Format game info
    game_date = game.game_date.strftime('%A, %B %d') if game.game_date else 'TBD'

    subject = f"Post-Game Report: {team.computed_display_name} vs {opponent.computed_display_name if opponent else 'TBD'} - {game_date}"

    matchup = f"{team.computed_display_name} vs {opponent.computed_display_name if opponent else 'TBD'}"

    body_text = f"""Hi {head_coach.name.split()[0] if head_coach.name else 'Coach'},

The league is moving our Google Sheets-based post-game data collection to the new SDLL OS website. Please submit the post-game report for today's game:

{matchup}

Click here to submit your report:
{report_url}

If the game was not played, click here instead:
{not_played_url}

Thanks,
SDLL
"""

    body_html = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #228B22;">Post-Game Report</h2>

    <p>Hi {head_coach.name.split()[0] if head_coach.name else 'Coach'},</p>

    <p>The league is moving our Google Sheets-based post-game data collection to the new SDLL OS website. Please submit the post-game report for today's game:</p>

    <p style="font-size: 18px; margin: 20px 0;">
        <strong>{matchup}</strong>
    </p>

    <p style="text-align: center; margin: 25px 0;">
        <a href="{report_url}" style="display: inline-block; background: #228B22; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
            Submit Post-Game Report
        </a>
    </p>

    <p style="text-align: center;">
        <a href="{not_played_url}" style="color: #666; font-size: 14px;">Game was not played</a>
    </p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #888; font-size: 12px;">South Durham Little League</p>
</body>
</html>
"""

    # Send email
    try:
        gmail = GmailService()
        gmail.send_email(
            to=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc_emails if cc_emails else None
        )

        # Record email sent
        report = PostGameReport.get_or_create(game_id, team_id)
        report.email_sent_at = datetime.utcnow()
        db.session.commit()

        return True, "Email sent successfully"

    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def send_pending_postgame_emails():
    """Cron job function: Send post-game emails for games that need them.

    Call this from a scheduled task (e.g., every 15 minutes).

    Returns:
        dict: Summary of emails sent and errors
    """
    games_needing_emails = get_games_needing_emails()

    results = {
        'sent': 0,
        'failed': 0,
        'errors': []
    }

    for game, team_id in games_needing_emails:
        success, message = send_postgame_email(game.ID, team_id)
        if success:
            results['sent'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"Game {game.ID}, Team {team_id}: {message}")

    return results


def get_pending_reports_for_coach(user_id):
    """Get games where this coach hasn't submitted a report yet.

    Args:
        user_id: User ID

    Returns:
        list: List of dicts with game and team info
    """
    return PostGameReport.get_pending_for_coach(user_id)


def get_report_summary(year, is_spring, league=None):
    """Get summary statistics for post-game reports.

    Args:
        year: Season year
        is_spring: Spring/Fall flag
        league: Optional league filter

    Returns:
        dict: Summary statistics
    """
    return PostGameReport.get_completion_stats(year, is_spring, league)
