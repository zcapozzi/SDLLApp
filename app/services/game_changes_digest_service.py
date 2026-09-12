"""Service for sending game changes digest emails.

Sends periodic summary emails of game changes to admins and umpire coordinators.
Smart enough to detect "net changes" - if a field was changed and then reverted
within the digest window, it won't be reported.

Can be triggered manually or via a scheduled cron job.
"""

import os
from datetime import datetime, timedelta
from collections import defaultdict
from app.extensions import db
from app.models.game_change import GameChange
from app.models.game import Game
from app.models.user import User


# Default recipient email (umpire coordinator)
DEFAULT_UMPIRE_COORDINATOR_EMAIL = 'sdll.umpires@gmail.com'


def get_recipient_emails():
    """Get list of email addresses for game change digests.

    Uses environment variables:
    - GAME_CHANGES_DIGEST_EMAILS: comma-separated list (overrides default)
    - ADMIN_EMAIL: master admin email (added to recipients if set)
    - Or falls back to umpire coordinator only

    Returns:
        List of email addresses
    """
    env_emails = os.environ.get('GAME_CHANGES_DIGEST_EMAILS', '')
    if env_emails:
        return [e.strip() for e in env_emails.split(',') if e.strip()]

    # Build recipient list: umpire coordinator + master admin (if configured)
    recipients = [DEFAULT_UMPIRE_COORDINATOR_EMAIL]

    admin_email = os.environ.get('ADMIN_EMAIL', '')
    if admin_email and admin_email not in recipients:
        recipients.append(admin_email)

    return recipients


def get_changes_with_net_effect(hours=2):
    """Get game changes from the past N hours, collapsing reversed changes.

    For each game, we look at all changes in the window and compute the
    "net effect" - if a field was changed and then reverted, it's not reported.

    Args:
        hours: Number of hours to look back

    Returns:
        List of dicts with game info and net changes:
        {
            'game': Game object,
            'changes': [GameChange objects],
            'net_changes': {field: {'old': X, 'new': Y}},
            'changed_by': set of user names,
            'change_types': set of change types
        }
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Get all changes in the time window
    all_changes = GameChange.query.filter(
        GameChange.changed_at >= cutoff
    ).order_by(GameChange.game_id, GameChange.changed_at).all()

    if not all_changes:
        return []

    # Group changes by game
    changes_by_game = defaultdict(list)
    for change in all_changes:
        changes_by_game[change.game_id].append(change)

    # Fetch all relevant games
    game_ids = list(changes_by_game.keys())
    games = Game.query.filter(Game.ID.in_(game_ids)).all()
    game_lookup = {g.ID: g for g in games}

    # Fetch users who made changes
    user_ids = set(c.changed_by for c in all_changes if c.changed_by)
    users = User.query.filter(User.ID.in_(user_ids)).all() if user_ids else []
    user_lookup = {u.ID: u.name or f'User {u.ID}' for u in users}

    # Process each game's changes to find net effect
    results = []

    for game_id, changes in changes_by_game.items():
        game = game_lookup.get(game_id)
        if not game:
            continue

        # Track the first and last values for each field
        field_tracking = {}  # field -> {'first_old': X, 'last_new': Y}

        change_types = set()
        changed_by_users = set()

        for change in changes:
            change_types.add(change.change_type)
            user_name = user_lookup.get(change.changed_by, f'User {change.changed_by}')
            changed_by_users.add(user_name)

            # Process the changes_json to track field changes
            changes_dict = change.changes_dict or {}
            for field, values in changes_dict.items():
                if not isinstance(values, dict):
                    continue

                old_val = values.get('old')
                new_val = values.get('new')

                if field not in field_tracking:
                    # First time seeing this field - record the original value
                    field_tracking[field] = {
                        'first_old': old_val,
                        'last_new': new_val
                    }
                else:
                    # Update the last new value
                    field_tracking[field]['last_new'] = new_val

        # Compute net changes (where first_old != last_new)
        net_changes = {}
        for field, tracking in field_tracking.items():
            first_old = tracking['first_old']
            last_new = tracking['last_new']

            # Normalize for comparison (handle None, empty strings, etc.)
            if _values_differ(first_old, last_new):
                net_changes[field] = {
                    'old': first_old,
                    'new': last_new
                }

        # Determine if this is a "reversed" change (changes made but net effect is zero)
        # Only counts as reversed if ALL changes were updates with no net effect
        significant_types = change_types - {'update'}  # create, cancel, delete, reschedule
        is_reversed = (not net_changes and not significant_types and len(changes) > 0)

        # Include all games that had changes
        if net_changes or significant_types or is_reversed:
            results.append({
                'game': game,
                'changes': changes,
                'net_changes': net_changes,
                'changed_by': changed_by_users,
                'change_types': change_types,
                'is_reversed': is_reversed
            })

    return results


def _values_differ(val1, val2):
    """Check if two values are meaningfully different."""
    # Normalize None and empty string
    if val1 is None or val1 == '':
        val1 = None
    if val2 is None or val2 == '':
        val2 = None

    # String comparison (case-insensitive for some fields)
    if isinstance(val1, str) and isinstance(val2, str):
        return val1.strip().lower() != val2.strip().lower()

    return val1 != val2


def format_digest_html(changes_data, hours):
    """Generate HTML email for game changes digest.

    Args:
        changes_data: List from get_changes_with_net_effect()
        hours: Hours window for the digest

    Returns:
        HTML string
    """
    if not changes_data:
        return None

    # Separate actionable changes from reversed changes
    actionable = [item for item in changes_data if not item.get('is_reversed')]
    reversed_items = [item for item in changes_data if item.get('is_reversed')]

    # Group actionable by league
    by_league = defaultdict(list)
    for item in actionable:
        league = item['game'].league or 'Unknown'
        by_league[league].append(item)

    # Group reversed by league
    reversed_by_league = defaultdict(list)
    for item in reversed_items:
        league = item['game'].league or 'Unknown'
        reversed_by_league[league].append(item)

    html_parts = [
        '<!DOCTYPE html>',
        '<html><head><style>',
        'body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }',
        '.game-card { background: #f9f9f9; border-left: 4px solid #228B22; padding: 12px; margin: 10px 0; }',
        '.game-card.reversed { border-left-color: #888; background: #f0f0f0; }',
        '.game-title { font-weight: bold; color: #228B22; margin-bottom: 8px; }',
        '.game-card.reversed .game-title { color: #666; }',
        '.change-item { margin: 4px 0; padding-left: 10px; }',
        '.old-value { color: #c33; text-decoration: line-through; }',
        '.new-value { color: #228B22; font-weight: bold; }',
        '.meta { font-size: 12px; color: #666; margin-top: 8px; }',
        '.reversed-note { color: #888; font-style: italic; font-size: 13px; }',
        '.section-header { background: #FF8C00; color: white; padding: 8px 12px; margin: 20px 0 10px 0; }',
        '.section-header.reversed { background: #888; }',
        '</style></head>',
        '<body>',
        f'<h2 style="color: #228B22;">Game Changes Summary</h2>',
        f'<p>The following games were modified in the last {hours} hour(s):</p>',
    ]

    field_labels = {
        'date': 'Date',
        'time': 'Time',
        'field': 'Field',
        'location': 'Field',
        'status': 'Status',
        'home_team': 'Home Team',
        'away_team': 'Away Team',
        'game_type': 'Game Type',
        'no_time_limit': 'Time Limit',
        'umpire_override': 'Umpire Partner'
    }

    type_labels = {
        'create': '🆕 Created',
        'cancel': '❌ Cancelled',
        'delete': '🗑️ Deleted',
        'reschedule': '📅 Rescheduled',
        'update': '✏️ Updated'
    }

    # ========== ACTIONABLE CHANGES SECTION ==========
    if actionable:
        html_parts.append(f'<h3 style="color: #228B22; margin-top: 20px;">Action Required ({len(actionable)} game{"s" if len(actionable) != 1 else ""})</h3>')

        for league in sorted(by_league.keys()):
            items = by_league[league]
            html_parts.append(f'<div class="section-header">{league} ({len(items)} game{"s" if len(items) != 1 else ""})</div>')

            for item in items:
                game = item['game']
                net_changes = item['net_changes']
                change_types = item['change_types']
                changed_by = item['changed_by']

                # Game title
                game_date = game.game_date.strftime('%a, %b %d at %I:%M %p').replace(' 0', ' ') if game.game_date else 'TBD'
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'

                html_parts.append('<div class="game-card">')
                html_parts.append(f'<div class="game-title">{home} vs {away}</div>')
                html_parts.append(f'<div>{game_date} at {game.field_name or "TBD"}</div>')

                # Show change types
                types_str = ', '.join(type_labels.get(t, t) for t in change_types)
                html_parts.append(f'<div style="margin: 8px 0;"><strong>Action:</strong> {types_str}</div>')

                # Show net changes
                if net_changes:
                    html_parts.append('<div style="margin: 8px 0;"><strong>Changes:</strong></div>')
                    for field, vals in net_changes.items():
                        label = field_labels.get(field, field.replace('_', ' ').title())
                        old_val = vals['old'] or '(none)'
                        new_val = vals['new'] or '(none)'
                        html_parts.append(
                            f'<div class="change-item">{label}: '
                            f'<span class="old-value">{old_val}</span> → '
                            f'<span class="new-value">{new_val}</span></div>'
                        )

                # Meta info
                html_parts.append(f'<div class="meta">Changed by: {", ".join(changed_by)}</div>')
                html_parts.append('</div>')
    else:
        html_parts.append('<p style="color: #666;">No actionable changes in this period.</p>')

    # ========== REVERSED CHANGES SECTION ==========
    if reversed_items:
        html_parts.append('<hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0 20px 0;">')
        html_parts.append(f'<h3 style="color: #888; margin-top: 20px;">Reversed Changes ({len(reversed_items)} game{"s" if len(reversed_items) != 1 else ""}) - No Action Needed</h3>')
        html_parts.append('<p class="reversed-note">These games were modified and then reverted to their original state within the time window. No action is required.</p>')

        for league in sorted(reversed_by_league.keys()):
            items = reversed_by_league[league]
            html_parts.append(f'<div class="section-header reversed">{league} ({len(items)} game{"s" if len(items) != 1 else ""})</div>')

            for item in items:
                game = item['game']
                changes = item['changes']
                changed_by = item['changed_by']

                # Game title
                game_date = game.game_date.strftime('%a, %b %d at %I:%M %p').replace(' 0', ' ') if game.game_date else 'TBD'
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'

                html_parts.append('<div class="game-card reversed">')
                html_parts.append(f'<div class="game-title">{home} vs {away}</div>')
                html_parts.append(f'<div>{game_date} at {game.field_name or "TBD"}</div>')
                html_parts.append(f'<div class="reversed-note">{len(changes)} change(s) made and reverted</div>')
                html_parts.append(f'<div class="meta">Changed by: {", ".join(changed_by)}</div>')
                html_parts.append('</div>')

    html_parts.extend([
        '<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">',
        '<p style="color: #888; font-size: 12px;">',
        'SDLL Automated Game Changes Digest<br>',
        f'Generated at {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}',
        '</p>',
        '</body></html>'
    ])

    return '\n'.join(html_parts)


def format_digest_text(changes_data, hours):
    """Generate plain text email for game changes digest.

    Args:
        changes_data: List from get_changes_with_net_effect()
        hours: Hours window for the digest

    Returns:
        Plain text string
    """
    if not changes_data:
        return None

    # Separate actionable changes from reversed changes
    actionable = [item for item in changes_data if not item.get('is_reversed')]
    reversed_items = [item for item in changes_data if item.get('is_reversed')]

    lines = [
        f"Game Changes Summary - Last {hours} Hour(s)",
        "=" * 50,
        ""
    ]

    field_labels = {
        'date': 'Date',
        'time': 'Time',
        'field': 'Field',
        'location': 'Field',
        'status': 'Status',
        'home_team': 'Home Team',
        'away_team': 'Away Team',
        'game_type': 'Game Type',
        'no_time_limit': 'Time Limit',
        'umpire_override': 'Umpire Partner'
    }

    # ========== ACTIONABLE CHANGES SECTION ==========
    if actionable:
        lines.append(f"ACTION REQUIRED ({len(actionable)} game(s))")
        lines.append("=" * 50)

        # Group by league
        by_league = defaultdict(list)
        for item in actionable:
            league = item['game'].league or 'Unknown'
            by_league[league].append(item)

        for league in sorted(by_league.keys()):
            items = by_league[league]
            lines.append(f"\n{league} ({len(items)} game(s))")
            lines.append("-" * 30)

            for item in items:
                game = item['game']
                net_changes = item['net_changes']
                change_types = item['change_types']
                changed_by = item['changed_by']

                game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'

                lines.append(f"\n  {home} vs {away}")
                lines.append(f"  {game_date} at {game.field_name or 'TBD'}")
                lines.append(f"  Action: {', '.join(change_types)}")

                if net_changes:
                    lines.append("  Changes:")
                    for field, vals in net_changes.items():
                        label = field_labels.get(field, field)
                        old_val = vals['old'] or '(none)'
                        new_val = vals['new'] or '(none)'
                        lines.append(f"    - {label}: {old_val} -> {new_val}")

                lines.append(f"  Changed by: {', '.join(changed_by)}")
    else:
        lines.append("No actionable changes in this period.")

    # ========== REVERSED CHANGES SECTION ==========
    if reversed_items:
        lines.append("")
        lines.append("=" * 50)
        lines.append(f"REVERSED CHANGES ({len(reversed_items)} game(s)) - NO ACTION NEEDED")
        lines.append("=" * 50)
        lines.append("These games were modified and then reverted to their original state.")
        lines.append("")

        # Group by league
        reversed_by_league = defaultdict(list)
        for item in reversed_items:
            league = item['game'].league or 'Unknown'
            reversed_by_league[league].append(item)

        for league in sorted(reversed_by_league.keys()):
            items = reversed_by_league[league]
            lines.append(f"\n{league} ({len(items)} game(s))")
            lines.append("-" * 30)

            for item in items:
                game = item['game']
                changes = item['changes']
                changed_by = item['changed_by']

                game_date = game.game_date.strftime('%a, %b %d at %I:%M %p') if game.game_date else 'TBD'
                home = game.home_team.computed_display_name if game.home_team else 'TBD'
                away = game.away_team.computed_display_name if game.away_team else 'TBD'

                lines.append(f"\n  {home} vs {away}")
                lines.append(f"  {game_date} at {game.field_name or 'TBD'}")
                lines.append(f"  ({len(changes)} change(s) made and reverted)")
                lines.append(f"  Changed by: {', '.join(changed_by)}")

    lines.extend([
        "",
        "-" * 50,
        "SDLL Automated Game Changes Digest"
    ])

    return '\n'.join(lines)


def send_game_changes_digest(hours=2, force=False):
    """Send game changes digest email.

    Args:
        hours: Look back this many hours for changes
        force: If True, send even if no changes

    Returns:
        Dict with status info
    """
    from app.services.notification_service import GmailService

    result = {
        'sent': False,
        'change_count': 0,
        'game_count': 0,
        'recipients': [],
        'error': None
    }

    try:
        # Get changes with net effect
        changes_data = get_changes_with_net_effect(hours)
        result['game_count'] = len(changes_data)
        result['change_count'] = sum(len(item['changes']) for item in changes_data)

        # Skip if no changes and not forcing
        if not changes_data and not force:
            result['sent'] = False
            return result

        # Generate email content
        html_content = format_digest_html(changes_data, hours)
        text_content = format_digest_text(changes_data, hours)

        if not html_content:
            if force:
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>SDLL Game Changes Digest</h2>
                <p>No game changes in the last {hours} hours.</p>
                </body>
                </html>
                """
                text_content = f"SDLL Game Changes Digest\n\nNo game changes in the last {hours} hours."
            else:
                return result

        # Send email
        gmail = GmailService()
        if not gmail.is_configured:
            result['error'] = 'Email service not configured'
            return result

        recipients = get_recipient_emails()
        result['recipients'] = recipients

        subject = f"SDLL Game Changes - {result['game_count']} game(s) modified"
        if result['game_count'] == 0:
            subject = "SDLL Game Changes - No changes"

        # Send to first recipient, CC the rest
        primary = recipients[0]
        cc_list = recipients[1:] if len(recipients) > 1 else None

        try:
            gmail.send_email(
                to=primary,
                subject=subject,
                body_text=text_content,
                body_html=html_content,
                cc=cc_list
            )
            print(f"Game changes digest sent to {primary}" + (f" (cc: {', '.join(cc_list)})" if cc_list else ""))
        except Exception as e:
            result['error'] = str(e)
            return result

        result['sent'] = True
        return result

    except Exception as e:
        result['error'] = str(e)
        return result
