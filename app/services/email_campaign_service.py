"""Email Campaign Service - handles variable injection, recipient resolution, and sending.

This service manages the lifecycle of email campaigns:
1. Generate campaigns from templates for a season
2. Resolve recipients based on template targeting
3. Inject variables into templates
4. Send campaigns via the notification service
"""

import re
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple

from app.extensions import db
from app.models.email_campaign_template import EmailCampaignTemplate
from app.models.email_campaign_instance import EmailCampaignInstance
from app.models.org_season import OrgSeason
from app.models.league_season import LeagueSeason
from app.models.umpire_profile import UmpireProfile
from app.models.umpire_partner import UmpirePartner
from app.models.partner_contact import PartnerContact
from app.models.user import User
from app.services.notification_service import GmailService


class EmailCampaignService:
    """Service for managing email campaigns."""

    def __init__(self):
        self.email_service = GmailService()

    def get_season_variables(self, org_season: OrgSeason) -> Dict[str, str]:
        """Get all available variables for a season.

        Args:
            org_season: The OrgSeason to get variables for.

        Returns:
            Dict mapping variable names to values.
        """
        variables = {
            'season_name': org_season.season_name,
            'year': str(org_season.year),
            'coordinator_email': os.environ.get('UMPIRE_COORDINATOR_EMAIL', 'umpires@sdll.org'),
            'coordinator_phone': os.environ.get('UMPIRE_COORDINATOR_PHONE', '773-420-6844'),
        }

        # Get dates from OrgSeason (with fallback to LeagueSeason)
        first_practice = org_season.get_first_practice_date()
        if first_practice:
            variables['first_practice_date'] = first_practice.strftime('%B %d, %Y')
        else:
            variables['first_practice_date'] = 'TBD'

        opening_day = org_season.get_opening_day_date()
        if opening_day:
            variables['opening_day_date'] = opening_day.strftime('%B %d, %Y')
        else:
            variables['opening_day_date'] = 'TBD'

        season_end = org_season.get_season_end_date()
        if season_end:
            variables['season_end_date'] = season_end.strftime('%B %d, %Y')
        else:
            variables['season_end_date'] = 'TBD'

        training_date = org_season.get_training_date()
        if training_date:
            variables['training_date'] = training_date.strftime('%B %d, %Y')
        else:
            variables['training_date'] = 'TBD'

        return variables

    def get_milestone_date(self, org_season: OrgSeason, milestone: str) -> Optional[date]:
        """Get the date for a specific milestone.

        Uses OrgSeason dates directly, with fallback to LeagueSeason dates.

        Args:
            org_season: The OrgSeason.
            milestone: Milestone code (first_practice, opening_day, training_date, season_end).

        Returns:
            date object or None if not set.
        """
        if milestone == EmailCampaignTemplate.MILESTONE_FIRST_PRACTICE:
            return org_season.get_first_practice_date()

        elif milestone == EmailCampaignTemplate.MILESTONE_OPENING_DAY:
            return org_season.get_opening_day_date()

        elif milestone == EmailCampaignTemplate.MILESTONE_TRAINING_DATE:
            return org_season.get_training_date()

        elif milestone == EmailCampaignTemplate.MILESTONE_SEASON_END:
            return org_season.get_season_end_date()

        return None

    def calculate_trigger_date(self, template: EmailCampaignTemplate,
                                org_season: OrgSeason) -> Optional[date]:
        """Calculate when a campaign should trigger.

        Args:
            template: The template with trigger settings.
            org_season: The season.

        Returns:
            date object for trigger, or None if can't be calculated.
        """
        if template.trigger_type == 'manual':
            # Manual triggers don't have a computed date
            return None

        milestone_date = self.get_milestone_date(org_season, template.trigger_milestone)
        if not milestone_date:
            return None

        offset = template.trigger_days_offset or 0
        return milestone_date + timedelta(days=offset)

    def resolve_recipients(self, template: EmailCampaignTemplate,
                           org_season: OrgSeason) -> List[Dict]:
        """Resolve recipients based on template targeting.

        Args:
            template: The template with recipient targeting.
            org_season: The season.

        Returns:
            List of recipient dicts: [{"email": "...", "name": "...", "type": "..."}]
        """
        recipients = []
        recipient_type = template.recipient_type
        status_filter = template.recipient_status_list

        if recipient_type == EmailCampaignTemplate.RECIPIENT_PARTNER:
            # Get all active partners
            partners = UmpirePartner.query.filter_by(active=1).all()
            for partner in partners:
                # Get partner contacts
                contacts = partner.contacts
                if contacts:
                    for contact in contacts:
                        if contact.email:
                            recipients.append({
                                'email': contact.email,
                                'name': contact.name or partner.name,
                                'type': 'partner',
                                'partner_id': partner.id,
                                'partner_name': partner.name
                            })
                elif partner.email:
                    # Fallback to partner's main email
                    recipients.append({
                        'email': partner.email,
                        'name': partner.name,
                        'type': 'partner',
                        'partner_id': partner.id,
                        'partner_name': partner.name
                    })

        elif recipient_type == EmailCampaignTemplate.RECIPIENT_LEAD:
            # Get umpire leads (prospective/contacted)
            query = UmpireProfile.query.filter(
                UmpireProfile.status.in_(UmpireProfile.LEAD_STATUSES)
            )

            # Filter by specific statuses if provided
            if status_filter:
                query = query.filter(UmpireProfile.status.in_(status_filter))

            # Filter by target season
            query = query.filter(
                db.or_(
                    UmpireProfile.target_org_season_id == org_season.ID,
                    UmpireProfile.target_org_season_id.is_(None)
                )
            )

            leads = query.all()
            for lead in leads:
                email = lead.contact_email
                if email:
                    recipients.append({
                        'email': email,
                        'name': lead.name,
                        'type': 'lead',
                        'umpire_profile_id': lead.id
                    })

        elif recipient_type == EmailCampaignTemplate.RECIPIENT_ACTIVE_UMPIRE:
            # Get active umpires
            umpires = UmpireProfile.query.filter_by(status=UmpireProfile.STATUS_ACTIVE).all()
            for umpire in umpires:
                email = umpire.contact_email
                if email:
                    recipients.append({
                        'email': email,
                        'name': umpire.name,
                        'type': 'umpire',
                        'umpire_profile_id': umpire.id
                    })

        elif recipient_type == EmailCampaignTemplate.RECIPIENT_LEAGUE_ADMIN:
            # Get users with scheduler or admin role
            users = User.query.filter(
                User.active == 1,
                db.or_(
                    User.role.like('%admin%'),
                    User.role.like('%scheduler%')
                )
            ).all()
            for user in users:
                if user.email:
                    recipients.append({
                        'email': user.email,
                        'name': user.name,
                        'type': 'admin',
                        'user_id': user.ID
                    })

        elif recipient_type == EmailCampaignTemplate.RECIPIENT_COORDINATOR:
            # Get umpire coordinators
            users = User.query.filter(
                User.active == 1,
                db.or_(
                    User.role.like('%admin%'),
                    User.role.like('%umpire_coordinator%')
                )
            ).all()
            for user in users:
                if user.email:
                    recipients.append({
                        'email': user.email,
                        'name': user.name,
                        'type': 'coordinator',
                        'user_id': user.ID
                    })

        return recipients

    def inject_variables(self, template_str: str, variables: Dict[str, str],
                          recipient: Optional[Dict] = None) -> str:
        """Inject variables into a template string.

        Args:
            template_str: String with {{variable}} placeholders.
            variables: Dict of variable name -> value.
            recipient: Optional recipient dict for recipient-specific variables.

        Returns:
            String with variables replaced.
        """
        result = template_str

        # Add recipient-specific variables
        if recipient:
            variables = variables.copy()
            variables['recipient_name'] = recipient.get('name', 'Friend')
            if recipient.get('partner_name'):
                variables['partner_name'] = recipient['partner_name']

        # Replace all {{variable}} patterns
        pattern = r'\{\{(\w+)\}\}'

        def replacer(match):
            var_name = match.group(1)
            return variables.get(var_name, match.group(0))

        return re.sub(pattern, replacer, result)

    def generate_campaign_for_template(self, template: EmailCampaignTemplate,
                                         org_season: OrgSeason) -> Optional[EmailCampaignInstance]:
        """Generate a campaign instance from a template for a season.

        Args:
            template: The template to use.
            org_season: The season to generate for.

        Returns:
            Created EmailCampaignInstance or None if already exists.
        """
        # Check if already exists
        if EmailCampaignInstance.exists_for_template_and_season(template.id, org_season.ID):
            return None

        # Calculate trigger date
        trigger_date = self.calculate_trigger_date(template, org_season)
        if not trigger_date:
            # Can't calculate trigger date yet (milestone dates not set)
            return None

        # Get season variables
        variables = self.get_season_variables(org_season)

        # Resolve recipients
        recipients = self.resolve_recipients(template, org_season)

        # Inject variables into template (without recipient-specific vars for initial draft)
        subject = self.inject_variables(template.subject_template, variables)
        body_html = self.inject_variables(template.body_html_template, variables)
        body_text = self.inject_variables(template.body_text_template or '', variables)

        # Create instance
        instance, created = EmailCampaignInstance.get_or_create(
            template_id=template.id,
            org_season_id=org_season.ID,
            trigger_date=trigger_date,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            recipients=recipients
        )

        return instance if created else None

    def generate_all_campaigns_for_season(self, org_season: OrgSeason) -> List[EmailCampaignInstance]:
        """Generate all campaign instances for a season.

        Creates instances for all active milestone-triggered templates.

        Args:
            org_season: The season to generate for.

        Returns:
            List of created EmailCampaignInstance objects.
        """
        templates = EmailCampaignTemplate.get_milestone_templates()
        created = []

        for template in templates:
            instance = self.generate_campaign_for_template(template, org_season)
            if instance:
                created.append(instance)

        return created

    def regenerate_campaign(self, instance: EmailCampaignInstance) -> bool:
        """Regenerate campaign content (re-fetch recipients, re-render).

        Only works for pending/draft campaigns.

        Args:
            instance: The campaign instance to regenerate.

        Returns:
            True if successful.
        """
        if not instance.is_editable:
            return False

        template = instance.template
        org_season = instance.org_season

        # Get fresh season variables
        variables = self.get_season_variables(org_season)

        # Re-resolve recipients
        recipients = self.resolve_recipients(template, org_season)

        # Re-inject variables (keeping any manual date override)
        subject = self.inject_variables(template.subject_template, variables)
        body_html = self.inject_variables(template.body_html_template, variables)
        body_text = self.inject_variables(template.body_text_template or '', variables)

        # Update instance
        instance.subject = subject
        instance.body_html = body_html
        instance.body_text = body_text
        instance.recipients = recipients

        # Recalculate trigger date only if not overridden
        if not instance.trigger_date_was_overridden:
            new_trigger = self.calculate_trigger_date(template, org_season)
            if new_trigger:
                instance.trigger_date = new_trigger

        db.session.commit()
        return True

    def prepare_draft(self, instance: EmailCampaignInstance) -> bool:
        """Prepare a campaign draft (transition from pending to draft).

        This is called when the trigger date is reached.

        Args:
            instance: The campaign instance.

        Returns:
            True if successful.
        """
        if instance.status != EmailCampaignInstance.STATUS_PENDING:
            return False

        # Regenerate content to ensure it's fresh
        self.regenerate_campaign(instance)

        # Mark as draft
        instance.mark_draft_ready()
        return True

    def send_campaign(self, instance: EmailCampaignInstance, user_id: int,
                       force: bool = False) -> Tuple[int, int]:
        """Send a campaign to all recipients.

        Args:
            instance: The campaign instance to send.
            user_id: ID of user sending the campaign.
            force: If True, bypass is_due check (for manual coordinator sends).

        Returns:
            Tuple of (sent_count, failed_count).
        """
        # Check if campaign can be sent
        # - Must be scheduled (not paused or already sent)
        # - Must have recipients
        # - Must be due (unless force=True for manual sends)
        if not instance.is_scheduled:
            return (0, 0)
        if instance.recipient_count == 0:
            return (0, 0)
        if not force and not instance.is_due:
            return (0, 0)

        sent_count = 0
        failed_count = 0

        # Get season variables for recipient-specific injection
        org_season = instance.org_season
        variables = self.get_season_variables(org_season)

        for recipient in instance.recipients:
            email = recipient.get('email')
            if not email:
                failed_count += 1
                continue

            try:
                # Inject recipient-specific variables
                subject = self.inject_variables(instance.subject, variables, recipient)
                body_html = self.inject_variables(instance.body_html, variables, recipient)
                body_text = self.inject_variables(instance.body_text or '', variables, recipient)

                # Send email
                self.email_service.send_email(
                    to=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )
                sent_count += 1

            except Exception as e:
                print(f"Failed to send campaign email to {email}: {e}")
                failed_count += 1

        # Update instance status
        instance.mark_sent(user_id, sent_count, failed_count)

        return (sent_count, failed_count)

    def check_due_campaigns(self) -> List[EmailCampaignInstance]:
        """Check for campaigns that are due and auto-send them.

        This should be called by a daily cron job at 8 AM.
        Campaigns with status='scheduled' and trigger_date <= today
        will be sent automatically.

        Returns:
            List of campaigns that were sent.
        """
        due_campaigns = EmailCampaignInstance.get_due_campaigns()
        sent_campaigns = []

        # Use a system user ID for auto-sent campaigns
        # ID 0 indicates system-initiated send
        system_user_id = 0

        for campaign in due_campaigns:
            if campaign.recipient_count > 0:
                # Regenerate content to ensure fresh data
                self.regenerate_campaign(campaign)

                # Auto-send the campaign
                sent_count, failed_count = self.send_campaign(campaign, system_user_id)

                if sent_count > 0 or failed_count > 0:
                    sent_campaigns.append(campaign)

        return sent_campaigns

    def notify_coordinators_of_sent_campaigns(self, campaigns: List[EmailCampaignInstance]) -> bool:
        """Notify coordinators about campaigns that were auto-sent.

        Args:
            campaigns: List of campaigns that were sent.

        Returns:
            True if notification sent successfully.
        """
        if not campaigns:
            return False

        # Get coordinator emails
        coordinators = User.query.filter(
            User.active == 1,
            db.or_(
                User.role.like('%admin%'),
                User.role.like('%umpire_coordinator%')
            )
        ).all()

        if not coordinators:
            return False

        # Build email content
        campaign_list = '\n'.join([
            f"  - {c.template.name}: {c.sent_count} sent, {c.failed_count} failed"
            for c in campaigns
        ])

        total_sent = sum(c.sent_count for c in campaigns)
        total_failed = sum(c.failed_count for c in campaigns)

        subject = f"SDLL: {len(campaigns)} Email Campaign(s) Auto-Sent"
        body_text = f"""The following email campaign(s) were automatically sent:

{campaign_list}

Total: {total_sent} emails sent, {total_failed} failed.

Log in to the SDLL app to view campaign details.
"""

        body_html = f"""
<h2>Email Campaigns Auto-Sent</h2>
<p>The following email campaign(s) were automatically sent:</p>
<ul>
{''.join(f"<li><strong>{c.template.name}</strong>: {c.sent_count} sent, {c.failed_count} failed</li>" for c in campaigns)}
</ul>
<p><strong>Total:</strong> {total_sent} emails sent, {total_failed} failed.</p>
<p>Log in to the SDLL app to view campaign details.</p>
"""

        # Send to all coordinators
        for coordinator in coordinators:
            if coordinator.email:
                try:
                    self.email_service.send_email(
                        to=coordinator.email,
                        subject=subject,
                        body_text=body_text,
                        body_html=body_html
                    )
                except Exception as e:
                    print(f"Failed to send notification to {coordinator.email}: {e}")

        return True

    # Legacy method for backwards compatibility
    def send_reminder_to_coordinators(self, campaigns: List[EmailCampaignInstance]) -> bool:
        """Legacy: Now calls notify_coordinators_of_sent_campaigns."""
        return self.notify_coordinators_of_sent_campaigns(campaigns)
