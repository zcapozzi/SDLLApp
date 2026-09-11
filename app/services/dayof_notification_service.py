"""Service for generating and sending day-of umpire pregame emails."""

from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple

from app.extensions import db
from app.models.umpire_dayof_notification import UmpireDayOfNotification
from app.models.game import Game
from app.models.coach import CoachSeason
from app.models.league_season import LeagueSeason
from app.services.assignr_service import AssignrService
from app.services.notification_service import GmailService
from app.utils.logging import SDLLLogger

logger = SDLLLogger('dayof_notification')


# League display strings (more readable names)
LEAGUE_STRINGS = {
    'BB Intermediate': 'Intermediate (Kid Pitch BB)',
    'BB AAA': 'AAA (Kid Pitch BB)',
    'BB AA': 'AA (Kid Pitch BB)',
    'BB A': 'Upper Machine Pitch BB',
    'BB Rookie': 'Lower Machine Pitch BB',
    'SB Rookie': 'Lower Machine Pitch SB',
}

# Local rules links by league
LOCAL_RULES = {
    'BB Intermediate': 'https://docs.google.com/document/d/1UkkwToe73q11W56QHqAKn5bg54F3Dd95_HFgkY0jLqA/edit?usp=sharing',
    'BB AAA': 'https://docs.google.com/document/d/1EgrTOgyVpyckRJGqXNs9Kz3E8xDiDoWc_vhJffbCqgQ/edit?usp=sharing',
    'BB AA': 'https://docs.google.com/document/d/1wCZ1MUXID0hS5kx3tdk635iu3zL5xMdWaKKZuOOQfTs/edit?usp=sharing',
    'BB A': 'https://docs.google.com/document/d/1ZQh4K49FFATuNXSchtWYB1xRkDtDB0Q7N37ZIzYFjSk/edit?usp=sharing',
    'BB Rookie': 'https://docs.google.com/document/d/1_kIORPh9d2M4JI7oIVJDELcIr1zxjVzI8bVBvqmWXSM/edit?usp=sharing',
    'SB Rookie': 'https://docs.google.com/document/d/1J8WdiDF7nR_bGArUyewAKUOudBk7qwVe6W5JadEYBY4/edit?usp=sharing',
}
DEFAULT_RULES_LINK = 'https://tshq.bluesombrero.com/Default.aspx?tabid=2180637'

# Field zip codes for WeatherBug lightning links
FIELD_ZIP_CODES = {
    'Herndon 1': 'durham-nc-27713',
    'Parkwood': 'durham-nc-27713',
    'Herndon 2': 'durham-nc-27713',
    'Southern Boundaries 2': 'durham-nc-27707',
    'Hillside High School': 'durham-nc-27707',
    'Alston Ridge': 'cary-nc-27519',
    'Pineywood Park': 'durham-nc-27713',
    'Sherwood Githens Middle School': 'durham-nc-27707',
    'Ephesus Park': 'chapel-hill-nc-27517',
}
DEFAULT_ZIP = 'durham-nc-27707'


class DayOfNotificationService:
    """Service for managing day-of umpire pregame emails."""

    def __init__(self):
        self.assignr = AssignrService()
        self.gmail = GmailService()

    @staticmethod
    def get_current_season() -> Tuple[int, int]:
        """Get the current active season (year, is_spring)."""
        config = LeagueSeason.query.filter_by(active=1).order_by(
            LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
        ).first()
        if config:
            return config.year, 1 if config.is_spring else 0
        # Default fallback
        today = date.today()
        return today.year, 1 if today.month < 7 else 0

    def get_games_for_timeframe(
        self,
        hours_ahead: int = 7,
        hours_start: int = 0
    ) -> List[Dict]:
        """
        Get games from Assignr within a time window.

        Args:
            hours_ahead: Hours in the future to look (end of window)
            hours_start: Hours in the future to start looking (start of window)

        Returns:
            List of enriched game dicts from Assignr
        """
        now = datetime.now()
        start_dt = now + timedelta(hours=hours_start)
        end_dt = now + timedelta(hours=hours_ahead)

        logger.info(f"Fetching games from {start_dt} to {end_dt}")

        games = self.assignr.get_all_games(start_dt, end_dt)

        # Filter out cancelled games
        games = [g for g in games if not g.get('is_cancelled')]

        # Enrich with local data
        games = self.assignr.enrich_games_with_local_data(games)

        # Filter out rainouts and cancelled local games
        filtered = []
        for g in games:
            local = g.get('_local')
            if local and local.get('status') in ('cancelled', 'rainout'):
                continue
            filtered.append(g)

        return filtered

    def get_coach_for_team(self, team_name: str, year: int) -> Optional[str]:
        """Get head coach name for a team."""
        if not team_name:
            return None

        from app.models.team import TeamSeason
        from sqlalchemy.orm import joinedload

        team = TeamSeason.query.options(
            joinedload(TeamSeason.coaches)
        ).filter(
            TeamSeason.year == year,
            TeamSeason.display_name == team_name
        ).first()

        if team:
            for coach in team.coaches:
                if coach.role == 'head':
                    return coach.name

        return None

    def generate_notifications(
        self,
        hours_ahead: int = 7,
        hours_start: int = 0
    ) -> List[UmpireDayOfNotification]:
        """
        Generate day-of notifications for upcoming games.

        Args:
            hours_ahead: Hours in the future to look
            hours_start: Hours from now to start looking

        Returns:
            List of created notification objects
        """
        year, is_spring = self.get_current_season()
        games = self.get_games_for_timeframe(hours_ahead, hours_start)

        logger.info(f"Found {len(games)} games in timeframe")

        notifications = []

        for game in games:
            # Get assignments for this game
            assignments = game.get('_embedded', {}).get('assignments', []) or []

            for assignment in assignments:
                embedded = assignment.get('_embedded', {}) or {}
                official = embedded.get('official', {}) or {}

                official_id = official.get('id')
                if not official_id:
                    continue

                first_name = official.get('first_name', '')
                last_name = official.get('last_name', '')
                umpire_name = f"{first_name} {last_name}".strip()

                assignr_game_id = game.get('id')

                # Check if notification already exists
                if UmpireDayOfNotification.exists_for_game_umpire(
                    assignr_game_id, official_id
                ):
                    logger.debug(f"Notification already exists for game {assignr_game_id}, umpire {official_id}")
                    continue

                # Get umpire email addresses from Assignr
                umpire_details = self.assignr.get_official(official_id)
                if not umpire_details:
                    logger.warning(f"Could not fetch details for official {official_id}")
                    continue

                email_addresses = umpire_details.get('email_addresses', [])
                if not email_addresses:
                    logger.warning(f"No email addresses for official {official_id}")
                    continue

                # Get game details
                local = game.get('_local', {}) or {}
                game_date = game.get('_game_date')
                location = local.get('field') or game.get('venue_name', 'TBD')
                league = local.get('league') or game.get('game_type', '')
                home_team = local.get('home_team') or ''
                away_team = local.get('away_team') or ''

                # Get coach names
                home_coach = self.get_coach_for_team(home_team, year)
                away_coach = self.get_coach_for_team(away_team, year)

                # Generate email content
                subject, body_html = self._render_email(
                    umpire_first_name=first_name,
                    game_date=game_date,
                    location=location,
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    home_coach=home_coach,
                    away_coach=away_coach
                )

                # Get local game ID if available
                local_game_id = local.get('game_id') if local else None

                # Create notification
                notification = UmpireDayOfNotification(
                    game_id=local_game_id,
                    assignr_game_id=assignr_game_id,
                    assignr_official_id=official_id,
                    umpire_name=umpire_name,
                    year=year,
                    is_spring=is_spring,
                    recipient_emails=str(email_addresses).replace("'", '"'),
                    subject=subject,
                    body_html=body_html,
                    game_date=game_date,
                    game_location=location,
                    game_league=league,
                    home_team=home_team,
                    away_team=away_team,
                    status=UmpireDayOfNotification.STATUS_DRAFT
                )

                db.session.add(notification)
                notifications.append(notification)

                logger.info(f"Created notification for {umpire_name} - game {assignr_game_id}")

        db.session.commit()
        return notifications

    def _render_email(
        self,
        umpire_first_name: str,
        game_date: datetime,
        location: str,
        league: str,
        home_team: str,
        away_team: str,
        home_coach: Optional[str],
        away_coach: Optional[str]
    ) -> Tuple[str, str]:
        """
        Render the HTML email content.

        Returns:
            Tuple of (subject, html_body)
        """
        # Format times
        time_str = game_date.strftime('%I:%M%p').lstrip('0').replace(':00', '')
        arrive_time = game_date - timedelta(minutes=15)
        arrive_str = arrive_time.strftime('%I:%M%p').lstrip('0').replace(':00', '')

        # Get league display string
        league_str = LEAGUE_STRINGS.get(league, league)

        # Get local rules link
        local_rules_link = LOCAL_RULES.get(league, DEFAULT_RULES_LINK)

        # Get weather zip
        weather_zip = FIELD_ZIP_CODES.get(location, DEFAULT_ZIP)

        # Build team strings with coaches
        if home_coach:
            home_team_w_coach = f"{home_team} (head coach is {home_coach})"
        else:
            home_team_w_coach = f"{home_team} (head coach is not listed)"

        if away_coach:
            away_team_w_coach = f"{away_team} (head coach is {away_coach})"
        else:
            away_team_w_coach = f"{away_team} (head coach is not listed)"

        # Build greeting
        hi_intro = f"Hi {umpire_first_name}," if umpire_first_name else "Hi,"

        # Build assignment details
        assignment_html = f"""<table style="border-collapse: collapse; width: 100%;">
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  {hi_intro}
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Here's the information for your game today at {location} @ {time_str}.
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Please try to arrive at the field by {arrive_str}.
</td>
</tr>
<tr>
<td style="line-height: 1.5; padding: 6px 0;">
  Today, you are working a {league_str} game.
  The {home_team_w_coach} are the home team and the away team is {away_team_w_coach}.
</td>
</tr>
</table>"""

        # Build full HTML (based on UmpirePregameInformation.html template)
        preheader_text = f"{location} @ {time_str}"
        field_encoded = location.replace(" ", "+")

        html = f"""<!DOCTYPE html><html><head>
<meta content="IE=edge" http-equiv="X-UA-Compatible">
<meta content="text/html; charset=UTF-8" http-equiv="Content-Type">
<meta content="width=device-width, initial-scale=1" name="viewport">
<title>SDLL // Gameday Umpiring Information</title>
<style>
@media only screen and (max-width:600px) {{
body{{margin-right:1px !important;margin-left:1px !important}}
}}
</style>
</head>
<body style="margin:0px">
<table style="border-collapse:collapse;table-layout:fixed;margin:0 auto;display:none;">
<tr><td>{preheader_text}</td></tr>
</table>

<table width="100%" bgcolor="#ffffff" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><td>
<div style="display: block; max-width: 670px; margin: 0 auto;">

<!-- HEADER -->
<div style="margin-bottom:7px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><th style="text-align:left;font-weight:400;padding:15px;font-family:Helvetica, Arial, sans-serif;font-size:16px;color:#333;display:block;background-color:#fff;border-radius:15px;border:1px solid #e6e6e6;margin-bottom:0px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><td colspan="2" align="center" style="padding-top:0px;">
<div style="display:inline-flex;">
<div style="padding:0;"><img style="width:30px; height:30px;" src="https://tshq.bluesombrero.com/Portals/22965/logo/logo638660559650795307.png" /></div>
<div style="padding:4px 0px 0px 15px;"><p style="font-family:Helvetica; font-size:24px; font-weight:700; line-height:22px;margin-top:0;margin-bottom:0px;">SDLL Umpiring</p></div>
</div>
</td></tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><td style="padding-top:20px">
<div><p style="line-height:22px;margin-top:0;margin-bottom:15px;font-size:16px;">{assignment_html}</p></div>
</td></tr>
</table>
</th></tr>
</table>
</div>

<!-- Running Late Section -->
<div style="margin-bottom:7px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><th style="text-align:left;font-weight:400;padding:15px;font-family:Helvetica, Arial, sans-serif;font-size:16px;color:#333;display:block;background-color:#fff;border-radius:15px;border:1px solid #e6e6e6;margin-bottom:0px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><td style="padding:0px 15px 15px 0px;">
<h1 style="font-family:Helvetica,Arial,sans-serif;font-size:24px;color:#1c7ff2;font-weight:700;margin-bottom:0;line-height:26px;margin-top:8px">
<font color="#1c7ff2">Running late?</font>
</h1>
</td></tr>
<tr><td colspan="2" align="" style="padding-top:0px;">
<div style="display:inline-flex;">
<div style="padding:4px 0px 0px 0px;">
<p style="font-family:Helvetica; font-size:18px; line-height:30px;margin-top:0;margin-bottom:0px;">
If you need to update the coaches so they know when you'll be arriving at the field,
<a href="https://docs.google.com/forms/d/e/1FAIpQLSfRYfhk8kt15U9MSfkfkKiixrNrWRQ4A1P6F7UVL0HKylvrlw/viewform?usp=pp_url&entry.583567966={field_encoded}">click here</a>.
</p>
</div>
</div>
</td></tr>
</table>
</th></tr>
</table>
</div>

<!-- Resources Section -->
<div style="margin-bottom:7px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><th style="text-align:left;font-weight:400;padding:15px;font-family:Helvetica, Arial, sans-serif;font-size:16px;color:#333;display:block;background-color:#fff;border-radius:15px;border:1px solid #e6e6e6;margin-bottom:0px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;">
<tr><td style="padding:0px 15px 15px 0px;">
<h1 style="font-family:Helvetica,Arial,sans-serif;font-size:24px;color:#1c7ff2;font-weight:700;margin-bottom:0;line-height:26px;margin-top:8px">
<font color="#1c7ff2">Resources</font>
</h1>
</td></tr>
<tr><td colspan="2" align="" style="padding-top:0px;">
<div style="display:inline-flex;">
<div style="padding:4px 0px 0px 0px;">
<p style="font-family:Helvetica; font-size:18px; line-height:30px;margin-top:0;margin-bottom:0px;">
Here are some resources that are good to have handy.<BR><BR>
<a href="{local_rules_link}">SDLL Rules</a><BR><BR>
<a href="https://www.weatherbug.com/alerts/spark/{weather_zip}">Weatherbug Lightning Strikes</a>
</p>
</div>
</div>
</td></tr>
</table>
</th></tr>
</table>
</div>

</div>
</td></tr>
</table>
</body></html>"""

        subject = "Information for your SDLL game today"

        return subject, html

    def send_notification(
        self,
        notification: UmpireDayOfNotification,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Send a day-of notification email.

        Args:
            notification: The notification to send
            user_id: ID of user sending the notification

        Returns:
            True if sent successfully
        """
        if not notification.can_send:
            logger.warning(f"Cannot send notification {notification.id}: status={notification.status}")
            return False

        try:
            recipients = notification.recipient_emails_list
            logger.info(f"Sending day-of notification to {recipients}")

            self.gmail.send_email(
                to=recipients,
                subject=notification.subject,
                body_text=f"Game today at {notification.game_location} @ {notification.game_time_str}",
                body_html=notification.body_html
            )

            notification.mark_sent(user_id)
            logger.info(f"Sent notification {notification.id} to {notification.umpire_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to send notification {notification.id}: {e}")
            return False

    def send_all_pending(self, user_id: Optional[int] = None) -> Tuple[int, int]:
        """
        Send all pending day-of notifications for today.

        Returns:
            Tuple of (sent_count, failed_count)
        """
        notifications = UmpireDayOfNotification.get_pending_for_today()

        sent = 0
        failed = 0

        for notif in notifications:
            if self.send_notification(notif, user_id):
                sent += 1
            else:
                failed += 1

        return sent, failed
