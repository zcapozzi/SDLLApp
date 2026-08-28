"""Templates for notification emails"""


def render_change_notification(change, game, recipient_type):
    """
    Render email content for a game change notification.

    Args:
        change: GameChange object
        game: Game object
        recipient_type: One of 'admin', 'coach', 'umpire', 'parent'

    Returns:
        Tuple of (subject, body_text, body_html)
    """
    # Format game info
    game_date_str = game.game_date.strftime('%A, %B %d, %Y at %I:%M %p') if game.game_date else 'TBD'
    field_str = game.field_name or 'TBD'
    league_str = game.league or 'Unknown League'

    # Get team names
    home_team_name = 'TBD'
    away_team_name = 'TBD'
    if game.home_ID:
        from app.models.team import TeamSeason
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.computed_display_name
    if game.away_ID:
        from app.models.team import TeamSeason
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.computed_display_name

    # Build subject line
    change_desc = change.describe_change() if change else 'Updated'
    subject = f"[SDLL] Game {change_desc}: {league_str} - {home_team_name} vs {away_team_name}"

    # Build body
    body_lines = [
        f"Game Change Notification",
        f"",
        f"League: {league_str}",
        f"Game: {home_team_name} vs {away_team_name}",
        f"Date/Time: {game_date_str}",
        f"Field: {field_str}",
        f"",
        f"Change: {change_desc}",
    ]

    if change and change.reason:
        body_lines.append(f"Reason: {change.reason}")

    body_lines.extend([
        f"",
        f"---",
        f"South Durham Little League",
        f"www.southdurhamlittleleague.org"
    ])

    body_text = '\n'.join(body_lines)

    # Build HTML body
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: rgb(34, 139, 34); color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .game-info {{ background-color: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .change-info {{ background-color: #fff3e0; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid rgb(255, 140, 0); }}
        .footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>SDLL Game Change Notification</h2>
    </div>
    <div class="content">
        <div class="game-info">
            <p><strong>League:</strong> {league_str}</p>
            <p><strong>Game:</strong> {home_team_name} vs {away_team_name}</p>
            <p><strong>Date/Time:</strong> {game_date_str}</p>
            <p><strong>Field:</strong> {field_str}</p>
        </div>

        <div class="change-info">
            <p><strong>Change:</strong> {change_desc}</p>
            {"<p><strong>Reason:</strong> " + change.reason + "</p>" if change and change.reason else ""}
        </div>

        <p>Please update your calendar accordingly.</p>
    </div>
    <div class="footer">
        <p>South Durham Little League</p>
        <p>www.southdurhamlittleleague.org</p>
    </div>
</body>
</html>
"""

    return subject, body_text, body_html


def render_cancellation_notification(game, reason=None):
    """
    Render email content for a game cancellation.

    Args:
        game: Game object
        reason: Optional cancellation reason

    Returns:
        Tuple of (subject, body_text, body_html)
    """
    # Format game info
    game_date_str = game.game_date.strftime('%A, %B %d, %Y at %I:%M %p') if game.game_date else 'TBD'
    field_str = game.field_name or 'TBD'
    league_str = game.league or 'Unknown League'

    # Get team names
    home_team_name = 'TBD'
    away_team_name = 'TBD'
    if game.home_ID:
        from app.models.team import TeamSeason
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.computed_display_name
    if game.away_ID:
        from app.models.team import TeamSeason
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.computed_display_name

    subject = f"[SDLL] CANCELLED: {league_str} - {home_team_name} vs {away_team_name} on {game_date_str}"

    body_lines = [
        f"GAME CANCELLED",
        f"",
        f"The following game has been cancelled:",
        f"",
        f"League: {league_str}",
        f"Game: {home_team_name} vs {away_team_name}",
        f"Date/Time: {game_date_str}",
        f"Field: {field_str}",
    ]

    if reason:
        body_lines.append(f"")
        body_lines.append(f"Reason: {reason}")

    body_lines.extend([
        f"",
        f"We apologize for any inconvenience.",
        f"",
        f"---",
        f"South Durham Little League",
        f"www.southdurhamlittleleague.org"
    ])

    body_text = '\n'.join(body_lines)

    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: #c62828; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .game-info {{ background-color: #ffebee; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #c62828; }}
        .footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>GAME CANCELLED</h2>
    </div>
    <div class="content">
        <p>The following game has been cancelled:</p>

        <div class="game-info">
            <p><strong>League:</strong> {league_str}</p>
            <p><strong>Game:</strong> {home_team_name} vs {away_team_name}</p>
            <p><strong>Date/Time:</strong> {game_date_str}</p>
            <p><strong>Field:</strong> {field_str}</p>
            {"<p><strong>Reason:</strong> " + reason + "</p>" if reason else ""}
        </div>

        <p>We apologize for any inconvenience.</p>
    </div>
    <div class="footer">
        <p>South Durham Little League</p>
        <p>www.southdurhamlittleleague.org</p>
    </div>
</body>
</html>
"""

    return subject, body_text, body_html


def render_umpire_reassignment_notification(game, action, partner_name, old_partner_name=None, new_partner_name=None):
    """
    Render email content for umpire assignment changes to partner organizations.

    Args:
        game: Game object
        action: 'assigned' or 'removed'
        partner_name: Name of the partner being notified
        old_partner_name: Name of the previous partner (for assigned notifications)
        new_partner_name: Name of the new partner (for removed notifications)

    Returns:
        Tuple of (subject, body_text, body_html)
    """
    # Format game info
    game_date_str = game.game_date.strftime('%A, %B %d, %Y at %I:%M %p') if game.game_date else 'TBD'
    field_str = game.field_name or 'TBD'
    league_str = game.league or 'Unknown League'

    # Get team names
    home_team_name = 'TBD'
    away_team_name = 'TBD'
    if game.home_ID:
        from app.models.team import TeamSeason
        home_team = TeamSeason.query.get(game.home_ID)
        if home_team:
            home_team_name = home_team.computed_display_name
    if game.away_ID:
        from app.models.team import TeamSeason
        away_team = TeamSeason.query.get(game.away_ID)
        if away_team:
            away_team_name = away_team.computed_display_name

    if action == 'assigned':
        subject = f"[SDLL] Game Assigned to {partner_name}: {league_str} on {game.game_date.strftime('%m/%d')}"
        action_text = f"This game has been ASSIGNED to {partner_name}."
        detail_text = f"Previously assigned to: {old_partner_name or 'N/A'}"
        header_color = "#2e7d32"  # Green
        box_color = "#e8f5e9"  # Light green
    else:  # removed
        subject = f"[SDLL] Game Removed from {partner_name}: {league_str} on {game.game_date.strftime('%m/%d')}"
        action_text = f"This game has been REMOVED from {partner_name}'s assignment."
        detail_text = f"Reassigned to: {new_partner_name or 'Unassigned'}"
        header_color = "#e65100"  # Orange
        box_color = "#fff3e0"  # Light orange

    body_lines = [
        f"Umpire Assignment Change",
        f"",
        action_text,
        f"",
        f"League: {league_str}",
        f"Game: {home_team_name} vs {away_team_name}",
        f"Date/Time: {game_date_str}",
        f"Field: {field_str}",
        f"",
        detail_text,
        f"",
        f"---",
        f"South Durham Little League",
        f"www.southdurhamlittleleague.org"
    ]

    body_text = '\n'.join(body_lines)

    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: {header_color}; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .game-info {{ background-color: {box_color}; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid {header_color}; }}
        .action-info {{ font-size: 18px; font-weight: bold; margin: 15px 0; color: {header_color}; }}
        .footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Umpire Assignment {'Assigned' if action == 'assigned' else 'Removed'}</h2>
    </div>
    <div class="content">
        <p class="action-info">{action_text}</p>

        <div class="game-info">
            <p><strong>League:</strong> {league_str}</p>
            <p><strong>Game:</strong> {home_team_name} vs {away_team_name}</p>
            <p><strong>Date/Time:</strong> {game_date_str}</p>
            <p><strong>Field:</strong> {field_str}</p>
        </div>

        <p><em>{detail_text}</em></p>

        <p>Please update your records accordingly.</p>
    </div>
    <div class="footer">
        <p>South Durham Little League</p>
        <p>www.southdurhamlittleleague.org</p>
    </div>
</body>
</html>
"""

    return subject, body_text, body_html