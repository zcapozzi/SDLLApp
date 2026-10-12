"""Players blueprint routes - player management, evaluations, and metrics."""

from decimal import Decimal, InvalidOperation
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.players import players_bp
from app.extensions import db
from app.models.player import (
    Player, PlayerSeason, PlayerEvaluation,
    EvaluationMetric, PlayerEvaluationScore, EvaluationMetricAgeRange
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
# Evaluation Metric Age Ranges
# =============================================================================

@players_bp.route('/metrics/<int:metric_id>/age-ranges', methods=['POST'])
@login_required
@role_required('admin')
def metrics_save_age_ranges(metric_id):
    """Save all age-specific score ranges for a metric (bulk upsert)."""
    metric = EvaluationMetric.query.get_or_404(metric_id)

    # Build a lookup of existing ranges by age
    existing_by_age = {ar.min_age: ar for ar in metric.age_ranges if ar.min_age == ar.max_age}

    updates = 0
    inserts = 0
    clears = 0

    # Process each age from 4 to 18
    for age in range(4, 19):
        min_score_str = request.form.get(f'min_score_{age}', '').strip()
        max_score_str = request.form.get(f'max_score_{age}', '').strip()
        increment_str = request.form.get(f'increment_{age}', '').strip()

        # Check if user wants to clear this age (use default)
        use_default = request.form.get(f'use_default_{age}') == '1'

        existing = existing_by_age.get(age)

        if use_default or (not min_score_str and not max_score_str):
            # User wants to use default - delete any existing custom range
            if existing:
                db.session.delete(existing)
                clears += 1
            continue

        # Parse values
        try:
            min_score = Decimal(min_score_str) if min_score_str else None
            max_score = Decimal(max_score_str) if max_score_str else None
            increment = Decimal(increment_str) if increment_str else Decimal('0.5')
        except (ValueError, InvalidOperation):
            continue  # Skip invalid entries

        # Validate
        if min_score is None or max_score is None:
            continue
        if min_score >= max_score:
            continue
        if increment <= 0:
            increment = Decimal('0.5')

        if existing:
            # Update existing range
            existing.min_score = min_score
            existing.max_score = max_score
            existing.score_increment = increment
            updates += 1
        else:
            # Insert new range
            age_range = EvaluationMetricAgeRange(
                metric_id=metric_id,
                min_age=age,
                max_age=age,  # Single age, not a range
                min_score=min_score,
                max_score=max_score,
                score_increment=increment
            )
            db.session.add(age_range)
            inserts += 1

    db.session.commit()

    # Build flash message
    changes = []
    if inserts:
        changes.append(f'{inserts} added')
    if updates:
        changes.append(f'{updates} updated')
    if clears:
        changes.append(f'{clears} reset to default')

    if changes:
        flash(f'Age ranges saved: {", ".join(changes)}.', 'success')
    else:
        flash('No changes made.', 'info')

    return redirect(url_for('players.metrics_edit', metric_id=metric_id) + '#age-ranges')


@players_bp.route('/metrics/<int:metric_id>/age-ranges/<int:age>/clear', methods=['POST'])
@login_required
@role_required('admin')
def metrics_clear_age_range(metric_id, age):
    """Clear a specific age's custom range (revert to default)."""
    metric = EvaluationMetric.query.get_or_404(metric_id)

    # Find and delete the range for this specific age
    deleted = EvaluationMetricAgeRange.query.filter_by(
        metric_id=metric_id,
        min_age=age,
        max_age=age
    ).delete()

    db.session.commit()

    if deleted:
        flash(f'Age {age} reset to use default range.', 'success')
    else:
        flash(f'Age {age} was already using default range.', 'info')

    return redirect(url_for('players.metrics_edit', metric_id=metric_id) + f'#age-{age}')


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

def _build_seasons_summary(recent_seasons):
    """Build summary of recent seasons with player counts and new player percentages.

    Args:
        recent_seasons: List of OrgSeason objects (most recent first)

    Returns:
        Dict with 'baseball' and 'softball' keys, each containing a list of season stats
    """
    from sqlalchemy import func

    # Get all season IDs we're interested in
    season_ids = [s.ID for s in recent_seasons]
    if not season_ids:
        return {'baseball': [], 'softball': []}

    # Build a map of season_id -> season for quick lookup
    season_map = {s.ID: s for s in recent_seasons}

    # Query player counts per season per sport
    # Join PlayerSeason with Player to get program (sport)
    stats_query = db.session.query(
        PlayerSeason.org_season_id,
        Player.program,
        func.count(PlayerSeason.id).label('total')
    ).join(
        Player, PlayerSeason.player_id == Player.id
    ).filter(
        PlayerSeason.org_season_id.in_(season_ids),
        Player.program.in_(['baseball', 'softball'])
    ).group_by(
        PlayerSeason.org_season_id,
        Player.program
    ).all()

    # Build lookup: (season_id, sport) -> count
    count_lookup = {}
    for row in stats_query:
        count_lookup[(row.org_season_id, row.program)] = row.total

    # For each season, we need to find "new" players
    # A player is "new" if they have no prior PlayerSeason records
    # We need to use chronological order (year, is_spring) not org_season_id
    # because IDs may not reflect actual chronological order

    # Create a chronological order value: year * 10 + (1 for spring, 2 for fall)
    # This ensures Spring 2024 (20241) < Fall 2024 (20242) < Spring 2025 (20251)
    season_order = OrgSeason.year * 10 + db.case(
        (OrgSeason.is_spring == 1, 1),  # Spring = 1
        else_=2  # Fall = 2
    )

    # Get the chronologically earliest season for each player
    first_season_subq = db.session.query(
        PlayerSeason.player_id,
        func.min(season_order).label('first_season_order')
    ).join(
        OrgSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).group_by(PlayerSeason.player_id).subquery()

    # Now find the actual org_season_id that matches this first season order
    # by joining back to get the season details
    player_first_season = db.session.query(
        PlayerSeason.player_id,
        PlayerSeason.org_season_id.label('first_season_id')
    ).join(
        OrgSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).join(
        first_season_subq, PlayerSeason.player_id == first_season_subq.c.player_id
    ).filter(
        (OrgSeason.year * 10 + db.case(
            (OrgSeason.is_spring == 1, 1),
            else_=2
        )) == first_season_subq.c.first_season_order
    ).subquery()

    # Count new players per season per sport
    # A player is "new" in a season if that season is their first season
    new_query = db.session.query(
        PlayerSeason.org_season_id,
        Player.program,
        func.count(PlayerSeason.id).label('new_count')
    ).join(
        Player, PlayerSeason.player_id == Player.id
    ).join(
        player_first_season, PlayerSeason.player_id == player_first_season.c.player_id
    ).filter(
        PlayerSeason.org_season_id.in_(season_ids),
        PlayerSeason.org_season_id == player_first_season.c.first_season_id,
        Player.program.in_(['baseball', 'softball'])
    ).group_by(
        PlayerSeason.org_season_id,
        Player.program
    ).all()

    # Build lookup: (season_id, sport) -> new_count
    new_lookup = {}
    for row in new_query:
        new_lookup[(row.org_season_id, row.program)] = row.new_count

    # Build the result grouped by sport
    result = {'baseball': [], 'softball': []}

    for season in recent_seasons:
        for sport in ['baseball', 'softball']:
            total = count_lookup.get((season.ID, sport), 0)
            new_count = new_lookup.get((season.ID, sport), 0)

            if total > 0:
                new_pct = round((new_count / total) * 100)
            else:
                new_pct = 0

            # Find prior year same season for trend comparison
            prior_season = None
            for s in recent_seasons:
                if s.year == season.year - 1 and s.is_spring == season.is_spring:
                    prior_season = s
                    break

            prior_total = 0
            if prior_season:
                prior_total = count_lookup.get((prior_season.ID, sport), 0)

            # Calculate trend (percentage change from prior year same season)
            trend = None
            if prior_total > 0:
                trend = round(((total - prior_total) / prior_total) * 100)

            result[sport].append({
                'season': season,
                'season_desc': season.season_desc,
                'total': total,
                'new_count': new_count,
                'returning_count': total - new_count,
                'new_pct': new_pct,
                'prior_total': prior_total,
                'trend': trend
            })

    return result


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

    # Get recent seasons with player data (last 4 seasons that have registrations)
    # Sort by year desc, then is_spring asc (Fall before Spring for same year)
    from sqlalchemy import func
    seasons_with_players = db.session.query(OrgSeason).join(
        PlayerSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).filter(
        OrgSeason.org_id == 1
    ).group_by(OrgSeason.ID).order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.asc()  # Fall (0) before Spring (1) within same year
    ).limit(4).all()

    # Build seasons summary with player counts by sport
    seasons_summary = _build_seasons_summary(seasons_with_players)

    return render_template('players/index.html',
                           current_season=current_season,
                           player_count=player_count,
                           season_record_count=season_record_count,
                           seasons_summary=seasons_summary)


# =============================================================================
# Player Pool and Roster Management
# =============================================================================

@players_bp.route('/pool')
@players_bp.route('/pool/<int:org_season_id>')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def player_pool(org_season_id=None):
    """View player pool for a season with filters."""
    from app.services.roster_service import RosterService
    from app.models.league import League
    from app.models.team import TeamSeason

    # Default to current season if not provided
    if org_season_id is None:
        current_season = OrgSeason.get_current_season()
        if current_season:
            org_season_id = current_season.ID
        else:
            flash('No current season found.', 'error')
            return redirect(url_for('players.index'))

    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Get filter parameters from query string
    league_id = request.args.get('league_id', type=int)
    status = request.args.get('status')
    sport = request.args.get('sport')

    # Get players with filters
    players = RosterService.get_player_pool(
        org_season_id,
        league_id=league_id,
        status=status,
        sport=sport
    )

    # Get pool statistics
    stats = RosterService.get_pool_stats(org_season_id, sport=sport)

    # Get available leagues and teams for filtering/assignment
    leagues = RosterService.get_leagues_for_season(org_season_id, sport=sport)
    teams = RosterService.get_available_teams(org_season_id)

    # Get all seasons for season selector
    seasons = OrgSeason.query.order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).limit(10).all()

    return render_template('players/pool.html',
                           org_season=org_season,
                           players=players,
                           stats=stats,
                           leagues=leagues,
                           teams=teams,
                           seasons=seasons,
                           current_league_id=league_id,
                           current_status=status,
                           current_sport=sport)


@players_bp.route('/roster/<int:team_id>')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def team_roster(team_id):
    """View roster for a specific team."""
    from app.services.roster_service import RosterService
    from app.models.team import TeamSeason

    team = RosterService.get_team_with_roster(team_id)
    if not team:
        flash('Team not found.', 'error')
        return redirect(url_for('players.index'))

    # Get org_season for this team's year/is_spring
    org_season = OrgSeason.query.filter_by(
        year=team.year,
        is_spring=team.is_spring,
        org_id=1
    ).first()

    # Get available players (unassigned in same league)
    available_players = []
    if org_season:
        all_pool = RosterService.get_player_pool(org_season.ID, league_id=team.league_id)
        available_players = [p for p in all_pool if not p.team_id]

    # Get roster
    roster = RosterService.get_team_roster(team_id)

    return render_template('players/team_roster.html',
                           team=team,
                           org_season=org_season,
                           roster=roster,
                           available_players=available_players)


@players_bp.route('/<int:player_season_id>/assign', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def assign_player(player_season_id):
    """Assign a player to a team. Supports both form POST and AJAX."""
    from app.services.roster_service import RosterService

    # Handle both form data and JSON
    if request.is_json:
        team_id = request.json.get('team_id')
    else:
        team_id = request.form.get('team_id', type=int)

    if not team_id:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Please select a team.'}), 400
        flash('Please select a team.', 'error')
        return redirect(request.referrer or url_for('players.player_pool'))

    try:
        player_season = RosterService.assign_player(player_season_id, team_id)

        if request.is_json:
            # Return data needed to update the UI
            return jsonify({
                'success': True,
                'player_season_id': player_season.id,
                'team_id': player_season.team_id,
                'team_display': f"{player_season.team.league_display_name} {player_season.team.scheduler_display_name}",
                'team_url': url_for('players.team_roster', team_id=player_season.team_id),
                'status': player_season.status
            })

        flash(f'Player assigned to team successfully.', 'success')
    except ValueError as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(str(e), 'error')

    # Redirect back with anchor to the player row
    referrer = request.referrer or url_for('players.player_pool')
    return redirect(referrer)


@players_bp.route('/<int:player_season_id>/unassign', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def unassign_player(player_season_id):
    """Remove a player from their team. Supports both form POST and AJAX."""
    from app.services.roster_service import RosterService

    try:
        player_season = RosterService.unassign_player(player_season_id)

        if request.is_json:
            return jsonify({
                'success': True,
                'player_season_id': player_season.id,
                'status': player_season.status
            })

        flash(f'Player removed from team.', 'success')
    except ValueError as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(str(e), 'error')

    # Redirect back
    referrer = request.referrer or url_for('players.player_pool')
    return redirect(referrer)


# =============================================================================
# Roster CSV Import
# =============================================================================

@players_bp.route('/pool/import', methods=['GET', 'POST'])
@players_bp.route('/pool/<int:org_season_id>/import', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def roster_import(org_season_id=None):
    """Upload roster CSV for batch assignments."""
    from flask import session
    from app.services.roster_service import RosterService, EXPECTED_ROSTER_COLUMNS

    # Default to current season
    if org_season_id is None:
        current_season = OrgSeason.get_current_season()
        if current_season:
            org_season_id = current_season.ID
        else:
            flash('No current season found.', 'error')
            return redirect(url_for('players.index'))

    org_season = OrgSeason.query.get_or_404(org_season_id)

    # Get available seasons
    seasons = OrgSeason.query.order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.desc()
    ).limit(10).all()

    if request.method == 'POST':
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('players.roster_import', org_season_id=org_season_id))

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('players.roster_import', org_season_id=org_season_id))

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return redirect(url_for('players.roster_import', org_season_id=org_season_id))

        # Read CSV content
        import io
        try:
            csv_content = file.stream.read().decode('utf-8-sig')
        except Exception as e:
            flash(f'Error reading CSV: {str(e)}', 'error')
            return redirect(url_for('players.roster_import', org_season_id=org_season_id))

        # Auto-map columns
        import csv
        stream = io.StringIO(csv_content)
        reader = csv.DictReader(stream)
        csv_headers = reader.fieldnames or []

        column_mapping = RosterService.auto_map_columns(csv_headers)

        # Store in session
        session['roster_import_csv'] = csv_content
        session['roster_import_season_id'] = org_season_id
        session['roster_import_column_mapping'] = column_mapping
        session['roster_import_csv_headers'] = csv_headers

        # Check if required columns are mapped
        if not RosterService.all_required_columns_mapped(column_mapping):
            flash('Some required columns could not be auto-mapped. Please map them manually.', 'warning')
            return redirect(url_for('players.roster_import_mapping', org_season_id=org_season_id))

        # Proceed to preview
        return redirect(url_for('players.roster_import_preview', org_season_id=org_season_id))

    return render_template('players/roster_import.html',
                           org_season=org_season,
                           seasons=seasons,
                           expected_columns=EXPECTED_ROSTER_COLUMNS)


@players_bp.route('/pool/<int:org_season_id>/import/mapping', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def roster_import_mapping(org_season_id):
    """Column mapping UI for roster import."""
    from flask import session
    from app.services.roster_service import RosterService, EXPECTED_ROSTER_COLUMNS

    org_season = OrgSeason.query.get_or_404(org_season_id)

    csv_content = session.get('roster_import_csv')
    csv_headers = session.get('roster_import_csv_headers', [])
    column_mapping = session.get('roster_import_column_mapping', {})

    if not csv_content:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.roster_import', org_season_id=org_season_id))

    if request.method == 'POST':
        # Update column mapping from form
        new_mapping = {}
        for expected in EXPECTED_ROSTER_COLUMNS:
            selected = request.form.get(f'map_{expected.name}', '').strip()
            new_mapping[expected.name] = selected if selected else None

        session['roster_import_column_mapping'] = new_mapping

        # Validate required columns
        if not RosterService.all_required_columns_mapped(new_mapping):
            flash('Please map all required columns before continuing.', 'error')
            return redirect(url_for('players.roster_import_mapping', org_season_id=org_season_id))

        return redirect(url_for('players.roster_import_preview', org_season_id=org_season_id))

    return render_template('players/roster_import_mapping.html',
                           org_season=org_season,
                           expected_columns=EXPECTED_ROSTER_COLUMNS,
                           csv_headers=csv_headers,
                           column_mapping=column_mapping)


@players_bp.route('/pool/<int:org_season_id>/import/preview')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def roster_import_preview(org_season_id):
    """Preview roster import matches."""
    from flask import session
    from app.services.roster_service import RosterService

    org_season = OrgSeason.query.get_or_404(org_season_id)

    csv_content = session.get('roster_import_csv')
    column_mapping = session.get('roster_import_column_mapping')

    if not csv_content:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.roster_import', org_season_id=org_season_id))

    # Parse and preview
    preview = RosterService.parse_roster_csv(csv_content, org_season_id, column_mapping)

    # Store preview in session for confirm step
    session['roster_import_preview'] = {
        'rows': [
            {
                'row_num': r.row_num,
                'player_code': r.player_code,
                'coach_name': r.coach_name,
                'player_season_id': r.player_season_id,
                'team_id': r.team_id,
                'match_status': r.match_status
            }
            for r in preview.rows
        ],
        'matched_count': preview.matched_count
    }

    return render_template('players/roster_import_preview.html',
                           org_season=org_season,
                           preview=preview)


@players_bp.route('/pool/<int:org_season_id>/import/confirm', methods=['POST'])
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def roster_import_confirm(org_season_id):
    """Execute the roster import."""
    from flask import session
    from app.services.roster_service import RosterService, RosterImportPreview, RosterImportRow

    org_season = OrgSeason.query.get_or_404(org_season_id)

    preview_data = session.pop('roster_import_preview', None)
    session.pop('roster_import_csv', None)
    session.pop('roster_import_column_mapping', None)
    session.pop('roster_import_csv_headers', None)

    if not preview_data:
        flash('Import session expired. Please upload the file again.', 'error')
        return redirect(url_for('players.roster_import', org_season_id=org_season_id))

    # Rebuild preview object
    preview = RosterImportPreview()
    for row_data in preview_data['rows']:
        preview.rows.append(RosterImportRow(
            row_num=row_data['row_num'],
            player_code=row_data['player_code'],
            coach_name=row_data['coach_name'],
            player_season_id=row_data['player_season_id'],
            team_id=row_data['team_id'],
            match_status=row_data['match_status']
        ))

    # Execute import
    result = RosterService.execute_roster_import(preview)

    if result['success_count'] > 0:
        flash(f"Successfully assigned {result['success_count']} players to teams.", 'success')

    if result['error_count'] > 0:
        flash(f"{result['error_count']} errors occurred during import.", 'error')

    return redirect(url_for('players.player_pool', org_season_id=org_season_id))


# =============================================================================
# Registration Trends
# =============================================================================

@players_bp.route('/registration-trends')
@login_required
@role_required('admin', 'BBPlayerAgent', 'SBPlayerAgent')
def registration_trends():
    """Registration trends report showing historical player data."""
    from sqlalchemy import func

    # Get all seasons with player data, ordered by date
    # Sort: year desc, is_spring asc (Fall before Spring for same year)
    # Only include seasons that have player registrations
    all_seasons = db.session.query(OrgSeason).join(
        PlayerSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).filter(
        OrgSeason.org_id == 1
    ).group_by(OrgSeason.ID).order_by(
        OrgSeason.year.desc(),
        OrgSeason.is_spring.asc()  # Fall (0) before Spring (1) within same year
    ).all()

    # Build comprehensive stats for all seasons
    season_ids = [s.ID for s in all_seasons]

    if not season_ids:
        return render_template('players/registration_trends.html',
                               seasons_data={'baseball': [], 'softball': []},
                               summary_stats={})

    # Query player counts per season per sport
    stats_query = db.session.query(
        PlayerSeason.org_season_id,
        Player.program,
        func.count(PlayerSeason.id).label('total')
    ).join(
        Player, PlayerSeason.player_id == Player.id
    ).filter(
        PlayerSeason.org_season_id.in_(season_ids),
        Player.program.in_(['baseball', 'softball'])
    ).group_by(
        PlayerSeason.org_season_id,
        Player.program
    ).all()

    count_lookup = {}
    for row in stats_query:
        count_lookup[(row.org_season_id, row.program)] = row.total

    # Get chronologically earliest season for each player (for new player calculation)
    # Use year * 10 + (1 for spring, 2 for fall) to ensure correct chronological order
    season_order = OrgSeason.year * 10 + db.case(
        (OrgSeason.is_spring == 1, 1),
        else_=2
    )

    first_season_subq = db.session.query(
        PlayerSeason.player_id,
        func.min(season_order).label('first_season_order')
    ).join(
        OrgSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).group_by(PlayerSeason.player_id).subquery()

    # Map back to actual org_season_id
    player_first_season = db.session.query(
        PlayerSeason.player_id,
        PlayerSeason.org_season_id.label('first_season_id')
    ).join(
        OrgSeason, PlayerSeason.org_season_id == OrgSeason.ID
    ).join(
        first_season_subq, PlayerSeason.player_id == first_season_subq.c.player_id
    ).filter(
        (OrgSeason.year * 10 + db.case(
            (OrgSeason.is_spring == 1, 1),
            else_=2
        )) == first_season_subq.c.first_season_order
    ).subquery()

    new_query = db.session.query(
        PlayerSeason.org_season_id,
        Player.program,
        func.count(PlayerSeason.id).label('new_count')
    ).join(
        Player, PlayerSeason.player_id == Player.id
    ).join(
        player_first_season, PlayerSeason.player_id == player_first_season.c.player_id
    ).filter(
        PlayerSeason.org_season_id.in_(season_ids),
        PlayerSeason.org_season_id == player_first_season.c.first_season_id,
        Player.program.in_(['baseball', 'softball'])
    ).group_by(
        PlayerSeason.org_season_id,
        Player.program
    ).all()

    new_lookup = {}
    for row in new_query:
        new_lookup[(row.org_season_id, row.program)] = row.new_count

    # Build season data with year-over-year comparisons
    seasons_data = {'baseball': [], 'softball': []}
    season_by_key = {}  # (year, is_spring) -> season

    for season in all_seasons:
        season_by_key[(season.year, season.is_spring)] = season

    for season in all_seasons:
        for sport in ['baseball', 'softball']:
            total = count_lookup.get((season.ID, sport), 0)
            new_count = new_lookup.get((season.ID, sport), 0)

            # Skip seasons with no players for this sport
            if total == 0:
                continue

            new_pct = round((new_count / total) * 100) if total > 0 else 0

            # Find prior year same season
            prior_key = (season.year - 1, season.is_spring)
            prior_season = season_by_key.get(prior_key)
            prior_total = 0
            trend = None

            if prior_season:
                prior_total = count_lookup.get((prior_season.ID, sport), 0)
                if prior_total > 0:
                    trend = round(((total - prior_total) / prior_total) * 100)

            seasons_data[sport].append({
                'season_desc': season.season_desc,
                'year': season.year,
                'is_spring': season.is_spring,
                'total': total,
                'new_count': new_count,
                'returning_count': total - new_count,
                'new_pct': new_pct,
                'prior_total': prior_total,
                'trend': trend
            })

    # Calculate summary stats
    summary_stats = {}
    for sport in ['baseball', 'softball']:
        data = seasons_data[sport]
        if data:
            totals = [d['total'] for d in data]
            new_pcts = [d['new_pct'] for d in data if d['total'] > 0]

            summary_stats[sport] = {
                'avg_players': round(sum(totals) / len(totals)) if totals else 0,
                'max_players': max(totals) if totals else 0,
                'min_players': min(totals) if totals else 0,
                'avg_new_pct': round(sum(new_pcts) / len(new_pcts)) if new_pcts else 0,
                'seasons_count': len(data)
            }

    return render_template('players/registration_trends.html',
                           seasons_data=seasons_data,
                           summary_stats=summary_stats)
