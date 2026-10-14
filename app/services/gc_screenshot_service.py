"""GameChanger Screenshot Service - parses box score screenshots using Claude vision API.

This service handles:
- Image upload and storage (base64)
- Claude API calls for image parsing
- Edit diff computation for audit tracking
"""

import os
import json
import uuid
import base64
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from app.extensions import db
from app.models.gc_screenshot_session import GCScreenshotSession
from app.models.player import PlayerSeason


@dataclass
class ParsedPitcher:
    """Parsed pitcher data from screenshot."""
    name: str
    player_code: Optional[str]
    pitches_thrown: int
    innings_pitched: Optional[float]
    strikes_thrown: Optional[int]
    batters_faced: Optional[int]
    runs_allowed: Optional[int]
    strikeouts: Optional[int]
    walks: Optional[int]


@dataclass
class ParsedGameData:
    """Parsed game data from screenshot."""
    our_score: int
    opponent_score: int
    pitchers: List[ParsedPitcher]
    confidence: float
    warnings: List[str]


class GCScreenshotService:
    """Service for parsing GameChanger screenshots using Claude vision API."""

    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-haiku-5-5"
    DEFAULT_TIMEOUT = 30  # Default timeout in seconds
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_CONTENT_TYPES = ['image/png', 'image/jpeg', 'image/webp']

    @classmethod
    def get_dynamic_timeout(cls) -> int:
        """Get dynamic timeout based on historical response times.

        Uses mean + 3 standard deviations from successful calls.
        Falls back to DEFAULT_TIMEOUT if insufficient data.

        Returns:
            Timeout in seconds (rounded up)
        """
        threshold_ms = GCScreenshotSession.get_timeout_threshold_ms(
            default_ms=cls.DEFAULT_TIMEOUT * 1000
        )
        # Convert to seconds, add a small buffer, round up
        return max(cls.DEFAULT_TIMEOUT, int(threshold_ms / 1000) + 1)

    @classmethod
    def get_response_time_info(cls) -> dict:
        """Get response time statistics for monitoring/display.

        Returns:
            Dict with stats or None if insufficient data
        """
        stats = GCScreenshotSession.get_response_time_stats()
        if stats is None:
            return {
                'has_data': False,
                'message': 'Insufficient data for response time statistics'
            }

        return {
            'has_data': True,
            'mean_seconds': round(stats['mean_ms'] / 1000, 1),
            'std_dev_seconds': round(stats['std_dev_ms'] / 1000, 1),
            'timeout_threshold_seconds': round(stats['timeout_threshold_ms'] / 1000, 1),
            'sample_count': stats['sample_count'],
            'min_seconds': round(stats['min_ms'] / 1000, 1),
            'max_seconds': round(stats['max_ms'] / 1000, 1)
        }

    @classmethod
    def is_configured(cls) -> bool:
        """Check if ANTHROPIC_API_KEY is set."""
        return bool(os.environ.get('ANTHROPIC_API_KEY'))

    @classmethod
    def create_session(
        cls,
        game_id: int,
        team_id: int,
        user_id: int,
        session_uuid: str = None
    ) -> GCScreenshotSession:
        """Create a new audit session for tracking.

        Args:
            game_id: The game ID
            team_id: The team ID
            user_id: The user ID
            session_uuid: Optional existing session UUID for retries

        Returns:
            New GCScreenshotSession record
        """
        # If session_uuid provided, find the latest attempt number
        attempt_number = 1
        if session_uuid:
            existing = GCScreenshotSession.query.filter_by(
                session_uuid=session_uuid
            ).order_by(GCScreenshotSession.attempt_number.desc()).first()
            if existing:
                attempt_number = existing.attempt_number + 1

        # Create new session UUID if not retrying
        if not session_uuid:
            session_uuid = str(uuid.uuid4())

        session = GCScreenshotSession(
            session_uuid=session_uuid,
            attempt_number=attempt_number,
            game_id=game_id,
            team_id=team_id,
            user_id=user_id,
            status=GCScreenshotSession.STATUS_PENDING
        )
        db.session.add(session)
        db.session.commit()
        return session

    @classmethod
    def validate_image(cls, file_data: bytes, content_type: str, filename: str) -> Tuple[bool, str]:
        """Validate uploaded image.

        Args:
            file_data: Raw file bytes
            content_type: MIME type
            filename: Original filename

        Returns:
            (is_valid, error_message)
        """
        if not file_data:
            return False, "No file data provided"

        if len(file_data) > cls.MAX_FILE_SIZE:
            return False, f"File too large. Maximum size is {cls.MAX_FILE_SIZE // (1024*1024)}MB"

        if content_type not in cls.ALLOWED_CONTENT_TYPES:
            allowed = ', '.join(cls.ALLOWED_CONTENT_TYPES)
            return False, f"Invalid file type. Allowed: {allowed}"

        return True, ""

    @classmethod
    def store_image(
        cls,
        session: GCScreenshotSession,
        file_data: bytes,
        filename: str,
        content_type: str
    ) -> None:
        """Store base64 image in session record.

        Args:
            session: The session to update
            file_data: Raw file bytes
            filename: Original filename
            content_type: MIME type
        """
        session.image_data = base64.b64encode(file_data).decode('utf-8')
        session.image_filename = filename
        session.image_content_type = content_type
        db.session.commit()

    @classmethod
    def get_roster_for_prompt(cls, team_id: int) -> List[Dict]:
        """Get roster formatted for prompt.

        Args:
            team_id: The team ID

        Returns:
            List of dicts with player_code, player_id, and name
        """
        from sqlalchemy.orm import joinedload

        players = PlayerSeason.query.filter_by(team_id=team_id).options(
            joinedload(PlayerSeason.player)
        ).all()

        roster = []
        for ps in players:
            if ps.player:
                roster.append({
                    'player_id': ps.player.id,
                    'player_code': ps.player.player_code,
                    'name': ps.player.full_name,
                    'first_name': ps.player.first_name,
                    'last_name': ps.player.last_name,
                })

        # Sort by last name
        roster.sort(key=lambda x: x.get('last_name', ''))
        return roster

    @classmethod
    def build_prompt(cls, team_name: str, opponent_name: str, roster: List[Dict]) -> str:
        """Build prompt with roster context for Claude.

        Args:
            team_name: Our team's name
            opponent_name: Opponent's name
            roster: List of player dicts

        Returns:
            Formatted prompt string
        """
        roster_str = '\n'.join([
            f"  - {p['name']} ({p['player_code']})"
            for p in roster
        ])

        prompt = f"""Analyze this GameChanger box score screenshot and extract the game data.

CONTEXT:
- Our team: {team_name}
- Opponent: {opponent_name}
- Our roster (use player_code to identify):
{roster_str}

EXTRACT:
1. Final score for both teams
2. Pitching statistics for OUR team's pitchers only

IMPORTANT:
- Match pitcher names to our roster and include the player_code
- If you can't confidently match a name, include the name as-is with player_code: null
- Only extract data that is clearly visible in the screenshot
- Set confidence based on image quality and clarity

RESPOND WITH VALID JSON ONLY (no markdown, no explanation):
{{
  "game": {{
    "our_score": <integer>,
    "opponent_score": <integer>
  }},
  "pitchers": [
    {{
      "name": "<player name as shown or matched>",
      "player_code": "<from roster or null if uncertain>",
      "pitches_thrown": <integer>,
      "innings_pitched": <decimal like 2.1 or null if not visible>,
      "strikes_thrown": <integer or null>,
      "batters_faced": <integer or null>,
      "runs_allowed": <integer or null>,
      "strikeouts": <integer or null>,
      "walks": <integer or null>
    }}
  ],
  "confidence": <0.0 to 1.0>,
  "warnings": ["<any issues or uncertainties>"]
}}"""
        return prompt

    @classmethod
    def parse_screenshot(
        cls,
        session: GCScreenshotSession,
        team_name: str,
        opponent_name: str,
        roster: List[Dict]
    ) -> Tuple[Optional[ParsedGameData], Optional[str]]:
        """Send screenshot to Claude API and parse response.

        Args:
            session: The session record (must have image_data)
            team_name: Our team's name
            opponent_name: Opponent's name
            roster: List of player dicts

        Returns:
            (ParsedGameData, error_message) - one will be None
        """
        if not cls.is_configured():
            return None, "Anthropic API key not configured"

        if not session.image_data:
            return None, "No image data in session"

        # Update status
        session.status = GCScreenshotSession.STATUS_PARSING
        db.session.commit()

        # Build prompt
        prompt = cls.build_prompt(team_name, opponent_name, roster)
        session.prompt_sent = prompt
        db.session.commit()

        # Prepare API request
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            session.status = GCScreenshotSession.STATUS_ERROR
            session.error_message = "ANTHROPIC_API_KEY environment variable is not set"
            db.session.commit()
            return None, "API key not configured"

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        }

        # Build message with image
        media_type = session.image_content_type or 'image/png'
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": session.image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]

        payload = {
            "model": cls.MODEL,
            "max_tokens": 10000,
            "messages": messages
        }

        # Debug logging - print to console for debugging
        print(f"[GC Screenshot] API call starting...")
        print(f"[GC Screenshot] Model: {cls.MODEL}")
        print(f"[GC Screenshot] URL: {cls.ANTHROPIC_API_URL}")
        print(f"[GC Screenshot] API key present: {bool(api_key)}")
        if api_key:
            print(f"[GC Screenshot] API key prefix: {api_key[:15]}...")
        print(f"[GC Screenshot] Image size: {len(session.image_data)} base64 chars")

        try:
            # Time the API call for performance tracking
            start_time = time.time()

            # Use dynamic timeout based on historical response times
            timeout = cls.get_dynamic_timeout()
            print(f"[GC Screenshot] Using timeout: {timeout}s")

            response = requests.post(
                cls.ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout
            )

            # Calculate and store response time
            response_time_ms = int((time.time() - start_time) * 1000)
            session.llm_response_time_ms = response_time_ms
            db.session.commit()

            # Log response details for debugging
            print(f"[GC Screenshot] Response status: {response.status_code}")
            print(f"[GC Screenshot] Response time: {response_time_ms}ms")
            print(f"[GC Screenshot] Response headers: {dict(response.headers)}")

            if response.status_code != 200:
                error_detail = response.text[:1000] if response.text else 'No response body'
                print(f"[GC Screenshot] Error response body: {error_detail}")
                session.status = GCScreenshotSession.STATUS_ERROR
                session.error_message = f"API returned {response.status_code}: {error_detail}"
                db.session.commit()
                return None, f"API error ({response.status_code}): {error_detail}"

            result = response.json()

            # Extract text response
            response_text = ""
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    response_text = block.get('text', '')
                    break

            session.llm_response = response_text
            db.session.commit()

            # Parse JSON response - handle potential markdown code blocks
            json_text = response_text.strip()

            # Remove markdown code blocks if present
            if json_text.startswith('```'):
                # Find the end of the opening fence
                first_newline = json_text.find('\n')
                if first_newline != -1:
                    json_text = json_text[first_newline + 1:]
                # Remove closing fence
                if json_text.endswith('```'):
                    json_text = json_text[:-3].strip()
                elif '```' in json_text:
                    json_text = json_text[:json_text.rfind('```')].strip()

            try:
                parsed = json.loads(json_text)
            except json.JSONDecodeError as e:
                print(f"[GC Screenshot] JSON parse error: {e}")
                print(f"[GC Screenshot] Raw response (first 500 chars): {response_text[:500]}")
                session.status = GCScreenshotSession.STATUS_ERROR
                session.error_message = f"Invalid JSON response: {str(e)}"
                db.session.commit()
                return None, "Failed to parse AI response. Please try again with a clearer screenshot."

            # Convert to ParsedGameData
            game_data = parsed.get('game', {})
            pitchers_data = parsed.get('pitchers', [])

            pitchers = []
            for p in pitchers_data:
                pitchers.append(ParsedPitcher(
                    name=p.get('name', ''),
                    player_code=p.get('player_code'),
                    pitches_thrown=p.get('pitches_thrown', 0),
                    innings_pitched=p.get('innings_pitched'),
                    strikes_thrown=p.get('strikes_thrown'),
                    batters_faced=p.get('batters_faced'),
                    runs_allowed=p.get('runs_allowed'),
                    strikeouts=p.get('strikeouts'),
                    walks=p.get('walks')
                ))

            parsed_data = ParsedGameData(
                our_score=game_data.get('our_score', 0),
                opponent_score=game_data.get('opponent_score', 0),
                pitchers=pitchers,
                confidence=parsed.get('confidence', 0.5),
                warnings=parsed.get('warnings', [])
            )

            # Store parsed JSON
            session.parsed_json = parsed
            session.parsed_at = datetime.utcnow()
            session.status = GCScreenshotSession.STATUS_PARSED
            db.session.commit()

            return parsed_data, None

        except requests.exceptions.Timeout:
            print("[GC Screenshot] ERROR: Request timed out")
            session.status = GCScreenshotSession.STATUS_ERROR
            session.error_message = "Request timed out"
            db.session.commit()
            return None, "Request timed out. Please try again."

        except requests.exceptions.HTTPError as e:
            # This shouldn't happen since we don't call raise_for_status()
            print(f"[GC Screenshot] ERROR: HTTPError caught: {e}")
            print(f"[GC Screenshot] HTTPError response: {e.response.text if e.response else 'No response'}")
            session.status = GCScreenshotSession.STATUS_ERROR
            session.error_message = f"HTTPError: {str(e)}"
            db.session.commit()
            return None, f"HTTP Error: {str(e)}"

        except requests.exceptions.RequestException as e:
            print(f"[GC Screenshot] ERROR: RequestException caught: {type(e).__name__}: {e}")
            session.status = GCScreenshotSession.STATUS_ERROR
            session.error_message = f"{type(e).__name__}: {str(e)}"
            db.session.commit()
            return None, f"API request failed: {str(e)}"

        except Exception as e:
            print(f"[GC Screenshot] ERROR: Unexpected exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            session.status = GCScreenshotSession.STATUS_ERROR
            session.error_message = f"{type(e).__name__}: {str(e)}"
            db.session.commit()
            return None, f"Unexpected error: {str(e)}"

    @classmethod
    def compute_edit_diff(cls, parsed_json: dict, final_json: dict) -> dict:
        """Compare parsed vs submitted data, field-by-field.

        Args:
            parsed_json: Original parsed data from LLM
            final_json: Final submitted data from user

        Returns:
            Structured diff for audit/QC
        """
        diff = {
            "has_changes": False,
            "summary": {
                "fields_changed": 0,
                "pitchers_modified": 0,
                "pitchers_added": 0,
                "pitchers_removed": 0
            },
            "game_changes": [],
            "pitcher_changes": []
        }

        # Compare game-level fields
        parsed_game = parsed_json.get('game', {})
        for field in ['our_score', 'opponent_score']:
            parsed_val = parsed_game.get(field)
            # Final JSON has flat structure from form
            final_val = final_json.get(field)

            change_type = 'unchanged' if parsed_val == final_val else 'modified'
            diff['game_changes'].append({
                'field': field,
                'parsed': parsed_val,
                'final': final_val,
                'type': change_type
            })

            if change_type != 'unchanged':
                diff['has_changes'] = True
                diff['summary']['fields_changed'] += 1

        # Compare pitchers by player_code
        parsed_pitchers = {
            p.get('player_code'): p
            for p in parsed_json.get('pitchers', [])
            if p.get('player_code')
        }
        final_pitchers = {
            p.get('player_code'): p
            for p in final_json.get('pitchers', [])
            if p.get('player_code')
        }

        # All player codes
        all_codes = set(parsed_pitchers.keys()) | set(final_pitchers.keys())

        pitcher_fields = ['pitches_thrown', 'innings_pitched', 'strikes_thrown', 'batters_faced', 'runs_allowed', 'strikeouts', 'walks']

        for code in all_codes:
            parsed_p = parsed_pitchers.get(code)
            final_p = final_pitchers.get(code)

            if parsed_p and final_p:
                # Both exist - check for field changes
                field_changes = []
                for field in pitcher_fields:
                    pval = parsed_p.get(field)
                    fval = final_p.get(field)
                    change_type = 'unchanged' if pval == fval else 'modified'
                    if change_type != 'unchanged':
                        diff['has_changes'] = True
                        diff['summary']['fields_changed'] += 1
                    field_changes.append({
                        'field': field,
                        'parsed': pval,
                        'final': fval,
                        'type': change_type
                    })

                status = 'matched'
                if any(fc['type'] != 'unchanged' for fc in field_changes):
                    status = 'modified'
                    diff['summary']['pitchers_modified'] += 1

                diff['pitcher_changes'].append({
                    'player_code': code,
                    'player_name': final_p.get('name', parsed_p.get('name', '')),
                    'status': status,
                    'fields': field_changes
                })

            elif parsed_p and not final_p:
                # Removed by coach
                diff['has_changes'] = True
                diff['summary']['pitchers_removed'] += 1
                diff['pitcher_changes'].append({
                    'player_code': code,
                    'player_name': parsed_p.get('name', ''),
                    'status': 'removed',
                    'fields': []
                })

            elif final_p and not parsed_p:
                # Added by coach
                diff['has_changes'] = True
                diff['summary']['pitchers_added'] += 1
                diff['pitcher_changes'].append({
                    'player_code': code,
                    'player_name': final_p.get('name', ''),
                    'status': 'added',
                    'fields': []
                })

        return diff

    @classmethod
    def record_submission(
        cls,
        session: GCScreenshotSession,
        final_data: dict
    ) -> None:
        """Record final submitted data for audit comparison.

        Args:
            session: The session record
            final_data: Final submitted data dict
        """
        session.final_submitted_json = final_data

        # Compute diff if we have parsed data
        if session.parsed_json:
            diff = cls.compute_edit_diff(session.parsed_json, final_data)
            session.edit_diff = diff
            session.was_edited = 1 if diff['has_changes'] else 0
        else:
            session.was_edited = 0

        session.status = GCScreenshotSession.STATUS_SUBMITTED
        session.submission_successful = 1
        session.submitted_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def mark_abandoned(cls, session: GCScreenshotSession) -> None:
        """Mark session as abandoned (user switched to manual entry).

        Args:
            session: The session record
        """
        session.status = GCScreenshotSession.STATUS_ABANDONED
        db.session.commit()
