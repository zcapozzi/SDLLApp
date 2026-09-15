"""Service for handling access requests - email sending and user creation."""

import re
import secrets
from flask import url_for

from app.extensions import db
from app.models.access_request import AccessRequest
from app.models.user import User
from app.models.email_campaign_template import EmailCampaignTemplate
from app.models.coach import CoachUser, CoachSeason
from app.models.team import TeamSeason
from app.services.notification_service import GmailService
from app.utils.logging import SDLLLogger

logger = SDLLLogger('access_request_service')


class AccessRequestService:
    """Service for processing access requests."""

    def __init__(self):
        self.email_service = GmailService()

    def _render_template(self, template_code, variables):
        """Render an email template with variables.

        Supports {{variable}} placeholders and simple {{#if variable}}...{{/if}} conditionals.
        """
        template = EmailCampaignTemplate.get_by_code(template_code)
        if not template:
            logger.error(f'Email template not found: {template_code}')
            return None, None, None

        subject = template.subject_template
        body_html = template.body_html_template
        body_text = template.body_text_template or ''

        # Replace simple variables {{variable}}
        for key, value in variables.items():
            placeholder = f'{{{{{key}}}}}'
            str_value = str(value) if value is not None else ''
            subject = subject.replace(placeholder, str_value)
            body_html = body_html.replace(placeholder, str_value)
            body_text = body_text.replace(placeholder, str_value)

        # Handle conditionals {{#if variable}}content{{/if}}
        def replace_conditional(match):
            var_name = match.group(1)
            content = match.group(2)
            if variables.get(var_name):
                return content
            return ''

        conditional_pattern = r'\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}'
        body_html = re.sub(conditional_pattern, replace_conditional, body_html, flags=re.DOTALL)
        body_text = re.sub(conditional_pattern, replace_conditional, body_text, flags=re.DOTALL)

        return subject, body_html, body_text

    def send_verification_email(self, access_request):
        """Send email verification link to parent requester."""
        if not self.email_service.is_configured:
            logger.warning('Email service not configured - verification email not sent')
            return False

        verify_url = url_for(
            'public.request_access_verify',
            token=access_request.verification_token,
            _external=True
        )

        variables = {
            'first_name': access_request.first_name,
            'last_name': access_request.last_name,
            'verify_url': verify_url
        }

        subject, body_html, body_text = self._render_template('verify_email', variables)
        if not subject:
            # Fallback if template not found
            subject = 'Verify your email for SDLL'
            body_text = f"""Hi {access_request.first_name},

Please verify your email address by clicking this link:
{verify_url}

This link expires in 24 hours.

- South Durham Little League"""
            body_html = None

        try:
            self.email_service.send_email(
                to=access_request.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            logger.info(f'Verification email sent to {access_request.email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send verification email: {e}')
            return False

    def send_welcome_email_parent(self, user, access_request):
        """Send welcome email to verified parent with password setup link."""
        if not self.email_service.is_configured:
            logger.warning('Email service not configured - welcome email not sent')
            return False

        # Generate password reset token
        token = user.generate_reset_token()
        reset_url = url_for('auth.reset_password', token=token, _external=True)

        variables = {
            'first_name': access_request.first_name,
            'last_name': access_request.last_name,
            'reset_url': reset_url
        }

        subject, body_html, body_text = self._render_template('welcome_parent', variables)
        if not subject:
            # Fallback
            subject = 'Welcome to SDLL - Set Your Password'
            body_text = f"""Hi {access_request.first_name},

Your account has been created. Set your password here:
{reset_url}

This link expires in 1 hour.

- South Durham Little League"""
            body_html = None

        try:
            self.email_service.send_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            logger.info(f'Welcome email (parent) sent to {user.email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send welcome email: {e}')
            return False

    def send_welcome_email_coach(self, user, access_request, team_name):
        """Send welcome email to approved coach with password setup link."""
        if not self.email_service.is_configured:
            return False

        token = user.generate_reset_token()
        reset_url = url_for('auth.reset_password', token=token, _external=True)

        variables = {
            'first_name': access_request.first_name,
            'last_name': access_request.last_name,
            'team_name': team_name or 'your team',
            'reset_url': reset_url
        }

        subject, body_html, body_text = self._render_template('welcome_coach', variables)
        if not subject:
            subject = 'Welcome to SDLL - Coach Access Approved'
            body_text = f"""Hi {access_request.first_name},

Your coach access has been approved for {team_name}.

Set your password here: {reset_url}

- South Durham Little League"""
            body_html = None

        try:
            self.email_service.send_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            logger.info(f'Welcome email (coach) sent to {user.email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send coach welcome email: {e}')
            return False

    def send_welcome_email_admin(self, user, access_request, assigned_roles):
        """Send welcome email to approved admin with password setup link."""
        if not self.email_service.is_configured:
            return False

        token = user.generate_reset_token()
        reset_url = url_for('auth.reset_password', token=token, _external=True)

        # Format roles for display
        roles_display = ', '.join(assigned_roles) if assigned_roles else 'Standard admin access'

        variables = {
            'first_name': access_request.first_name,
            'last_name': access_request.last_name,
            'roles': roles_display,
            'reset_url': reset_url
        }

        subject, body_html, body_text = self._render_template('welcome_admin', variables)
        if not subject:
            subject = 'Welcome to SDLL - Admin Access Approved'
            body_text = f"""Hi {access_request.first_name},

Your admin access has been approved. Your roles: {roles_display}

Set your password here: {reset_url}

- South Durham Little League"""
            body_html = None

        try:
            self.email_service.send_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            logger.info(f'Welcome email (admin) sent to {user.email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send admin welcome email: {e}')
            return False

    def notify_admins_of_new_request(self, access_request):
        """Send notification to site admins about a new pending request."""
        if not self.email_service.is_configured:
            return False

        # Get admin emails
        admins = User.query.filter(
            User.active == 1,
            User.role.contains('admin')
        ).all()

        if not admins:
            logger.warning('No admins found to notify of access request')
            return False

        admin_emails = [a.email for a in admins]

        review_url = url_for('admin.access_requests', _external=True)

        # Get team name if coach request
        team_name = ''
        if access_request.team_id and access_request.team:
            team_name = access_request.team.computed_display_name

        variables = {
            'requester_name': access_request.full_name,
            'request_type': access_request.type_display,
            'team_name': team_name,
            'requested_roles': access_request.requested_roles or 'N/A',
            'review_url': review_url
        }

        subject, body_html, body_text = self._render_template('access_request_pending', variables)
        if not subject:
            subject = f'SDLL Access Request: {access_request.type_display} - {access_request.full_name}'
            body_text = f"""New access request requires review.

Name: {access_request.full_name}
Type: {access_request.type_display}

Review here: {review_url}"""
            body_html = None

        try:
            # Send to all admins
            for email in admin_emails:
                self.email_service.send_email(
                    to=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )
            logger.info(f'Admin notification sent for request {access_request.id}')
            return True
        except Exception as e:
            logger.error(f'Failed to send admin notification: {e}')
            return False

    def send_rejection_email(self, access_request, reason=None):
        """Send rejection notification to requester."""
        if not self.email_service.is_configured:
            return False

        variables = {
            'first_name': access_request.first_name,
            'last_name': access_request.last_name,
            'reason': reason or ''
        }

        subject, body_html, body_text = self._render_template('access_request_rejected', variables)
        if not subject:
            subject = 'SDLL Access Request Update'
            body_text = f"""Hi {access_request.first_name},

We're unable to approve your access request at this time.

{('Reason: ' + reason) if reason else ''}

If you have questions, please contact info@sdll.org.

- South Durham Little League"""
            body_html = None

        try:
            self.email_service.send_email(
                to=access_request.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            logger.info(f'Rejection email sent to {access_request.email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send rejection email: {e}')
            return False

    def create_user_from_request(self, access_request, role='parent', additional_roles=None):
        """Create a User record from an approved access request.

        Args:
            access_request: The AccessRequest object
            role: Primary role for the user
            additional_roles: List of additional roles to add

        Returns:
            The created User object
        """
        # Generate a random temporary password (user will set via reset link)
        temp_password = secrets.token_urlsafe(16)

        # Build full role string
        roles = [role]
        if additional_roles:
            roles.extend(additional_roles)
        role_str = '|'.join(roles)

        user = User.create_user(
            email=access_request.email,
            password=temp_password,
            name=access_request.full_name,
            phone=access_request.phone,
            role=role_str
        )

        # Link request to created user
        access_request.created_user_id = user.ID
        db.session.commit()

        logger.info(f'Created user {user.ID} from access request {access_request.id}')
        return user

    def process_parent_verification(self, token):
        """Process parent email verification.

        Returns:
            tuple: (success: bool, message: str, user: User or None)
        """
        request = AccessRequest.get_by_verification_token(token)
        if not request:
            return False, 'Invalid verification link.', None

        if request.status == AccessRequest.STATUS_EXPIRED:
            return False, 'This verification link has expired. Please submit a new request.', None

        if request.status == AccessRequest.STATUS_APPROVED:
            # Already verified
            if request.created_user:
                return True, 'Your email was already verified.', request.created_user
            # Edge case: approved but no user created yet
            pass

        # Check if user already exists with this email
        existing_user = User.get_by_email(request.email)
        if existing_user:
            return False, 'An account with this email already exists. Please log in instead.', None

        # Verify the email
        if not request.verify_email(token):
            return False, 'Verification failed. The link may have expired.', None

        # Create the user account
        user = self.create_user_from_request(request, role='parent')

        # Send welcome email
        self.send_welcome_email_parent(user, request)

        return True, 'Email verified! Check your inbox for the password setup link.', user

    def approve_coach_request(self, request_id, processor_id, team_id=None):
        """Approve a coach access request and create the user.

        Args:
            request_id: ID of the access request
            processor_id: User ID of the admin processing the request
            team_id: Optional team ID to override the requested team

        Returns:
            tuple: (success: bool, message: str, user: User or None)
        """
        request = db.session.get(AccessRequest, request_id)
        if not request:
            return False, 'Request not found.', None

        if request.status != AccessRequest.STATUS_PENDING:
            return False, 'This request has already been processed.', None

        # Check if user already exists
        existing_user = User.get_by_email(request.email)
        if existing_user:
            return False, f'A user with email {request.email} already exists.', None

        # Use provided team_id or the one from the request
        final_team_id = team_id if team_id is not None else request.team_id
        team = db.session.get(TeamSeason, final_team_id) if final_team_id else None
        team_name = team.computed_display_name if team else 'your team'

        # Create user with coach role
        user = self.create_user_from_request(request, role='coach')

        # Create CoachUser record
        coach = CoachUser(
            user_id=user.ID,
            sport='both',  # Default to both; could be determined by league
            status=CoachUser.STATUS_ACTIVE
        )
        db.session.add(coach)
        db.session.commit()

        # Create CoachSeason record if team is provided
        if team:
            coach_season = CoachSeason(
                coach_id=coach.id,
                team_id=team.team_ID,
                role='head'  # Default to head coach
            )
            db.session.add(coach_season)
            db.session.commit()

        # Mark request as approved
        request.approve(processor_id, user.ID)

        # Send welcome email
        self.send_welcome_email_coach(user, request, team_name)

        logger.info(f'Approved coach request {request_id} for user {user.ID}')
        return True, f'Coach access approved for {request.full_name}.', user

    def approve_admin_request(self, request_id, processor_id, roles):
        """Approve an admin access request and create the user with specified roles.

        Args:
            request_id: ID of the access request
            processor_id: User ID of the admin processing the request
            roles: List of roles to assign

        Returns:
            tuple: (success: bool, message: str, user: User or None)
        """
        request = db.session.get(AccessRequest, request_id)
        if not request:
            return False, 'Request not found.', None

        if request.status != AccessRequest.STATUS_PENDING:
            return False, 'This request has already been processed.', None

        # Check if user already exists
        existing_user = User.get_by_email(request.email)
        if existing_user:
            return False, f'A user with email {request.email} already exists.', None

        # Validate roles
        valid_roles = [r for r in roles if r in User.ROLES]
        if not valid_roles:
            return False, 'No valid roles selected.', None

        # Create user with first role as primary, rest as additional
        user = self.create_user_from_request(
            request,
            role=valid_roles[0],
            additional_roles=valid_roles[1:] if len(valid_roles) > 1 else None
        )

        # Mark request as approved
        request.approve(processor_id, user.ID)

        # Send welcome email
        self.send_welcome_email_admin(user, request, valid_roles)

        logger.info(f'Approved admin request {request_id} for user {user.ID} with roles {valid_roles}')
        return True, f'Admin access approved for {request.full_name}.', user

    def reject_request(self, request_id, processor_id, reason=None, send_email=True):
        """Reject an access request.

        Args:
            request_id: ID of the access request
            processor_id: User ID of the admin processing the request
            reason: Optional reason for rejection
            send_email: Whether to send rejection email (default True)

        Returns:
            tuple: (success: bool, message: str)
        """
        request = db.session.get(AccessRequest, request_id)
        if not request:
            return False, 'Request not found.'

        if request.status != AccessRequest.STATUS_PENDING:
            return False, 'This request has already been processed.'

        # Mark as rejected
        request.reject(processor_id, reason)

        # Send rejection email if requested
        if send_email:
            self.send_rejection_email(request, reason)

        logger.info(f'Rejected request {request_id} by user {processor_id}')
        return True, f'Request from {request.full_name} rejected.'

    def send_daily_parent_digest(self):
        """Send daily digest of new parent accounts to admins.

        Call from a scheduled job.
        """
        from datetime import datetime, timedelta

        if not self.email_service.is_configured:
            return 0

        # Get requests approved in last 24 hours
        since = datetime.utcnow() - timedelta(hours=24)
        recent_parents = AccessRequest.get_recent_approved_parents(since)

        if not recent_parents:
            return 0

        # Get admin emails
        admins = User.query.filter(
            User.active == 1,
            User.role.contains('admin')
        ).all()

        if not admins:
            return 0

        admin_emails = [a.email for a in admins]

        # Build accounts table/list
        accounts_table_rows = []
        accounts_list = []
        for req in recent_parents:
            time_str = req.processed_at.strftime('%I:%M %p') if req.processed_at else ''
            accounts_table_rows.append(
                f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">{req.full_name}</td>'
                f'<td style="padding: 8px; border-bottom: 1px solid #ddd;">{req.email}</td>'
                f'<td style="padding: 8px; border-bottom: 1px solid #ddd;">{time_str}</td></tr>'
            )
            accounts_list.append(f'- {req.full_name} ({req.email}) at {time_str}')

        variables = {
            'count': len(recent_parents),
            'accounts_table': '\n'.join(accounts_table_rows),
            'accounts_list': '\n'.join(accounts_list)
        }

        subject, body_html, body_text = self._render_template('daily_parent_digest', variables)
        if not subject:
            subject = f'SDLL Daily Summary: {len(recent_parents)} New Parent Accounts'
            body_text = f"""{len(recent_parents)} new parent accounts created:

{chr(10).join(accounts_list)}"""
            body_html = None

        sent_count = 0
        for email in admin_emails:
            try:
                self.email_service.send_email(
                    to=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )
                sent_count += 1
            except Exception as e:
                logger.error(f'Failed to send digest to {email}: {e}')

        logger.info(f'Daily parent digest sent to {sent_count} admins ({len(recent_parents)} accounts)')
        return len(recent_parents)
