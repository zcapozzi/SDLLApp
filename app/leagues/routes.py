"""League management routes"""

from datetime import time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.league import League
from app.models.field import Field
from app.extensions import db
from app.utils.logging import SDLLLogger

leagues_bp = Blueprint('leagues', __name__)
logger = SDLLLogger('leagues')


@leagues_bp.route('/')
@login_required
def index():
    """List all leagues"""
    leagues = League.get_all_active()
    return render_template('leagues/index.html', leagues=leagues)


@leagues_bp.route('/pitch-types', methods=['GET', 'POST'])
@login_required
def pitch_types():
    """Manage league pitch types"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league settings.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        league_id = int(request.form.get('league_id'))
        pitch_type = request.form.get('pitch_type')

        league = League.query.get(league_id)
        if league and pitch_type in [p[0] for p in League.PITCH_TYPES]:
            league.pitch_type = pitch_type
            db.session.commit()
            logger.info(f'Set pitch type for {league.display_name}: {league.pitch_type_display}')
            flash(f'Set pitch type for {league.display_name}: {league.pitch_type_display}', 'success')

        return redirect(url_for('leagues.pitch_types') + f'#league-{league_id}')

    leagues = League.get_all_active()
    return render_template('leagues/pitch_types.html', leagues=leagues, pitch_types=League.PITCH_TYPES)


@leagues_bp.route('/seasonal-names', methods=['GET', 'POST'])
@login_required
def seasonal_names():
    """Manage league seasonal names"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league names.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        league_id = int(request.form.get('league_id'))
        fall_name = request.form.get('fall_display_name', '').strip()

        league = League.query.get(league_id)
        if league:
            league.fall_display_name = fall_name if fall_name else None
            db.session.commit()
            if fall_name:
                logger.info(f'Set fall name for {league.display_name}: {fall_name}')
                flash(f'Set fall name for {league.display_name}: {fall_name}', 'success')
            else:
                logger.info(f'Cleared fall name for {league.display_name}')
                flash(f'Cleared fall name for {league.display_name}', 'success')

        return redirect(url_for('leagues.seasonal_names') + f'#league-{league_id}')

    leagues = League.get_all_active()
    return render_template('leagues/seasonal_names.html', leagues=leagues)


@leagues_bp.route('/time-restrictions', methods=['GET', 'POST'])
@login_required
def time_restrictions():
    """Manage league time restrictions"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league restrictions.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        league_id = int(request.form.get('league_id'))
        earliest_str = request.form.get('earliest_start_time')
        latest_str = request.form.get('latest_start_time')

        league = League.query.get(league_id)
        if league:
            # Parse times (empty string = no restriction)
            league.earliest_start_time = time.fromisoformat(earliest_str) if earliest_str else None
            league.latest_start_time = time.fromisoformat(latest_str) if latest_str else None
            db.session.commit()
            logger.info(f'Updated time restrictions for {league.display_name}: {league.time_restriction_display}')
            flash(f'Updated time restrictions for {league.display_name}', 'success')

        return redirect(url_for('leagues.time_restrictions') + f'#league-{league_id}')

    leagues = League.get_all_active()
    return render_template('leagues/time_restrictions.html', leagues=leagues)


@leagues_bp.route('/field-rules', methods=['GET', 'POST'])
@login_required
def field_rules():
    """Manage league field rules - where each league can play games/practices"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league field rules.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        league_id = int(request.form.get('league_id'))
        league = League.query.get(league_id)

        if league:
            # Get selected field IDs from form
            game_fields = request.form.getlist('game_fields')
            practice_fields = request.form.getlist('practice_fields')
            preferred_fields = request.form.getlist('preferred_fields')

            # Convert to integers and store
            league.allowed_game_field_ids = [int(f) for f in game_fields] if game_fields else []
            league.allowed_practice_field_ids = [int(f) for f in practice_fields] if practice_fields else []
            league.preferred_field_ids = [int(f) for f in preferred_fields] if preferred_fields else []

            db.session.commit()
            logger.info(f'Updated field rules for {league.display_name}')
            flash(f'Updated field rules for {league.display_name}', 'success')

        return redirect(url_for('leagues.field_rules') + f'#league-{league_id}')

    leagues = League.get_all_active()
    # Only show SDLL-owned fields (not away fields)
    fields = Field.query.filter_by(active=1, is_owned=1).order_by(Field.location_title).all()

    return render_template(
        'leagues/field_rules.html',
        leagues=leagues,
        fields=fields
    )


@leagues_bp.route('/field-rules/save-all', methods=['POST'])
@login_required
def field_rules_save_all():
    """Save field rules for all leagues at once"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league field rules.', 'error')
        return redirect(url_for('leagues.index'))

    leagues = League.get_all_active()
    updated_count = 0

    for league in leagues:
        # Get selected field IDs from form using league-specific field names
        game_fields = request.form.getlist(f'game_fields_{league.ID}')
        practice_fields = request.form.getlist(f'practice_fields_{league.ID}')
        preferred_fields = request.form.getlist(f'preferred_fields_{league.ID}')

        # Convert to integers and store
        league.allowed_game_field_ids = [int(f) for f in game_fields] if game_fields else []
        league.allowed_practice_field_ids = [int(f) for f in practice_fields] if practice_fields else []
        league.preferred_field_ids = [int(f) for f in preferred_fields] if preferred_fields else []
        updated_count += 1

    db.session.commit()
    logger.info(f'Updated field rules for {updated_count} leagues')
    flash(f'Updated field rules for all {updated_count} leagues', 'success')

    return redirect(url_for('leagues.field_rules'))


@leagues_bp.route('/umpire-patterns', methods=['GET', 'POST'])
@login_required
def umpire_patterns():
    """Manage umpire requirements per league"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage umpire patterns.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        league_id = int(request.form.get('league_id'))
        league = League.query.get(league_id)

        if league:
            # Parse umpire counts (empty = 0 for regular, NULL for playoffs)
            umpire_count_str = request.form.get('umpire_count', '0')
            umpire_count_playoffs_str = request.form.get('umpire_count_playoffs', '')

            league.umpire_count = int(umpire_count_str) if umpire_count_str else 0

            # Playoffs: empty means "same as regular season" (NULL)
            if umpire_count_playoffs_str == '' or umpire_count_playoffs_str == 'same':
                league.umpire_count_playoffs = None
            else:
                league.umpire_count_playoffs = int(umpire_count_playoffs_str)

            db.session.commit()
            logger.info(f'Updated umpire pattern for {league.display_name}: {league.umpire_count_display}')
            flash(f'Updated umpire settings for {league.display_name}', 'success')

        return redirect(url_for('leagues.umpire_patterns') + f'#league-{league_id}')

    leagues = League.get_all_active()
    return render_template('leagues/umpire_patterns.html', leagues=leagues)


@leagues_bp.route('/rules', methods=['GET', 'POST'])
@login_required
def rules():
    """Manage league rules document URLs"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage league rules.', 'error')
        return redirect(url_for('leagues.index'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_single':
            league_id = int(request.form.get('league_id'))
            rules_url = request.form.get('rules_doc_url', '').strip()

            league = League.query.get(league_id)
            if league:
                league.rules_doc_url = rules_url if rules_url else None
                db.session.commit()
                if rules_url:
                    logger.info(f'Set rules URL for {league.display_name}')
                    flash(f'Updated rules URL for {league.display_name}', 'success')
                else:
                    logger.info(f'Cleared rules URL for {league.display_name}')
                    flash(f'Cleared rules URL for {league.display_name}', 'success')

            return redirect(url_for('leagues.rules') + f'#league-{league_id}')

        elif action == 'save_all':
            leagues = League.get_all_active()
            updated_count = 0

            for league in leagues:
                rules_url = request.form.get(f'rules_url_{league.ID}', '').strip()
                new_url = rules_url if rules_url else None

                if league.rules_doc_url != new_url:
                    league.rules_doc_url = new_url
                    updated_count += 1

            db.session.commit()
            logger.info(f'Updated rules URLs for {updated_count} leagues')
            flash(f'Saved rules URLs ({updated_count} updated)', 'success')

            return redirect(url_for('leagues.rules'))

    leagues = League.get_all_active()
    return render_template('leagues/rules.html', leagues=leagues)
