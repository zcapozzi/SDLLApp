"""Routes for Umpire Academy registration flow."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user, login_user

from app.extensions import limiter
from app.models.umpire_profile import UmpireProfile
from app.models.user import User
from app.services.umpire_academy_service import UmpireAcademyService
from app.utils.logging import SDLLLogger

umpire_academy_bp = Blueprint('umpire_academy', __name__)
logger = SDLLLogger('umpire_academy')


@umpire_academy_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def register():
    """Phase I: Interest registration - creates User and UmpireProfile, then proceeds to profile."""
    # If already logged in with an umpire profile, go to profile completion
    if current_user.is_authenticated:
        profile = UmpireProfile.get_by_user_id(current_user.ID)
        if profile:
            if profile.registration_completed_at:
                return redirect(url_for('umpire_academy.profile_complete'))
            return redirect(url_for('umpire_academy.profile'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip() or None

        errors = []

        # Validate required fields
        if not first_name:
            errors.append('First name is required')
        if not last_name:
            errors.append('Last name is required')
        if not email:
            errors.append('Email is required')
        elif '@' not in email:
            errors.append('Please enter a valid email address')

        # Check if email already exists
        if email:
            existing_user = User.get_by_email(email)
            if existing_user:
                # Check if they already have an umpire profile
                existing_profile = UmpireProfile.get_by_user_id(existing_user.ID)
                if existing_profile:
                    errors.append('An account with this email already exists. Please log in instead.')
                else:
                    # They have a user account but no umpire profile - we'll create one
                    pass

        if errors:
            return render_template('umpire_academy/register.html',
                                   errors=errors,
                                   form_data={
                                       'first_name': first_name,
                                       'last_name': last_name,
                                       'email': email,
                                       'phone': phone
                                   })

        try:
            user, profile = UmpireAcademyService.register_interest(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone
            )
            logger.info(f'Umpire Academy registration: user={user.ID}, profile={profile.id}')

            # Auto-login and redirect to profile completion
            login_user(user)
            return redirect(url_for('umpire_academy.profile'))

        except Exception as e:
            logger.error(f'Failed to register umpire academy interest: {e}')
            errors.append('An error occurred. Please try again.')
            return render_template('umpire_academy/register.html',
                                   errors=errors,
                                   form_data={
                                       'first_name': first_name,
                                       'last_name': last_name,
                                       'email': email,
                                       'phone': phone
                                   })

    return render_template('umpire_academy/register.html',
                           errors=[],
                           form_data={})


@umpire_academy_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Profile completion form - collects additional info."""
    # Get the user's umpire profile
    profile = UmpireProfile.get_by_user_id(current_user.ID)

    if not profile:
        flash('No umpire profile found.', 'error')
        return redirect(url_for('main.dashboard'))

    # If profile is already completed, redirect to success
    if profile.registration_completed_at:
        return redirect(url_for('umpire_academy.profile_complete'))

    if request.method == 'POST':
        # Extract form data
        birth_date = request.form.get('birth_date', '').strip() or None
        parent_first_name = request.form.get('parent_first_name', '').strip() or None
        parent_last_name = request.form.get('parent_last_name', '').strip() or None
        parent_email = request.form.get('parent_email', '').strip().lower() or None
        parent_phone = request.form.get('parent_phone', '').strip() or None
        seasons_played = request.form.get('seasons_played', '').strip() or None
        highest_level_played = request.form.get('highest_level_played', '').strip() or None
        shirt_size = request.form.get('shirt_size', '').strip() or None
        interested_sports = request.form.get('interested_sports', '').strip() or None
        kid_pitch_interest = request.form.get('kid_pitch_interest', '').strip() or None
        availability_notes = request.form.get('availability_notes', '').strip() or None

        errors = []

        # Birth date is required
        if not birth_date:
            errors.append('Date of birth is required')
        else:
            from datetime import datetime
            try:
                bd = datetime.strptime(birth_date, '%Y-%m-%d').date()
                age = UmpireAcademyService.calculate_age_on_date(bd)
                if age is not None and age < 18:
                    # Minor - parent info required
                    if not parent_first_name or not parent_last_name:
                        errors.append('Parent name is required for umpires under 18')
                    if not parent_email:
                        errors.append('Parent email is required for umpires under 18')
            except ValueError:
                errors.append('Invalid birth date format')

        if errors:
            return render_template('umpire_academy/profile.html',
                                   profile=profile,
                                   errors=errors,
                                   form_data=request.form)

        try:
            UmpireAcademyService.complete_profile(
                profile=profile,
                birth_date=birth_date,
                parent_first_name=parent_first_name,
                parent_last_name=parent_last_name,
                parent_email=parent_email,
                parent_phone=parent_phone,
                seasons_played=seasons_played,
                highest_level_played=highest_level_played,
                shirt_size=shirt_size,
                interested_sports=interested_sports,
                kid_pitch_interest=kid_pitch_interest,
                availability_notes=availability_notes
            )
            logger.info(f'Umpire Academy profile completed: profile={profile.id}')

            return redirect(url_for('umpire_academy.profile_complete'))
        except Exception as e:
            logger.error(f'Failed to complete umpire academy profile: {e}')
            errors.append('An error occurred. Please try again.')
            return render_template('umpire_academy/profile.html',
                                   profile=profile,
                                   errors=errors,
                                   form_data=request.form)

    return render_template('umpire_academy/profile.html',
                           profile=profile,
                           errors=[],
                           form_data={})


@umpire_academy_bp.route('/complete')
@login_required
def profile_complete():
    """Final success page after completing registration."""
    profile = UmpireProfile.get_by_user_id(current_user.ID)
    return render_template('umpire_academy/profile_complete.html', profile=profile)


@umpire_academy_bp.route('/contact', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def contact():
    """Contact form for questions before signing up."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        message = request.form.get('message', '').strip()

        errors = []

        if not name:
            errors.append('Name is required')
        if not email:
            errors.append('Email is required')
        elif '@' not in email:
            errors.append('Please enter a valid email address')
        if not message:
            errors.append('Message is required')

        if errors:
            return render_template('umpire_academy/contact.html',
                                   errors=errors,
                                   form_data={
                                       'name': name,
                                       'email': email,
                                       'message': message
                                   })

        try:
            UmpireAcademyService.send_contact_message(name, email, message)
            logger.info(f'Umpire Academy contact form submitted by {email[:3]}***')
            return render_template('umpire_academy/contact_success.html')
        except Exception as e:
            logger.error(f'Failed to send umpire academy contact message: {e}')
            errors.append('An error occurred sending your message. Please try again.')
            return render_template('umpire_academy/contact.html',
                                   errors=errors,
                                   form_data={
                                       'name': name,
                                       'email': email,
                                       'message': message
                                   })

    return render_template('umpire_academy/contact.html',
                           errors=[],
                           form_data={})


# Legacy routes for backwards compatibility
@umpire_academy_bp.route('/success')
def register_success():
    """Legacy route - redirect to profile or register."""
    if current_user.is_authenticated:
        return redirect(url_for('umpire_academy.profile'))
    return redirect(url_for('umpire_academy.register'))


@umpire_academy_bp.route('/complete/<token>', methods=['GET', 'POST'])
def complete_registration(token):
    """Legacy token-based route - redirect to register."""
    flash('Please register again using the form below.', 'info')
    return redirect(url_for('umpire_academy.register'))
