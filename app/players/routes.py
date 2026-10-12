"""Players blueprint routes - player management, evaluations, and metrics."""

from decimal import Decimal, InvalidOperation
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.players import players_bp
from app.extensions import db
from app.models.player import (
    Player, PlayerSeason, PlayerEvaluation,
    EvaluationMetric, PlayerEvaluationScore
)
from app.models.org_season import OrgSeason
from app.utils.auth import role_required


# =============================================================================
# Evaluation Metrics Management
# =============================================================================

@players_bp.route('/metrics')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def metrics_index():
    """List all evaluation metrics."""
    metrics = EvaluationMetric.query.order_by(
        EvaluationMetric.sort_order,
        EvaluationMetric.name
    ).all()

    # Group by category for display
    categories = {}
    for m in metrics:
        cat = m.category or 'other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(m)

    return render_template('players/metrics_index.html',
                           metrics=metrics,
                           categories=categories)


@players_bp.route('/metrics/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def metrics_new():
    """Create a new evaluation metric."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip().lower().replace(' ', '_')
        display_name = request.form.get('display_name', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        program = request.form.get('program', 'both')

        # Validate required fields
        if not name or not display_name:
            flash('Name and display name are required.', 'error')
            return redirect(url_for('players.metrics_new'))

        # Check for duplicate name
        existing = EvaluationMetric.query.filter_by(name=name).first()
        if existing:
            flash(f'A metric with name "{name}" already exists.', 'error')
            return redirect(url_for('players.metrics_new'))

        # Parse numeric fields
        try:
            min_score = Decimal(request.form.get('min_score', '1.0'))
            max_score = Decimal(request.form.get('max_score', '7.0'))
            score_increment = Decimal(request.form.get('score_increment', '0.5'))
            sort_order = int(request.form.get('sort_order', '100'))
        except (ValueError, InvalidOperation):
            flash('Invalid numeric value provided.', 'error')
            return redirect(url_for('players.metrics_new'))

        metric = EvaluationMetric(
            name=name,
            display_name=display_name,
            description=description,
            category=category,
            program=program,
            min_score=min_score,
            max_score=max_score,
            score_increment=score_increment,
            sort_order=sort_order,
            active=1
        )
        db.session.add(metric)
        db.session.commit()

        flash(f'Metric "{display_name}" created successfully.', 'success')
        return redirect(url_for('players.metrics_index'))

    # GET - show form
    categories = ['batting', 'fielding', 'pitching', 'running', 'other']
    programs = [('both', 'Both'), ('baseball', 'Baseball Only'), ('softball', 'Softball Only')]

    return render_template('players/metrics_form.html',
                           metric=None,
                           categories=categories,
                           programs=programs,
                           action='Create')


@players_bp.route('/metrics/<int:metric_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def metrics_edit(metric_id):
    """Edit an existing evaluation metric."""
    metric = EvaluationMetric.query.get_or_404(metric_id)

    if request.method == 'POST':
        metric.display_name = request.form.get('display_name', '').strip()
        metric.description = request.form.get('description', '').strip()
        metric.category = request.form.get('category', '').strip()
        metric.program = request.form.get('program', 'both')

        # Parse numeric fields
        try:
            metric.min_score = Decimal(request.form.get('min_score', '1.0'))
            metric.max_score = Decimal(request.form.get('max_score', '7.0'))
            metric.score_increment = Decimal(request.form.get('score_increment', '0.5'))
            metric.sort_order = int(request.form.get('sort_order', '100'))
        except (ValueError, InvalidOperation):
            flash('Invalid numeric value provided.', 'error')
            return redirect(url_for('players.metrics_edit', metric_id=metric_id))

        db.session.commit()
        flash(f'Metric "{metric.display_name}" updated successfully.', 'success')
        return redirect(url_for('players.metrics_index'))

    # GET - show form
    categories = ['batting', 'fielding', 'pitching', 'running', 'other']
    programs = [('both', 'Both'), ('baseball', 'Baseball Only'), ('softball', 'Softball Only')]

    return render_template('players/metrics_form.html',
                           metric=metric,
                           categories=categories,
                           programs=programs,
                           action='Update')


@players_bp.route('/metrics/<int:metric_id>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def metrics_toggle(metric_id):
    """Toggle a metric's active status."""
    metric = EvaluationMetric.query.get_or_404(metric_id)
    metric.active = 0 if metric.active else 1
    db.session.commit()

    status = 'activated' if metric.active else 'deactivated'
    flash(f'Metric "{metric.display_name}" {status}.', 'success')
    return redirect(url_for('players.metrics_index'))


@players_bp.route('/metrics/<int:metric_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def metrics_delete(metric_id):
    """Delete a metric (only if no scores exist)."""
    metric = EvaluationMetric.query.get_or_404(metric_id)

    # Check if any scores use this metric
    score_count = PlayerEvaluationScore.query.filter_by(metric_id=metric_id).count()
    if score_count > 0:
        flash(f'Cannot delete "{metric.display_name}" - {score_count} scores use this metric. '
              'Deactivate it instead.', 'error')
        return redirect(url_for('players.metrics_index'))

    db.session.delete(metric)
    db.session.commit()
    flash(f'Metric "{metric.display_name}" deleted.', 'success')
    return redirect(url_for('players.metrics_index'))


@players_bp.route('/metrics/reorder', methods=['POST'])
@login_required
@role_required('admin')
def metrics_reorder():
    """Update sort order for metrics (AJAX)."""
    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'error': 'Missing order data'}), 400

    for item in data['order']:
        metric_id = item.get('id')
        sort_order = item.get('sort_order')
        if metric_id and sort_order is not None:
            metric = EvaluationMetric.query.get(metric_id)
            if metric:
                metric.sort_order = sort_order

    db.session.commit()
    return jsonify({'success': True})


# =============================================================================
# CSV Import
# =============================================================================

@players_bp.route('/import')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_index():
    """Import dashboard - choose what to import."""
    # Get available seasons for import target
    seasons = OrgSeason.query.order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).limit(10).all()

    # Get current counts
    player_count = Player.query.count()
    current_season = OrgSeason.get_current_season()
    season_record_count = 0
    if current_season:
        season_record_count = PlayerSeason.query.filter_by(
            org_season_id=current_season.ID
        ).count()

    return render_template('players/import_index.html',
                           seasons=seasons,
                           player_count=player_count,
                           current_season=current_season,
                           season_record_count=season_record_count)


@players_bp.route('/import/registration', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_registration():
    """Upload and preview registration CSV."""
    import csv
    import io
    from datetime import datetime
    from flask import session
    from app.services.player_import_service import (
        auto_map_columns, all_required_columns_mapped, EXPECTED_REGISTRATION_COLUMNS
    )

    # Get available seasons
    seasons = OrgSeason.query.order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).limit(10).all()

    if request.method == 'POST':
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('players.import_registration'))

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('players.import_registration'))

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return redirect(url_for('players.import_registration'))

        # Get target season
        season_id = request.form.get('season_id')
        if not season_id:
            flash('Please select a target season.', 'error')
            return redirect(url_for('players.import_registration'))

        org_season = OrgSeason.query.get(season_id)
        if not org_season:
            flash('Invalid season selected.', 'error')
            return redirect(url_for('players.import_registration'))

        # Get sport selection
        program = request.form.get('program')
        if program not in ('baseball', 'softball'):
            flash('Please select a sport.', 'error')
            return redirect(url_for('players.import_registration'))

        # Read and parse CSV
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            rows = list(reader)
        except Exception as e:
            flash(f'Error reading CSV: {str(e)}', 'error')
            return redirect(url_for('players.import_registration'))

        if not rows:
            flash('CSV file is empty.', 'error')
            return redirect(url_for('players.import_registration'))

        # Auto-map columns using aliases
        csv_headers = reader.fieldnames
        column_mapping = auto_map_columns(csv_headers)

        # Store CSV content and settings in session
        stream.seek(0)
        session['import_csv'] = stream.read()
        session['import_csv_headers'] = csv_headers
        session['import_season_id'] = int(season_id)
        session['import_program'] = program
        session['import_create_users'] = request.form.get('create_users') == '1'
        session['import_column_mapping'] = column_mapping

        # Check if all required columns are mapped
        if not all_required_columns_mapped(column_mapping):
            # Redirect to column mapping page
            return redirect(url_for('players.import_column_mapping'))

        # All required columns mapped - proceed to preview
        return redirect(url_for('players.import_preview'))

    # GET - show upload form
    return render_template('players/import_registration.html',
                           seasons=seasons)


@players_bp.route('/import/registration/mapping', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_column_mapping():
    """Column mapping UI for CSV import."""
    from flask import session
    from app.services.player_import_service import (
        EXPECTED_REGISTRATION_COLUMNS, all_required_columns_mapped
    )

    # Check session data exists
    csv_content = session.get('import_csv')
    csv_headers = session.get('import_csv_headers')
    column_mapping = session.get('import_column_mapping', {})

    if not csv_content or not csv_headers:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.import_registration'))

    if request.method == 'POST':
        # Update column mapping from form
        new_mapping = {}
        for expected in EXPECTED_REGISTRATION_COLUMNS:
            selected = request.form.get(f'map_{expected.name}', '').strip()
            new_mapping[expected.name] = selected if selected else None

        session['import_column_mapping'] = new_mapping

        # Validate required columns
        if not all_required_columns_mapped(new_mapping):
            flash('Please map all required columns before continuing.', 'error')
            return redirect(url_for('players.import_column_mapping'))

        # Proceed to preview
        return redirect(url_for('players.import_preview'))

    # GET - show mapping form
    org_season = OrgSeason.query.get(session.get('import_season_id'))

    return render_template('players/import_column_mapping.html',
                           expected_columns=EXPECTED_REGISTRATION_COLUMNS,
                           csv_headers=csv_headers,
                           column_mapping=column_mapping,
                           org_season=org_season,
                           program=session.get('import_program'))


@players_bp.route('/import/registration/preview')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_preview():
    """Preview import after column mapping."""
    import csv
    import io
    from datetime import datetime
    from flask import session
    from app.utils.encryption import hash_for_lookup
    from app.models.user import User

    # Get session data
    csv_content = session.get('import_csv')
    column_mapping = session.get('import_column_mapping', {})
    season_id = session.get('import_season_id')
    program = session.get('import_program')
    create_users = session.get('import_create_users', False)

    if not csv_content or not season_id:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.import_registration'))

    org_season = OrgSeason.query.get(season_id)
    if not org_season:
        flash('Invalid season.', 'error')
        return redirect(url_for('players.import_registration'))

    # Parse CSV
    stream = io.StringIO(csv_content)
    reader = csv.DictReader(stream)
    rows = list(reader)

    # Pre-load existing players and users for fast lookup
    existing_players = Player.query.all()
    player_cache = {}
    for p in existing_players:
        key = (p.parent_email_hash, p.name_hash)
        player_cache[key] = p

    existing_users = User.query.all()
    user_cache = {u.email_hash: u for u in existing_users if u.email_hash}

    # Helper to get field value using mapping
    def get_field(row, field_name):
        csv_col = column_mapping.get(field_name)
        if csv_col:
            return row.get(csv_col, '').strip()
        return row.get(field_name, '').strip()

    # Parse and validate ALL rows for accurate counts
    preview_rows = []
    errors = []

    # Track unique emails for parent counts
    emails_seen = set()
    new_parents = 0
    returning_parents = 0
    new_players = 0
    returning_players = 0

    for i, row in enumerate(rows, start=2):
        email = get_field(row, 'User Email')
        first_name = get_field(row, 'Player First Name')
        last_name = get_field(row, 'Player Last Name')
        birth_date_str = get_field(row, 'Player Birth Date')
        division = get_field(row, 'Division Name')

        # Validate
        if not email or not first_name or not last_name:
            errors.append(f'Row {i}: Missing required field (email, first name, or last name)')
            continue

        # Parse birth date
        birth_date = None
        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y', '%m/%d/%y']:
            try:
                birth_date = datetime.strptime(birth_date_str, fmt).date()
                break
            except ValueError:
                continue

        if not birth_date:
            errors.append(f'Row {i}: Invalid birth date "{birth_date_str}"')
            continue

        # Check if player exists using cache
        email_hash = hash_for_lookup(email)
        name_normalized = f"{first_name}{last_name}".lower().replace(' ', '').replace('-', '')
        name_hash = hash_for_lookup(name_normalized)
        player_key = (email_hash, name_hash)

        existing_player = player_cache.get(player_key)
        player_exists = existing_player is not None

        if player_exists:
            returning_players += 1
        else:
            new_players += 1

        # Check if parent user exists (only count each email once)
        if email not in emails_seen:
            emails_seen.add(email)
            if email_hash in user_cache:
                returning_parents += 1
            else:
                new_parents += 1

        # Only include first 100 rows in preview table
        if len(preview_rows) < 100:
            preview_rows.append({
                'row_num': i,
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'birth_date': birth_date,
                'division': division,
                'exists': player_exists,
                'player_id': existing_player.id if existing_player else None
            })

    # Build stats dict
    import_stats = {
        'new_players': new_players,
        'returning_players': returning_players,
        'new_parents': new_parents,
        'returning_parents': returning_parents,
        'unique_emails': len(emails_seen)
    }

    return render_template('players/import_preview.html',
                           org_season=org_season,
                           program=program,
                           preview_rows=preview_rows,
                           total_rows=len(rows),
                           errors=errors[:20],
                           total_errors=len(errors),
                           columns=reader.fieldnames,
                           create_users=create_users,
                           import_stats=import_stats)


@players_bp.route('/import/registration/confirm', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_registration_confirm():
    """Process the confirmed import."""
    from flask import session
    from app.services.player_import_service import PlayerImportService
    import io

    # Get stored data from session
    csv_content = session.pop('import_csv', None)
    season_id = session.pop('import_season_id', None)
    program = session.pop('import_program', None)
    create_users = session.pop('import_create_users', False)
    column_mapping = session.pop('import_column_mapping', None)
    # Clean up other session keys
    session.pop('import_csv_headers', None)

    if not csv_content or not season_id or not program:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.import_registration'))

    org_season = OrgSeason.query.get(season_id)
    if not org_season:
        flash('Invalid season.', 'error')
        return redirect(url_for('players.import_registration'))

    # Process import
    try:
        # Write to temp file for import service
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                          delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            service = PlayerImportService(org_season)
            stats = service.import_registration_csv(
                temp_path,
                program=program,
                create_parent_users=create_users,
                column_mapping=column_mapping
            )
        finally:
            os.unlink(temp_path)

        # Show results
        flash(f'Import complete! Created {stats["players_created"]} players, '
              f'updated {stats["players_updated"]}, '
              f'created {stats["parent_users_created"]} parent accounts.', 'success')

        if stats['errors']:
            # Store errors for display
            session['import_errors'] = stats['errors'][:50]
            return redirect(url_for('players.import_results'))

        return redirect(url_for('players.import_index'))

    except Exception as e:
        flash(f'Import failed: {str(e)}', 'error')
        return redirect(url_for('players.import_registration'))


@players_bp.route('/import/results')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def import_results():
    """Show import results with any errors."""
    from flask import session

    errors = session.pop('import_errors', [])
    return render_template('players/import_results.html', errors=errors)


# =============================================================================
# Player Listing
# =============================================================================

@players_bp.route('/')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def index():
    """Player management dashboard."""
    # Get current season stats
    current_season = OrgSeason.get_current_season()
    player_count = Player.query.count()
    season_record_count = 0
    if current_season:
        season_record_count = PlayerSeason.query.filter_by(
            org_season_id=current_season.ID
        ).count()

    return render_template('players/index.html',
                           current_season=current_season,
                           player_count=player_count,
                           season_record_count=season_record_count)
