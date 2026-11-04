"""Service for handling Umpire Academy registration flow."""

import secrets
from datetime import datetime, date
from flask import url_for

from app.extensions import db
from app.models.user import User
from app.models.umpire_profile import UmpireProfile
from app.models.org_season import OrgSeason
from app.services.notification_service import GmailService


class UmpireAcademyService:
    """Handles the Umpire Academy registration flow.

    Phase I: Interest Registration - Creates User account and UmpireProfile
    Phase II: Profile Completion - Collects additional info (birth date, etc.)
    """

    @staticmethod
    def register_interest(first_name, last_name, email, phone=None):
        """Phase I: Register interest - creates User and UmpireProfile.

        Creates a User account with a random password (they can reset later),
        and an UmpireProfile linked to that user.

        Args:
            first_name: Umpire's first name
            last_name: Umpire's last name
            email: Umpire's email address (required)
            phone: Umpire's phone number (optional)

        Returns:
            tuple: (User, UmpireProfile)
        """
        # Check if user already exists
        existing_user = User.get_by_email(email)

        if existing_user:
            # User exists - check if they have a profile
            existing_profile = UmpireProfile.get_by_user_id(existing_user.ID)
            if existing_profile:
                # Already registered - just return existing
                return existing_user, existing_profile
            else:
                # User exists but no profile - create one
                user = existing_user
        else:
            # Create new user with random password (they can reset via forgot password)
            random_password = secrets.token_urlsafe(16)
            user = User(
                role='umpire',
                org_ID=1
            )
            user.email = email
            user.name = f"{first_name} {last_name}"
            user.phone = phone
            user.set_password(random_password)
            db.session.add(user)
            db.session.flush()  # Get the user ID

        # Get current season
        current_season = OrgSeason.get_current_season()

        # Create umpire profile
        profile = UmpireProfile(
            user_id=user.ID,
            status=UmpireProfile.STATUS_LEAD,
            lead_source=UmpireProfile.LEAD_SOURCE_UMPIRE_ACADEMY,
            target_org_season_id=current_season.ID if current_season else None
        )
        profile.first_name = first_name
        profile.last_name = last_name
        if phone:
            profile.umpire_phone = phone
        profile.umpire_email = email

        db.session.add(profile)
        db.session.commit()

        # Send welcome email with password reset link (async, don't block)
        UmpireAcademyService._send_welcome_email(user, profile)

        return user, profile

    @staticmethod
    def _send_welcome_email(user, profile):
        """Send welcome email with password setup link.

        Args:
            user: The User object
            profile: The UmpireProfile object
        """
        try:
            email_service = GmailService()
            if not email_service.is_configured:
                print("Email service not configured, skipping welcome email")
                return

            # Generate password reset token so they can set their password
            token = user.generate_reset_token()
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            subject = 'Welcome to the SDLL Umpire Academy!'
            body_text = f"""Hi {profile.first_name},

Thanks for registering your interest in the SDLL Umpire Academy!

Your account has been created. To set your password for future logins, click here:
{reset_url}

(This link expires in 24 hours, but you can always use "Forgot Password" later.)

What happens next:
- Complete your profile to tell us a bit about yourself
- Our umpire coordinator will review your registration
- You'll receive training session information via email

If you have any questions, just reply to this email.

- South Durham Little League Umpire Coordinator
"""
            body_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: rgb(34, 139, 34); padding: 20px; text-align: center;">
        <h1 style="color: white; margin: 0;">Welcome to SDLL Umpire Academy!</h1>
    </div>

    <div style="padding: 30px; background: #f8f9fa;">
        <p style="font-size: 16px; color: #333;">Hi {profile.first_name},</p>

        <p style="font-size: 16px; color: #333;">
            Thanks for registering your interest in the SDLL Umpire Academy!
        </p>

        <p style="font-size: 16px; color: #333;">
            Your account has been created. To set your password for future logins:
        </p>

        <p style="text-align: center; margin: 25px 0;">
            <a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background: rgb(34, 139, 34); color: white; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Set Your Password
            </a>
        </p>

        <p style="font-size: 14px; color: #666;">
            (This link expires in 24 hours, but you can always use "Forgot Password" later.)
        </p>

        <div style="background: white; border-radius: 8px; padding: 20px; margin: 20px 0;">
            <h3 style="color: #333; margin-top: 0;">What happens next:</h3>
            <ul style="color: #666; padding-left: 20px;">
                <li>Complete your profile to tell us a bit about yourself</li>
                <li>Our umpire coordinator will review your registration</li>
                <li>You'll receive training session information via email</li>
            </ul>
        </div>

        <p style="font-size: 14px; color: #666;">
            If you have any questions, just reply to this email.
        </p>

        <p style="font-size: 14px; color: #333;">
            - South Durham Little League Umpire Coordinator
        </p>
    </div>
</div>
"""
            email_service.send_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            print(f"Welcome email sent to {user.email[:3]}***")
        except Exception as e:
            print(f"Failed to send welcome email: {e}")

    @staticmethod
    def complete_profile(profile, birth_date=None, parent_first_name=None, parent_last_name=None,
                         parent_email=None, parent_phone=None, seasons_played=None,
                         highest_level_played=None, shirt_size=None, interested_sports=None,
                         kid_pitch_interest=None, availability_notes=None):
        """Phase II: Complete profile with additional information.

        Args:
            profile: The UmpireProfile to update
            birth_date: Umpire's birth date
            parent_first_name: Parent first name (required if minor)
            parent_last_name: Parent last name (required if minor)
            parent_email: Parent email address (required if minor)
            parent_phone: Parent phone number (optional)
            seasons_played: Number of LL seasons played
            highest_level_played: Highest LL division played
            shirt_size: Shirt size (XS, S, M, L, XL, XXL)
            interested_sports: 'baseball', 'softball', or 'both'
            kid_pitch_interest: Interest in kid-pitch games (1-5 scale)
            availability_notes: Free-form availability notes

        Returns:
            UmpireProfile: The updated profile
        """
        # Update birth date
        if birth_date:
            if isinstance(birth_date, str):
                profile.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            else:
                profile.birth_date = birth_date

        # Update parent info (for minors)
        if parent_first_name and parent_last_name:
            profile.parent_name = f"{parent_first_name} {parent_last_name}"
        if parent_email:
            profile.parent_email = parent_email
        if parent_phone:
            profile.parent_phone = parent_phone

        # Update profile fields
        if seasons_played is not None:
            profile.seasons_played = int(seasons_played) if seasons_played else None
        if highest_level_played:
            profile.highest_level_played = highest_level_played
        if shirt_size:
            profile.shirt_size = shirt_size
        if interested_sports:
            profile.interested_sports = interested_sports
        if kid_pitch_interest is not None:
            profile.kid_pitch_interest = int(kid_pitch_interest) if kid_pitch_interest else None
        if availability_notes:
            profile.availability_notes = availability_notes

        # Mark registration as completed
        profile.registration_completed_at = datetime.utcnow()
        profile.status = UmpireProfile.STATUS_PENDING_REVIEW

        db.session.commit()
        return profile

    @staticmethod
    def send_contact_message(name, email, message):
        """Send a contact message to the umpire coordinator.

        Args:
            name: Sender's name
            email: Sender's email (for reply)
            message: The message content

        Returns:
            bool: True if sent successfully
        """
        email_service = GmailService()
        if not email_service.is_configured:
            print("Email service not configured, cannot send contact message")
            raise Exception("Email service not configured")

        # Get umpire coordinator email from organization settings or use default
        coordinator_email = 'umpires@sdll.org'

        subject = f'Umpire Academy Question from {name}'
        body_text = f"""New question from the Umpire Academy contact form:

From: {name}
Email: {email}

Message:
{message}

---
Reply directly to this email to respond to {name}.
"""
        body_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: rgb(34, 139, 34); padding: 15px 20px;">
        <h2 style="color: white; margin: 0;">Umpire Academy Question</h2>
    </div>

    <div style="padding: 20px; background: #f8f9fa;">
        <p style="margin: 0 0 10px;"><strong>From:</strong> {name}</p>
        <p style="margin: 0 0 20px;"><strong>Email:</strong> <a href="mailto:{email}">{email}</a></p>

        <div style="background: white; border-radius: 8px; padding: 20px; border-left: 4px solid rgb(34, 139, 34);">
            <p style="margin: 0; white-space: pre-wrap;">{message}</p>
        </div>

        <p style="margin: 20px 0 0; font-size: 14px; color: #666;">
            Reply directly to this email to respond to {name}.
        </p>
    </div>
</div>
"""
        email_service.send_email(
            to=coordinator_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            reply_to=email
        )
        return True

    @staticmethod
    def calculate_age_on_date(birth_date, reference_date=None):
        """Calculate age on a given date.

        Args:
            birth_date: Date of birth
            reference_date: Date to calculate age on (defaults to today)

        Returns:
            int: Age in years
        """
        if not birth_date:
            return None
        if reference_date is None:
            reference_date = date.today()

        return reference_date.year - birth_date.year - (
            (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day)
        )
