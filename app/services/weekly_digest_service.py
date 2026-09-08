"""Service for generating and sending weekly umpire partner digest emails."""

import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.weekly_digest import WeeklyDigest
from app.models.umpire_partner import UmpirePartner
from app.models.game import Game
from app.models.league import League
from app.models.league_season import LeagueSeason
from app.services.notification_service import GmailService
from app.utils.logging import SDLLLogger

logger = SDLLLogger('weekly_digest')


class WeeklyDigestService:
    """Service for managing weekly umpire partner digest emails."""

    # Partner code for internal SDLL Academy
    SDLL_ACADEMY_CODE = 'SDL'
    SDLL_ACADEMY_NAME = 'SDLL Academy'

    def __init__(self):
        self.gmail = GmailService()

    @staticmethod
    def get_current_week_monday():
        """Get the Monday of the current week."""
        today = date.today()
        return today - timedelta(days=today.weekday())

    @staticmethod
    def get_next_week_monday():
        """Get the Monday of next week (for upcoming games)."""
        return WeeklyDigestService.get_current_week_monday() + timedelta(days=7)

    @staticmethod
    def get_current_season():
        """Get the current active season (year, is_spring)."""
        config = LeagueSeason.query.filter_by(active=1).order_by(
            LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
        ).first()
        if config:
            return config.year, 1 if config.is_spring else 0
        # Default fallback
        today = date.today()
        return today.year, 1 if today.month < 7 else 0

    def get_partner_games(self, partner_code, week_start, year, is_spring):
        """
        Get games for a partner in the specified week.

        Args:
            partner_code: Partner short code (DIA, DYN, SDL)
            week_start: Monday of the week (date)
            year: Season year
            is_spring: 1 for spring, 0 for fall

        Returns:
            List of Game objects with eager-loaded relationships
        """
        week_end = week_start + timedelta(days=6)

        games = Game.query.options(
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.field_rel)
        ).filter(
            Game.umpire_override == partner_code,
            Game.year == year,
            Game.is_spring == (is_spring == 1),
            Game.active == 1,
            Game.game_type.in_(['regular', 'playoff']),
            db.func.date(Game.game_date) >= week_start,
            db.func.date(Game.game_date) <= week_end
        ).order_by(Game.game_date).all()

        return games

    def get_partner_recipients(self, partner_code):
        """
        Get recipient email addresses for a partner's weekly digest.

        Args:
            partner_code: Partner short code

        Returns:
            List of email addresses for contacts subscribed to weeklyDigest
        """
        from app.models.partner_contact import PartnerContact

        if partner_code == self.SDLL_ACADEMY_CODE:
            # For SDLL Academy, could use a configured email or skip
            # For now, return empty to indicate internal handling
            return []

        partner = UmpirePartner.get_by_code(partner_code)
        if partner:
            return partner.get_emails_for_message_type(PartnerContact.MSG_WEEKLY_DIGEST)
        return []

    def get_partner_info(self, partner_code):
        """
        Get partner name and auto_send setting.

        Args:
            partner_code: Partner short code

        Returns:
            Tuple of (name, auto_send_digest)
        """
        if partner_code == self.SDLL_ACADEMY_CODE:
            return self.SDLL_ACADEMY_NAME, False

        partner = UmpirePartner.get_by_code(partner_code)
        if partner:
            auto_send = getattr(partner, 'auto_send_digest', False) or False
            return partner.name, auto_send
        return partner_code, False

    def render_digest_html(self, partner_name, games, week_start, partner_code=None):
        """
        Render the HTML content for a digest email.

        Args:
            partner_name: Name to use in greeting
            games: List of Game objects
            week_start: Monday of the week
            partner_code: Partner short code (for schedule link)

        Returns:
            Tuple of (subject, html_body)
        """
        # Get partner schedule URL if available
        schedule_url = None
        if partner_code:
            partner = UmpirePartner.get_by_code(partner_code)
            if partner and partner.schedule_token:
                schedule_url = f"https://www.southdurhamlittleleague.org/s/partner/{partner.schedule_token}"
        week_display = week_start.strftime('%B %d')
        game_count = len(games)

        subject = f"SDLL Games - Week of {week_display}"

        # Group games by date, then by league
        games_by_date = defaultdict(list)
        for game in games:
            if game.game_date:
                game_date = game.game_date.date()
                games_by_date[game_date].append(game)

        # Build HTML content matching the exampleUpcomingUmpireEmail.html format
        html_parts = []

        # Header with logo
        html_parts.append('''
<div style="margin:0px">
<table width="100%" bgcolor="#ffffff" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td>
<div style="display:block;max-width:670px;margin:0 auto">
<div style="margin-bottom:7px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><th style="text-align:left;font-weight:400;padding:15px;font-family:Helvetica,Arial,sans-serif;font-size:16px;color:#333;display:block;background-color:#fff;border-radius:15px;border:1px solid #e6e6e6;border-collapse:collapse;margin-bottom:0px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td colspan="2" align="center" style="padding-top:0px">
<div style="display:inline-flex">
<div style="padding:0">
<img style="width:30px;height:30px" src="https://tshq.bluesombrero.com/Portals/22965/logo/logo638660559650795307.png">
</div>
<div style="padding:4px 0px 0px 15px">
<p style="font-family:Helvetica;font-size:24px;font-weight:700;line-height:22px;margin-top:0;margin-bottom:0px">SDLL Umpiring</p>
</div>
</div>
</td></tr>
</tbody></table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td style="padding-top:20px">
<div>
<table style="border-collapse:collapse;width:100%">
<tbody>
''')

        # Greeting
        schedule_link_text = ''
        if schedule_url:
            schedule_link_text = f' And <a href="{schedule_url}" style="color:#228B22">here</a> is the full schedule view.'

        html_parts.append(f'''
<tr><td style="line-height:1.5;padding:6px 0">Hi,</td></tr>
<tr><td style="line-height:1.5;padding:6px 0">
Here's your upcoming schedule of {game_count} SDLL game{'s' if game_count != 1 else ''} for the week of {week_display}. If you see anything that looks inaccurate, let me know.{schedule_link_text}
</td></tr>
<tr><td style="line-height:1.5;padding:6px 0"></td></tr>
''')

        # Games by date
        for game_date in sorted(games_by_date.keys()):
            date_games = games_by_date[game_date]
            date_str = game_date.strftime('%a %b %d')  # e.g., "Mon May 11th"
            day_suffix = self._get_day_suffix(game_date.day)
            date_display = f"{game_date.strftime('%a %b')} {game_date.day}{day_suffix}"
            game_word = "game" if len(date_games) == 1 else "games"

            html_parts.append(f'<tr><td><h3>{date_display} ({len(date_games)} {game_word})</h3></td></tr>')

            # Group by league
            games_by_league = defaultdict(list)
            for game in date_games:
                league = game.league or 'Unknown'
                games_by_league[league].append(game)

            for league in sorted(games_by_league.keys()):
                html_parts.append(f'<tr><td style="padding-left:10px"><h4>{league}</h4></td></tr>')

                for game in games_by_league[league]:
                    time_str = game.game_date.strftime('%I:%M %p').lstrip('0').lower()
                    field_name = game.field_name or 'TBD'

                    # Add Google Maps link if field has address
                    maps_link = ''
                    if game.field_rel and game.field_rel.google_maps_url:
                        maps_link = (
                            f' <a href="{game.field_rel.google_maps_url}" '
                            f'style="text-decoration:none;vertical-align:middle" '
                            f'title="Get directions">'
                            f'<img src="https://maps.google.com/mapfiles/ms/icons/red-dot.png" '
                            f'style="width:16px;height:16px;vertical-align:middle" alt="Map">'
                            f'</a>'
                        )

                    html_parts.append(
                        f'<tr><td style="border-bottom:solid 1px #eee;padding-left:20px">'
                        f'{time_str} @ {field_name}{maps_link}</td></tr>'
                    )

        # Footer
        html_parts.append('''
</tbody></table>
<p style="line-height:22px;margin-top:0;margin-bottom:15px"></p>
</div>
</td></tr></tbody></table>
</th></tr></tbody></table>
</div>
</div>
</td></tr></tbody></table>
</div>
''')

        html_body = ''.join(html_parts)
        return subject, html_body

    def _get_day_suffix(self, day):
        """Get ordinal suffix for a day number."""
        if 11 <= day <= 13:
            return 'th'
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')

    def generate_digest_for_partner(self, partner_code, week_start, year, is_spring):
        """
        Generate or update a digest for a specific partner and week.

        Args:
            partner_code: Partner short code
            week_start: Monday of the week
            year: Season year
            is_spring: 1 for spring, 0 for fall

        Returns:
            WeeklyDigest object (new or updated)
        """
        # Check for existing digest
        existing = WeeklyDigest.get_for_partner_week(partner_code, week_start)
        if existing and existing.status == WeeklyDigest.STATUS_SENT:
            logger.info(f"Digest already sent for {partner_code} week {week_start}")
            return existing

        # Get partner info
        partner_name, auto_send = self.get_partner_info(partner_code)

        # Get games for this partner/week
        games = self.get_partner_games(partner_code, week_start, year, is_spring)

        # Get recipients
        recipients = self.get_partner_recipients(partner_code)

        # Generate content
        subject, body_html = self.render_digest_html(partner_name, games, week_start, partner_code)

        if existing:
            # Update existing draft
            digest = existing
            digest.partner_name = partner_name
            digest.recipient_emails = json.dumps(recipients)
            digest.subject = subject
            digest.body_html = body_html
            digest.game_count = len(games)
            # Reset status to draft if regenerating
            if digest.status != WeeklyDigest.STATUS_SENT:
                digest.status = WeeklyDigest.STATUS_DRAFT
        else:
            # Create new digest
            digest = WeeklyDigest(
                partner_code=partner_code,
                partner_name=partner_name,
                week_start=week_start,
                year=year,
                is_spring=is_spring,
                recipient_emails=json.dumps(recipients),
                subject=subject,
                body_html=body_html,
                game_count=len(games),
                status=WeeklyDigest.STATUS_DRAFT
            )
            db.session.add(digest)

        db.session.commit()

        # Handle auto-send or no-games scenarios
        if len(games) == 0:
            digest.mark_skipped()
            logger.info(f"Skipped digest for {partner_code} - no games")
        elif auto_send and recipients:
            # Auto-send mode: send immediately
            success = self.send_digest(digest, sent_by_user_id=None)
            if success:
                logger.info(f"Auto-sent digest for {partner_code}")
            else:
                logger.error(f"Failed to auto-send digest for {partner_code}")

        return digest

    def generate_all_digests(self, week_start=None, year=None, is_spring=None):
        """
        Generate digests for all active partners.

        Args:
            week_start: Monday of the target week (default: next week)
            year: Season year (default: current season)
            is_spring: 1 for spring, 0 for fall (default: current season)

        Returns:
            List of generated WeeklyDigest objects
        """
        if week_start is None:
            week_start = self.get_next_week_monday()

        if year is None or is_spring is None:
            year, is_spring = self.get_current_season()

        # Get all partner codes that have games assigned
        partner_codes_with_games = db.session.query(Game.umpire_override).filter(
            Game.umpire_override.isnot(None),
            Game.year == year,
            Game.is_spring == (is_spring == 1),
            Game.active == 1
        ).distinct().all()
        partner_codes = [p[0] for p in partner_codes_with_games if p[0]]

        # Also include any active partners even if they have no games
        # (so we can show "skipped" status)
        active_partners = UmpirePartner.get_active()
        for p in active_partners:
            if p.short_code and p.short_code not in partner_codes:
                partner_codes.append(p.short_code)

        # Generate digest for each partner
        digests = []
        for code in partner_codes:
            try:
                digest = self.generate_digest_for_partner(code, week_start, year, is_spring)
                digests.append(digest)
            except Exception as e:
                logger.error(f"Error generating digest for {code}: {e}")

        return digests

    def send_digest(self, digest, sent_by_user_id=None):
        """
        Send a digest email.

        Args:
            digest: WeeklyDigest object
            sent_by_user_id: User ID who initiated the send (optional for auto-send)

        Returns:
            True if sent successfully, False otherwise
        """
        if not digest.can_send:
            logger.warning(f"Cannot send digest {digest.id} - status: {digest.status}, games: {digest.game_count}")
            return False

        recipients = digest.recipient_emails_list
        if not recipients:
            logger.warning(f"No recipients for digest {digest.id}")
            return False

        # Generate plain text version
        body_text = self._html_to_text(digest.body_html)

        try:
            # Send to each recipient
            for recipient in recipients:
                self.gmail.send_email(
                    to=recipient,
                    subject=digest.subject,
                    body_text=body_text,
                    body_html=digest.body_html
                )
                logger.info(f"Sent digest {digest.id} to {recipient}")

            # Mark as sent
            digest.status = WeeklyDigest.STATUS_SENT
            digest.sent_at = datetime.utcnow()
            digest.sent_by = sent_by_user_id
            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to send digest {digest.id}: {e}")
            return False

    def _html_to_text(self, html):
        """Convert HTML to plain text for email fallback."""
        import re

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html)
        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def send_reminder_to_admins(self, pending_digests):
        """
        Send reminder email to admins about pending digests.

        Args:
            pending_digests: List of WeeklyDigest objects with status=draft

        Returns:
            True if reminder sent successfully
        """
        if not pending_digests:
            return False

        # Build summary
        partner_list = ', '.join([d.partner_name for d in pending_digests])
        week_start = pending_digests[0].week_start

        subject = f"Reminder: {len(pending_digests)} umpire digest(s) pending review"
        body_text = f"""
The following weekly umpire digests are pending review for the week of {week_start.strftime('%B %d, %Y')}:

Partners: {partner_list}

Please review and send these digests at:
https://www.southdurhamlittleleague.org/umpires/{pending_digests[0].year}/{pending_digests[0].is_spring}/digests

This is an automated reminder.
"""

        try:
            # Send to admin email (configured in environment)
            import os
            admin_email = os.environ.get('ADMIN_EMAIL', 'sdll.umpires@gmail.com')

            self.gmail.send_email(
                to=admin_email,
                subject=subject,
                body_text=body_text
            )

            # Mark reminders as sent
            for digest in pending_digests:
                digest.reminder_sent = True
            db.session.commit()

            logger.info(f"Sent reminder for {len(pending_digests)} pending digests")
            return True

        except Exception as e:
            logger.error(f"Failed to send digest reminder: {e}")
            return False

    # =========================================================================
    # Academy Umpire Digests
    # =========================================================================

    # Default group name for Academy umpires in Assignr
    ACADEMY_GROUP_NAME = 'SDLL Academy'

    def get_umpire_recipients(self, official, umpire_profile=None):
        """
        Get email recipients for an Academy umpire digest.

        Includes the umpire's email (from Assignr) and parent emails
        (from local UmpireProfile if linked).

        Args:
            official: Dict with official data from Assignr (has 'emails' list)
            umpire_profile: Optional UmpireProfile model instance

        Returns:
            List of email addresses
        """
        recipients = []

        # Add umpire's own emails from Assignr
        for email in official.get('emails', []):
            if email and email not in recipients:
                recipients.append(email)

        # Add parent/guardian emails from local profile
        if umpire_profile:
            # Check parent_email field
            if umpire_profile.parent_email:
                if umpire_profile.parent_email not in recipients:
                    recipients.append(umpire_profile.parent_email)

            # Check guardians
            for ug in umpire_profile.guardians:
                if ug.guardian and ug.guardian.email:
                    if ug.guardian.email not in recipients:
                        recipients.append(ug.guardian.email)

        return recipients

    def render_umpire_digest_html(self, umpire_name, games, week_start):
        """
        Render the HTML content for an individual umpire's digest email.

        Args:
            umpire_name: Umpire's full name
            games: List of game dicts from Assignr
            week_start: Monday of the week

        Returns:
            Tuple of (subject, html_body)
        """
        week_display = week_start.strftime('%B %d')
        game_count = len(games)

        subject = f"Your SDLL Games - Week of {week_display}"

        # Group games by date
        games_by_date = defaultdict(list)
        for game in games:
            game_date = game.get('_game_date')
            if game_date:
                games_by_date[game_date.date()].append(game)

        # Build HTML content
        html_parts = []

        # Header with logo
        html_parts.append('''
<div style="margin:0px">
<table width="100%" bgcolor="#ffffff" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td>
<div style="display:block;max-width:670px;margin:0 auto">
<div style="margin-bottom:7px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><th style="text-align:left;font-weight:400;padding:15px;font-family:Helvetica,Arial,sans-serif;font-size:16px;color:#333;display:block;background-color:#fff;border-radius:15px;border:1px solid #e6e6e6;border-collapse:collapse;margin-bottom:0px">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td colspan="2" align="center" style="padding-top:0px">
<div style="display:inline-flex">
<div style="padding:0">
<img style="width:30px;height:30px" src="https://tshq.bluesombrero.com/Portals/22965/logo/logo638660559650795307.png">
</div>
<div style="padding:4px 0px 0px 15px">
<p style="font-family:Helvetica;font-size:24px;font-weight:700;line-height:22px;margin-top:0;margin-bottom:0px">SDLL Umpiring</p>
</div>
</div>
</td></tr>
</tbody></table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">
<tbody><tr><td style="padding-top:20px">
<div>
<table style="border-collapse:collapse;width:100%">
<tbody>
''')

        # Greeting
        html_parts.append(f'''
<tr><td style="line-height:1.5;padding:6px 0">Hi {umpire_name.split()[0] if umpire_name else 'there'},</td></tr>
<tr><td style="line-height:1.5;padding:6px 0">
Here's your upcoming schedule of {game_count} SDLL game{'s' if game_count != 1 else ''} for the week of {week_display}.
</td></tr>
<tr><td style="line-height:1.5;padding:6px 0"></td></tr>
''')

        # Games by date
        for game_date in sorted(games_by_date.keys()):
            date_games = games_by_date[game_date]
            day_suffix = self._get_day_suffix(game_date.day)
            date_display = f"{game_date.strftime('%a %b')} {game_date.day}{day_suffix}"
            game_word = "game" if len(date_games) == 1 else "games"

            html_parts.append(f'<tr><td><h3>{date_display} ({len(date_games)} {game_word})</h3></td></tr>')

            for game in date_games:
                time_str = game.get('localized_time', '')
                venue_name = game.get('venue_name', 'TBD')
                league_name = game.get('league_name', '')
                home_team = game.get('home_team', 'TBD')
                away_team = game.get('away_team', 'TBD')

                # Build matchup string
                matchup = f"{home_team} vs {away_team}"
                if league_name:
                    matchup = f"({league_name}) {matchup}"

                html_parts.append(
                    f'<tr><td style="border-bottom:solid 1px #eee;padding-left:10px">'
                    f'<strong>{time_str}</strong> @ {venue_name}<br>'
                    f'<span style="color:#666;font-size:14px">{matchup}</span>'
                    f'</td></tr>'
                )

        # Footer
        html_parts.append('''
<tr><td style="line-height:1.5;padding:20px 0 6px 0">
Good luck out there!
</td></tr>
</tbody></table>
</div>
</td></tr></tbody></table>
</th></tr></tbody></table>
</div>
</div>
</td></tr></tbody></table>
</div>
''')

        html_body = ''.join(html_parts)
        return subject, html_body

    def generate_academy_umpire_digests(
        self,
        week_start=None,
        year=None,
        is_spring=None,
        group_name=None,
        auto_send=False
    ):
        """
        Generate digests for Academy umpires who have games in the upcoming week.

        Args:
            week_start: Monday of the target week (default: next week)
            year: Season year (default: current season)
            is_spring: 1 for spring, 0 for fall (default: current season)
            group_name: Assignr group name (default: ACADEMY_GROUP_NAME)
            auto_send: Whether to auto-send digests (default: False)

        Returns:
            List of generated UmpireDigest objects
        """
        from datetime import timedelta
        from app.models.umpire_digest import UmpireDigest
        from app.models.umpire_profile import UmpireProfile
        from app.services.assignr_service import AssignrService

        if week_start is None:
            week_start = self.get_next_week_monday()

        if year is None or is_spring is None:
            year, is_spring = self.get_current_season()

        if group_name is None:
            group_name = self.ACADEMY_GROUP_NAME

        # Convert to datetime if needed
        if hasattr(week_start, 'date'):
            week_start_dt = week_start
        else:
            week_start_dt = datetime.combine(week_start, datetime.min.time())

        week_end_dt = week_start_dt + timedelta(days=6, hours=23, minutes=59)

        # Get Academy umpires with games from Assignr
        assignr_service = AssignrService()
        if not assignr_service.is_configured():
            logger.warning("Assignr not configured - cannot generate Academy digests")
            return []

        umpires_with_games = assignr_service.get_academy_umpires_with_games(
            group_name, week_start_dt, week_end_dt
        )

        if not umpires_with_games:
            logger.info(f"No Academy umpires with games for week of {week_start}")
            return []

        # Get local umpire profiles for parent emails
        local_profiles = UmpireProfile.query.filter(
            UmpireProfile.assignr_id.isnot(None)
        ).all()
        profiles_by_assignr_id = {p.assignr_id: p for p in local_profiles}

        # Generate digest for each umpire
        digests = []
        for umpire_data in umpires_with_games:
            try:
                official_id = umpire_data['official_id']
                umpire_name = umpire_data['full_name']
                games = umpire_data['games']

                # Check for existing digest
                existing = UmpireDigest.get_for_umpire_week(official_id, week_start)
                if existing and existing.status == UmpireDigest.STATUS_SENT:
                    logger.info(f"Digest already sent for {umpire_name}")
                    digests.append(existing)
                    continue

                # Get local profile if linked
                local_profile = profiles_by_assignr_id.get(str(official_id))

                # Get recipients (umpire + parents)
                recipients = self.get_umpire_recipients(umpire_data, local_profile)

                # Generate content
                subject, body_html = self.render_umpire_digest_html(
                    umpire_name, games, week_start
                )

                if existing:
                    # Update existing draft
                    digest = existing
                    digest.umpire_name = umpire_name
                    digest.recipient_emails = json.dumps(recipients)
                    digest.subject = subject
                    digest.body_html = body_html
                    digest.game_count = len(games)
                    digest.umpire_profile_id = local_profile.id if local_profile else None
                    if digest.status != UmpireDigest.STATUS_SENT:
                        digest.status = UmpireDigest.STATUS_DRAFT
                else:
                    # Create new digest
                    digest = UmpireDigest(
                        assignr_official_id=official_id,
                        umpire_name=umpire_name,
                        week_start=week_start,
                        year=year,
                        is_spring=is_spring,
                        umpire_profile_id=local_profile.id if local_profile else None,
                        recipient_emails=json.dumps(recipients),
                        subject=subject,
                        body_html=body_html,
                        game_count=len(games),
                        status=UmpireDigest.STATUS_DRAFT
                    )
                    db.session.add(digest)

                db.session.commit()

                # Handle auto-send
                if auto_send and recipients:
                    success = self.send_umpire_digest(digest)
                    if success:
                        logger.info(f"Auto-sent digest for {umpire_name}")

                digests.append(digest)

            except Exception as e:
                logger.error(f"Error generating digest for {umpire_data.get('full_name', 'unknown')}: {e}")

        logger.info(f"Generated {len(digests)} Academy umpire digests")
        return digests

    def send_umpire_digest(self, digest, sent_by_user_id=None):
        """
        Send an individual umpire digest email.

        Args:
            digest: UmpireDigest object
            sent_by_user_id: User ID who initiated the send (optional)

        Returns:
            True if sent successfully, False otherwise
        """
        from app.models.umpire_digest import UmpireDigest

        if not digest.can_send:
            logger.warning(f"Cannot send umpire digest {digest.id}")
            return False

        recipients = digest.recipient_emails_list
        if not recipients:
            logger.warning(f"No recipients for umpire digest {digest.id}")
            return False

        # Generate plain text version
        body_text = self._html_to_text(digest.body_html)

        try:
            # Send to each recipient
            for recipient in recipients:
                self.gmail.send_email(
                    to=recipient,
                    subject=digest.subject,
                    body_text=body_text,
                    body_html=digest.body_html
                )
                logger.info(f"Sent umpire digest {digest.id} to {recipient}")

            # Mark as sent
            digest.mark_sent(sent_by_user_id)
            return True

        except Exception as e:
            logger.error(f"Failed to send umpire digest {digest.id}: {e}")
            return False

    def send_all_umpire_digests(self, week_start, sent_by_user_id=None):
        """
        Send all pending umpire digests for a week.

        Args:
            week_start: Monday of the target week
            sent_by_user_id: User ID who initiated the send

        Returns:
            Tuple of (sent_count, failed_count)
        """
        from app.models.umpire_digest import UmpireDigest

        pending = UmpireDigest.get_pending_for_week(week_start)
        sent = 0
        failed = 0

        for digest in pending:
            if self.send_umpire_digest(digest, sent_by_user_id):
                sent += 1
            else:
                failed += 1

        return sent, failed
