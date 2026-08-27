"""Authentication routes"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import limiter
from app.models.user import User
from app.utils.logging import SDLLLogger, logged_action

auth_bp = Blueprint('auth', __name__)
logger = SDLLLogger('auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        logger.info(f'Login attempt for email: {email[:3]}***')

        user = User.get_by_email(email)

        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.update_last_login()
            logger.info(f'Login successful for user ID: {user.ID}')

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))

        logger.info('Login failed - invalid credentials')
        flash('Invalid email or password', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logger.info(f'User {current_user.ID} logging out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('3 per minute')
def forgot_password():
    """Request password reset"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.get_by_email(email)

        if user:
            token = user.generate_reset_token()
            logger.info(f'Password reset requested for user ID: {user.ID}')

            # Send email with reset link
            try:
                from app.services.notification_service import GmailService
                email_service = GmailService()

                reset_url = url_for('auth.reset_password', token=token, _external=True)

                subject = 'SDLL - Set Your Password'
                body_text = f"""You requested to set or reset your password for South Durham Little League.

Click the link below to set your password:
{reset_url}

This link will expire in 24 hours.

If you did not request this, you can safely ignore this email.

- South Durham Little League
"""
                body_html = f"""
<p>You requested to set or reset your password for South Durham Little League.</p>

<p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: rgb(34, 139, 34); color: white; text-decoration: none; border-radius: 4px; font-weight: bold;">Set Your Password</a></p>

<p>Or copy this link: {reset_url}</p>

<p>This link will expire in 24 hours.</p>

<p>If you did not request this, you can safely ignore this email.</p>

<p>- South Durham Little League</p>
"""
                email_service.send_email(
                    to=user.email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html
                )
                logger.info(f'Password reset email sent to user ID: {user.ID}')
            except Exception as e:
                logger.error(f'Failed to send password reset email: {e}')

        # Always show success message to prevent email enumeration
        flash('If an account exists with that email, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    # Find user with this token
    user = User.query.filter_by(password_reset_token=token).first()

    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            user.set_password(password)
            user.clear_reset_token()
            logger.info(f'Password reset completed for user ID: {user.ID}')
            flash('Your password has been reset. Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)
