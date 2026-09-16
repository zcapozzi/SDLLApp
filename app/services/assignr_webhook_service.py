"""Assignr Webhook Processing Service.

Handles:
1. Webhook signature verification (HMAC-SHA256)
2. Event processing (fetching details from Assignr API)
3. Alert notifications for late umpire acceptances
"""

import hmac
import hashlib
import os
import json
from datetime import datetime, timedelta
from typing import Tuple, Optional, List

from app.extensions import db
from app.models.assignr_webhook_event import AssignrWebhookEvent
from app.models.game import Game
from app.models.user import User
from app.services.assignr_service import get_assignr_service
from app.services.notification_service import GmailService
from app.utils.logging import SDLLLogger

logger = SDLLLogger('assignr_webhook')


class AssignrWebhookService:
    """Service for processing Assignr webhooks."""

    # Alert threshold in hours
    ALERT_THRESHOLD_HOURS = 48

    def __init__(self):
        self.assignr = get_assignr_service()
        self.email_service = GmailService()

    def verify_signature(self, request) -> Tuple[bool, Optional[str]]:
        """
        Verify Assignr webhook signature.

        Header format: X-Hook0-Signature: t=<timestamp>,h=x-event-id x-event-type,v1=<signature>
        Signed string: {timestamp}.x-event-id x-event-type.{event_id}.{topic}.{body}

        Args:
            request: Flask request object

        Returns:
            Tuple of (is_valid, error_message)
        """
        secret = os.environ.get('ASSIGNR_WEBHOOK_SECRET')
        if not secret:
            logger.warning("ASSIGNR_WEBHOOK_SECRET not configured")
            return False, "Webhook secret not configured"

        signature_header = request.headers.get('X-Hook0-Signature', '')
        if not signature_header:
            return False, "Missing signature header"

        # Parse the signature header components
        # Format: t=<timestamp>,h=x-event-id x-event-type,v1=<signature>
        parts = {}
        for part in signature_header.split(','):
            if '=' in part:
                key, value = part.split('=', 1)
                parts[key] = value

        timestamp = parts.get('t')
        headers_to_sign = parts.get('h', '')
        signature = parts.get('v1')

        if not all([timestamp, signature]):
            return False, "Invalid signature header format"

        # Verify timestamp is recent (within 5 minutes)
        try:
            ts = int(timestamp)
            now = int(datetime.now().timestamp())
            if abs(now - ts) > 300:  # 5 minutes
                return False, "Signature timestamp expired"
        except ValueError:
            return False, "Invalid timestamp"

        # Get event details from headers
        event_id = request.headers.get('X-Event-Id', '')
        event_type = request.headers.get('X-Event-Type', '')

        # Get request body
        body = request.get_data(as_text=True)

        # Construct the signed string
        # Format: {timestamp}.x-event-id x-event-type.{event_id}.{topic}.{body}
        signed_string = f"{timestamp}.{headers_to_sign}.{event_id}.{event_type}.{body}"

        # Calculate expected signature
        expected = hmac.new(
            secret.encode('utf-8'),
            signed_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison
        if not hmac.compare_digest(expected, signature):
            logger.warning(f"Signature mismatch for event {event_id}")
            return False, "Invalid signature"

        return True, None

    def parse_webhook_payload(self, request) -> Tuple[Optional[dict], Optional[str]]:
        """
        Parse and validate webhook payload.

        Args:
            request: Flask request object

        Returns:
            Tuple of (payload_dict, error_message)
        """
        try:
            payload = request.get_json(force=True)
            if not payload:
                return None, "Empty payload"

            # Validate required fields
            if 'id' not in payload:
                return None, "Missing event ID"
            if 'topic' not in payload:
                return None, "Missing topic"

            return payload, None

        except json.JSONDecodeError as e:
            return None, f"Invalid JSON: {e}"

    def extract_ids_from_payload(self, payload: dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract game ID and assignment ID from webhook payload links.

        Args:
            payload: Parsed webhook payload

        Returns:
            Tuple of (game_id, assignment_id)
        """
        links = payload.get('_links', {})

        # Extract assignment ID from resource link
        assignment_id = None
        resource_link = links.get('resource', {})
        resource_href = resource_link.get('href', '')
        if '/assignments/' in resource_href:
            # Extract ID from URL like ".../assignments/12345"
            try:
                assignment_id = resource_href.split('/assignments/')[-1].split('/')[0].split('?')[0]
            except (IndexError, AttributeError):
                pass

        # Extract game ID from game link
        game_id = None
        game_link = links.get('game', {})
        game_href = game_link.get('href', '')
        if '/games/' in game_href:
            try:
                game_id = game_href.split('/games/')[-1].split('/')[0].split('?')[0]
            except (IndexError, AttributeError):
                pass

        return game_id, assignment_id

    def store_event(
        self,
        event_id: int,
        topic: str,
        payload: dict,
        game_id: Optional[str] = None,
        assignment_id: Optional[str] = None
    ) -> AssignrWebhookEvent:
        """
        Store webhook event in database.

        Args:
            event_id: Assignr webhook event ID
            topic: Event topic
            payload: Full payload dict
            game_id: Extracted Assignr game ID
            assignment_id: Extracted assignment ID

        Returns:
            AssignrWebhookEvent instance
        """
        # Check for duplicate
        existing = AssignrWebhookEvent.get_by_event_id(event_id)
        if existing:
            logger.info(f"Duplicate webhook event {event_id}, skipping")
            return existing

        event = AssignrWebhookEvent.create_from_webhook(
            event_id=event_id,
            topic=topic,
            payload=json.dumps(payload),
            assignr_game_id=game_id,
            assignr_assignment_id=assignment_id
        )

        # Parse and store the event timestamp from payload
        event.set_event_timestamp_from_payload()

        db.session.commit()

        logger.info(f"Stored webhook event {event_id}: {topic}")
        return event

    def process_event(self, event: AssignrWebhookEvent) -> bool:
        """
        Process a webhook event.

        Args:
            event: AssignrWebhookEvent to process

        Returns:
            True if processed successfully
        """
        if event.topic != 'game.official.changed':
            event.mark_ignored(f"Unsupported topic: {event.topic}")
            return True

        event.mark_processing()

        try:
            return self._process_official_changed(event)
        except Exception as e:
            logger.error(f"Failed to process event {event.id}: {e}")
            event.mark_failed(str(e))
            return False

    def _process_official_changed(self, event: AssignrWebhookEvent) -> bool:
        """
        Process a game.official.changed event.

        1. Fetch assignment details from Assignr API
        2. Fetch game details to get start time
        3. Find local game by assignr_id
        4. Determine action type (accepted, declined, removed, etc.)
        5. Check if accepted AND within 48 hours
        6. Send notification if needed

        Args:
            event: AssignrWebhookEvent being processed

        Returns:
            True if processed successfully
        """
        game_id = event.assignr_game_id
        assignment_id = event.assignr_assignment_id

        if not game_id:
            event.mark_ignored("No game ID in payload")
            return True

        # Fetch assignment details from Assignr API
        assignment_data = None
        if assignment_id:
            assignments = self.assignr.get_game_officials(int(game_id))
            for a in assignments:
                if str(a.get('id')) == str(assignment_id):
                    assignment_data = a
                    break

        # Determine action type and official info
        is_accepted = False
        official_name = "Unknown"
        position = "Unknown"
        action_type = "removed"  # Default if assignment not found (was removed)

        if assignment_data:
            embedded = assignment_data.get('_embedded', {}) or {}
            official = embedded.get('official', {}) or {}
            first_name = official.get('first_name', '')
            last_name = official.get('last_name', '')
            official_name = f"{first_name} {last_name}".strip() or "Unknown"
            position = assignment_data.get('position', 'Unknown')

            # Determine action type based on assignment state
            accepted = assignment_data.get('accepted')
            declined = assignment_data.get('declined')

            if accepted in [True, 'True', 'true']:
                action_type = "accepted"
                is_accepted = True
            elif declined in [True, 'True', 'true']:
                action_type = "declined"
            else:
                # Assignment exists but not accepted/declined = pending/assigned
                action_type = "assigned"
        else:
            logger.info(f"Assignment {assignment_id} not found in game {game_id} - likely removed")
            # Assignment not found = was removed

        # Fetch game details
        game_data = self.assignr.get_game(int(game_id))
        if not game_data:
            event.mark_failed(f"Could not fetch game {game_id} from Assignr")
            return False

        # Parse game start time
        game_datetime = self.assignr._parse_game_datetime(game_data)
        if not game_datetime:
            event.mark_failed(f"Could not parse game start time")
            return False

        # Find local game
        local_game = Game.query.filter_by(assignr_id=str(game_id), active=1).first()
        local_game_id = local_game.ID if local_game else None

        # Check if we should send an alert
        should_alert, reason = self._should_send_alert(game_datetime, is_accepted)

        notification_sent = False
        if should_alert:
            notification_sent = self._send_alert(
                event=event,
                game_data=game_data,
                local_game=local_game,
                official_name=official_name,
                position=position,
                hours_until_game=self._hours_until(game_datetime)
            )

        event.mark_completed(
            local_game_id=local_game_id,
            notification_sent=notification_sent,
            notification_reason=reason,
            official_name=official_name,
            action_type=action_type,
            position=position
        )

        return True

    def _should_send_alert(
        self,
        game_datetime: datetime,
        is_accepted: bool
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if an alert should be sent.

        Args:
            game_datetime: When the game starts
            is_accepted: Whether the assignment was accepted

        Returns:
            Tuple of (should_send, reason)
        """
        if not is_accepted:
            return False, None

        hours_until_game = self._hours_until(game_datetime)

        # Game must be in the future and within threshold
        if hours_until_game <= 0:
            return False, None

        if hours_until_game <= self.ALERT_THRESHOLD_HOURS:
            return True, f"accepted_within_{int(hours_until_game)}h"

        return False, None

    def _hours_until(self, game_datetime: datetime) -> float:
        """Calculate hours until a game."""
        delta = game_datetime - datetime.now()
        return delta.total_seconds() / 3600

    def _send_alert(
        self,
        event: AssignrWebhookEvent,
        game_data: dict,
        local_game: Optional[Game],
        official_name: str,
        position: str,
        hours_until_game: float
    ) -> bool:
        """
        Send alert email to umpire coordinators.

        Args:
            event: The webhook event
            game_data: Game data from Assignr
            local_game: Local game record if found
            official_name: Name of the umpire
            position: Position (Plate, Base, etc.)
            hours_until_game: Hours until game starts

        Returns:
            True if email sent successfully
        """
        # Get recipients - all users with umpire_coordinator role
        coordinators = self._get_umpire_coordinators()
        if not coordinators:
            logger.warning("No umpire coordinators found for alert notification")
            return False

        # Build email content
        subject, body_text, body_html = self._build_alert_email(
            game_data=game_data,
            local_game=local_game,
            official_name=official_name,
            position=position,
            hours_until_game=hours_until_game
        )

        # Send to all coordinators
        recipient_emails = [c.email for c in coordinators if c.email]
        if not recipient_emails:
            logger.warning("No valid email addresses for umpire coordinators")
            return False

        try:
            # Send to first coordinator, CC others
            primary = recipient_emails[0]
            cc = recipient_emails[1:] if len(recipient_emails) > 1 else None

            self.email_service.send_email(
                to=primary,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                cc=cc
            )
            logger.info(f"Sent late acceptance alert to {len(recipient_emails)} coordinators")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    def _get_umpire_coordinators(self) -> List[User]:
        """Get all users with umpire_coordinator or admin role."""
        users = User.query.filter(User.active == 1).all()
        return [u for u in users if u.has_role('admin', 'umpire_coordinator')]

    def _build_alert_email(
        self,
        game_data: dict,
        local_game: Optional[Game],
        official_name: str,
        position: str,
        hours_until_game: float
    ) -> Tuple[str, str, str]:
        """
        Build alert email content.

        Returns:
            Tuple of (subject, body_text, body_html)
        """
        # Extract game details
        game_datetime = self.assignr._parse_game_datetime(game_data)
        game_date_str = game_datetime.strftime('%A, %B %d, %Y') if game_datetime else 'Unknown'
        game_time_str = game_datetime.strftime('%I:%M %p').lstrip('0') if game_datetime else 'Unknown'

        # Get field and teams from local game or Assignr data
        if local_game:
            league = local_game.league or 'Unknown'
            field_name = local_game.field_name or 'Unknown'
            home_team = local_game.home_team.computed_display_name if local_game.home_team else 'TBD'
            away_team = local_game.away_team.computed_display_name if local_game.away_team else 'TBD'
        else:
            league = game_data.get('league_name', 'Unknown')
            field_name = game_data.get('venue_name', 'Unknown')
            home_team = game_data.get('home_team', 'TBD')
            away_team = game_data.get('away_team', 'TBD')

        hours_display = int(hours_until_game) if hours_until_game >= 1 else '<1'

        subject = f"Late Umpire Acceptance: {league} Game in {hours_display} hours"

        body_text = f"""An umpire just accepted a game assignment with less than 48 hours notice:

Game Details:
- League: {league}
- Date/Time: {game_date_str} at {game_time_str}
- Location: {field_name}
- Teams: {home_team} vs {away_team}

Umpire:
- Name: {official_name}
- Position: {position}

Time until game: {hours_display} hours

---
SDLL Umpire Management
"""

        body_html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; color: #333; }}
        .alert-header {{ background: #ff9800; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
        .content {{ padding: 20px; background: #f9f9f9; border-radius: 0 0 5px 5px; }}
        .detail {{ margin: 10px 0; }}
        .label {{ font-weight: bold; color: #666; }}
        .urgent {{ color: #d32f2f; font-weight: bold; }}
        .footer {{ margin-top: 20px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="alert-header">
        <h2 style="margin: 0;">Late Umpire Acceptance Alert</h2>
    </div>
    <div class="content">
        <p>An umpire just accepted a game assignment with less than 48 hours notice:</p>

        <h3>Game Details</h3>
        <div class="detail"><span class="label">League:</span> {league}</div>
        <div class="detail"><span class="label">Date/Time:</span> {game_date_str} at {game_time_str}</div>
        <div class="detail"><span class="label">Location:</span> {field_name}</div>
        <div class="detail"><span class="label">Teams:</span> {home_team} vs {away_team}</div>

        <h3>Umpire</h3>
        <div class="detail"><span class="label">Name:</span> {official_name}</div>
        <div class="detail"><span class="label">Position:</span> {position}</div>

        <p class="urgent">Time until game: {hours_display} hours</p>

        <div class="footer">
            <p>SDLL Umpire Management System</p>
        </div>
    </div>
</body>
</html>
"""

        return subject, body_text, body_html

    def process_pending_events(self, limit: int = 10) -> dict:
        """
        Process pending webhook events.

        Args:
            limit: Maximum events to process

        Returns:
            Dict with processing results
        """
        events = AssignrWebhookEvent.get_pending(limit=limit)

        results = {
            'processed': 0,
            'failed': 0,
            'total': len(events)
        }

        for event in events:
            if self.process_event(event):
                results['processed'] += 1
            else:
                results['failed'] += 1

        return results


# Singleton instance
_webhook_service = None


def get_webhook_service() -> AssignrWebhookService:
    """Get the singleton webhook service instance."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = AssignrWebhookService()
    return _webhook_service
