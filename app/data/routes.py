"""Data Management routes for player evals, placement, and surveys."""

from flask import render_template
from flask_login import login_required, current_user
from functools import wraps

from app.data import data_bp


def data_manager_required(f):
    """Decorator to require DataManager or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        if not current_user.has_role('admin', 'DataManager'):
            from flask import flash, redirect, url_for
            flash('You do not have permission to access data management.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@data_bp.route('/player-evals')
@login_required
@data_manager_required
def player_evals():
    """Player evaluations management."""
    return render_template('data/player_evals.html')


@data_bp.route('/player-placement')
@login_required
@data_manager_required
def player_placement():
    """Player placement and draft management."""
    return render_template('data/player_placement.html')


@data_bp.route('/surveys')
@login_required
@data_manager_required
def surveys():
    """Survey management and results."""
    return render_template('data/surveys.html')
