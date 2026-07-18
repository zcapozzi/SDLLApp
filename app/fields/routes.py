"""Field allocation routes"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import time
from app.models.field import Field
from app.models.field_slot import FieldSlot
from app.models.league import League
from app.models.team import TeamSeason
from app.extensions import db
from app.utils.logging import SDLLLogger

fields_bp = Blueprint('fields', __name__)
logger = SDLLLogger('fields')


@fields_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """List all fields"""
    if request.method == 'POST' and current_user.can_edit_schedule():
        action = request.form.get('action')

        if action == 'add_field':
            field_name = request.form.get('field_name', '').strip()
            if field_name:
                # Check for duplicate
                existing = Field.query.filter_by(location_title=field_name, active=1).first()
                if existing:
                    flash(f'Field "{field_name}" already exists', 'error')
                else:
                    field = Field(
                        active=1,
                        location_title=field_name,
                        is_owned=1,
                        restriction_type='anyone'
                    )
                    db.session.add(field)
                    db.session.commit()
                    logger.info(f'Added field: {field_name}')
                    flash(f'Added field: {field_name}', 'success')
            else:
                flash('Field name is required', 'error')

        elif action == 'delete_field':
            field_id = int(request.form.get('field_id'))
            field = Field.query.get(field_id)
            if field:
                field.active = 0
                db.session.commit()
                logger.info(f'Deleted field: {field.location_title}')
                flash(f'Deleted field: {field.location_title}', 'success')

        elif action == 'toggle_ownership':
            field_id = int(request.form.get('field_id'))
            field = Field.query.get(field_id)
            if field:
                field.is_owned = 0 if field.is_owned else 1
                db.session.commit()
                status = 'SDLL' if field.is_owned else 'Away'
                logger.info(f'Set {field.location_title} ownership to {status}')

        return redirect(url_for('fields.index'))

    fields = Field.get_all_active()
    return render_template('fields/index.html', fields=fields)


@fields_bp.route('/allocations')
@login_required
def allocations():
    """Overview of field allocations by season"""
    # Get all seasons that have field slots
    seasons = db.session.query(
        FieldSlot.year,
        FieldSlot.is_spring,
        db.func.count(FieldSlot.slot_ID).label('slot_count')
    ).filter(
        FieldSlot.active == 1
    ).group_by(
        FieldSlot.year,
        FieldSlot.is_spring
    ).order_by(
        FieldSlot.year.desc(),
        FieldSlot.is_spring.desc()
    ).all()

    season_list = []
    for year, is_spring, slot_count in seasons:
        # Count unique fields
        field_count = db.session.query(
            db.func.count(db.distinct(FieldSlot.field_ID))
        ).filter(
            FieldSlot.year == year,
            FieldSlot.is_spring == is_spring,
            FieldSlot.active == 1
        ).scalar()

        season_list.append({
            'year': year,
            'is_spring': is_spring,
            'name': f'{"Spring" if is_spring else "Fall"} {year}',
            'slot_count': slot_count,
            'field_count': field_count
        })

    # Also get seasons with teams but no slots (for creating new allocations)
    team_seasons = db.session.query(
        TeamSeason.year,
        TeamSeason.is_spring
    ).filter(
        TeamSeason.active == 1
    ).group_by(
        TeamSeason.year,
        TeamSeason.is_spring
    ).all()

    available_seasons = []
    existing_combos = {(s['year'], s['is_spring']) for s in season_list}
    for year, is_spring in team_seasons:
        if (year, is_spring) not in existing_combos:
            available_seasons.append({
                'year': year,
                'is_spring': is_spring,
                'name': f'{"Spring" if is_spring else "Fall"} {year}'
            })

    return render_template(
        'fields/allocations.html',
        seasons=season_list,
        available_seasons=available_seasons
    )


@fields_bp.route('/allocations/<int:year>/<int:is_spring>')
@login_required
def view_allocations(year, is_spring):
    """View field allocations for a specific season"""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'
    slots = FieldSlot.get_by_season(year, is_spring)

    # Group by field
    slots_by_field = {}
    for slot in slots:
        field_name = slot.field.location_title if slot.field else f"Field {slot.field_ID}"
        if field_name not in slots_by_field:
            slots_by_field[field_name] = []
        slots_by_field[field_name].append(slot)

    # Get available fields for adding new slots
    fields = Field.get_all_active()
    leagues = League.get_all_active()

    return render_template(
        'fields/view_allocations.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        slots_by_field=slots_by_field,
        slot_count=len(slots),
        fields=fields,
        leagues=leagues,
        days=FieldSlot.DAY_NAMES
    )


@fields_bp.route('/allocations/<int:year>/<int:is_spring>/manage', methods=['GET', 'POST'])
@login_required
def manage_allocations(year, is_spring):
    """Manage field allocations for a season"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage field allocations.', 'error')
        return redirect(url_for('fields.view_allocations', year=year, is_spring=is_spring))

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_slot':
            field_id = int(request.form.get('field_id'))
            day_of_week = int(request.form.get('day_of_week'))
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            league = request.form.get('league') or None
            is_owned = 1 if request.form.get('is_owned') else 0
            notes = request.form.get('notes') or None

            # Parse times
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)

            slot = FieldSlot(
                active=1,
                field_ID=field_id,
                year=year,
                is_spring=is_spring,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                league=league,
                is_owned=is_owned,
                notes=notes
            )
            db.session.add(slot)
            db.session.commit()

            field = Field.query.get(field_id)
            logger.info(f'Added slot: {field.location_title} {FieldSlot.DAY_NAMES[day_of_week]} {start_time_str}')
            flash(f'Added slot: {field.location_title} {FieldSlot.DAY_NAMES[day_of_week]} {start_time_str}', 'success')

        elif action == 'delete_slot':
            slot_id = int(request.form.get('slot_id'))
            slot = FieldSlot.query.get(slot_id)
            if slot and slot.year == year and slot.is_spring == is_spring:
                slot.active = 0
                db.session.commit()
                logger.info(f'Deleted slot {slot_id}')
                flash('Slot removed', 'success')

        elif action == 'update_slot':
            slot_id = int(request.form.get('slot_id'))
            slot = FieldSlot.query.get(slot_id)
            if slot and slot.year == year and slot.is_spring == is_spring:
                slot.day_of_week = int(request.form.get('day_of_week'))
                slot.start_time = time.fromisoformat(request.form.get('start_time'))
                slot.end_time = time.fromisoformat(request.form.get('end_time'))
                slot.league = request.form.get('league') or None
                slot.is_owned = 1 if request.form.get('is_owned') else 0
                slot.notes = request.form.get('notes') or None
                db.session.commit()
                logger.info(f'Updated slot {slot_id}')
                flash('Slot updated', 'success')

        elif action == 'set_field_ownership':
            field_id = int(request.form.get('field_id'))
            is_owned = int(request.form.get('is_owned'))
            slots = FieldSlot.query.filter_by(
                field_ID=field_id,
                year=year,
                is_spring=is_spring,
                active=1
            ).all()
            count = 0
            for slot in slots:
                slot.is_owned = is_owned
                count += 1
            db.session.commit()
            field = Field.query.get(field_id)
            status = 'SDLL owned' if is_owned else 'Away'
            logger.info(f'Set {count} slots at {field.location_title} to {status}')
            flash(f'Set {count} slots at {field.location_title} to {status}', 'success')

        # Preserve filter/group settings on redirect
        return redirect(url_for(
            'fields.manage_allocations',
            year=year,
            is_spring=is_spring,
            group_by=request.args.get('group_by', 'field'),
            ownership=request.args.get('ownership', 'all')
        ))

    # GET - show management page
    group_by = request.args.get('group_by', 'field')  # 'field' or 'day'
    ownership = request.args.get('ownership', 'all')  # 'all', 'owned', 'away'
    slots = FieldSlot.get_by_season(year, is_spring)

    # Filter by ownership
    if ownership == 'owned':
        slots = [s for s in slots if s.is_owned]
    elif ownership == 'away':
        slots = [s for s in slots if not s.is_owned]

    # Group by field
    slots_by_field = {}
    for slot in slots:
        field_name = slot.field.location_title if slot.field else f"Field {slot.field_ID}"
        if field_name not in slots_by_field:
            slots_by_field[field_name] = {'field_id': slot.field_ID, 'slots': []}
        slots_by_field[field_name]['slots'].append(slot)

    # Group by day
    slots_by_day = {}
    for slot in slots:
        day_name = slot.day_name
        if day_name not in slots_by_day:
            slots_by_day[day_name] = {'day_of_week': slot.day_of_week, 'slots': []}
        slots_by_day[day_name]['slots'].append(slot)
    # Sort by day of week
    slots_by_day = dict(sorted(slots_by_day.items(), key=lambda x: x[1]['day_of_week']))

    fields = Field.get_all_active()
    leagues = League.get_all_active()

    return render_template(
        'fields/manage_allocations.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        slots_by_field=slots_by_field,
        slots_by_day=slots_by_day,
        group_by=group_by,
        ownership=ownership,
        slot_count=len(slots),
        fields=fields,
        leagues=leagues,
        days=FieldSlot.DAY_NAMES
    )


@fields_bp.route('/allocations/copy', methods=['GET', 'POST'])
@login_required
def copy_allocations():
    """Copy field allocations from one season to another"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to copy field allocations.', 'error')
        return redirect(url_for('fields.allocations'))

    if request.method == 'POST':
        source_year = int(request.form.get('source_year'))
        source_is_spring = int(request.form.get('source_is_spring'))
        target_year = int(request.form.get('target_year'))
        target_is_spring = int(request.form.get('target_is_spring'))

        source_name = f'{"Spring" if source_is_spring else "Fall"} {source_year}'
        target_name = f'{"Spring" if target_is_spring else "Fall"} {target_year}'

        # Check if target already has slots
        existing = FieldSlot.query.filter_by(
            year=target_year,
            is_spring=target_is_spring,
            active=1
        ).first()

        if existing:
            flash(f'{target_name} already has field allocations. Delete them first.', 'error')
            return redirect(url_for('fields.copy_allocations'))

        try:
            new_slots = FieldSlot.copy_to_new_season(
                source_year, source_is_spring,
                target_year, target_is_spring
            )
            logger.info(f'Copied {len(new_slots)} slots from {source_name} to {target_name}')
            flash(f'Copied {len(new_slots)} field slots to {target_name}', 'success')
            return redirect(url_for('fields.manage_allocations', year=target_year, is_spring=target_is_spring))

        except Exception as e:
            db.session.rollback()
            logger.info(f'Field slot copy failed: {str(e)}')
            flash(f'Error copying allocations: {str(e)}', 'error')

    # GET - show copy form
    # Get seasons with slots
    seasons_with_slots = db.session.query(
        FieldSlot.year,
        FieldSlot.is_spring,
        db.func.count(FieldSlot.slot_ID).label('slot_count')
    ).filter(
        FieldSlot.active == 1
    ).group_by(
        FieldSlot.year,
        FieldSlot.is_spring
    ).order_by(
        FieldSlot.year.desc(),
        FieldSlot.is_spring.desc()
    ).all()

    source_options = [{
        'year': year,
        'is_spring': is_spring,
        'name': f'{"Spring" if is_spring else "Fall"} {year}',
        'slot_count': slot_count
    } for year, is_spring, slot_count in seasons_with_slots]

    return render_template('fields/copy_allocations.html', source_options=source_options)


@fields_bp.route('/api/allocations/<int:year>/<int:is_spring>')
@login_required
def api_allocations(year, is_spring):
    """API endpoint to get field allocations for a season"""
    slots = FieldSlot.get_by_season(year, is_spring)
    return jsonify([{
        'slot_ID': s.slot_ID,
        'field_ID': s.field_ID,
        'field_name': s.field.location_title if s.field else None,
        'day_of_week': s.day_of_week,
        'day_name': s.day_name,
        'start_time': s.start_time.strftime('%H:%M'),
        'end_time': s.end_time.strftime('%H:%M'),
        'time_display': s.time_display,
        'league': s.league,
        'is_owned': s.is_owned
    } for s in slots])


@fields_bp.route('/properties', methods=['GET', 'POST'])
@login_required
def properties():
    """Manage field properties - usage type and practice capacity"""
    if not current_user.can_edit_schedule():
        flash('You do not have permission to manage field properties.', 'error')
        return redirect(url_for('fields.index'))

    ownership_filter = request.args.get('ownership', 'sdll')  # 'sdll', 'away', 'all'

    if request.method == 'POST':
        field_id = int(request.form.get('field_id'))
        usage_type = request.form.get('usage_type')
        practice_capacity = request.form.get('practice_capacity', type=int) or 1
        practice_capacity_late = request.form.get('practice_capacity_late', type=int) or None

        field = Field.query.get(field_id)
        if field:
            field.usage_type = usage_type
            field.practice_capacity = practice_capacity
            field.practice_capacity_late = practice_capacity_late if practice_capacity_late != practice_capacity else None
            db.session.commit()
            logger.info(f'Updated properties for {field.location_title}: {field.usage_type_display}')
            flash(f'Updated properties for {field.location_title}', 'success')

        return redirect(url_for('fields.properties', ownership=ownership_filter) + f'#field-{field_id}')

    # GET - filter fields by ownership
    query = Field.query.filter_by(active=1)
    if ownership_filter == 'sdll':
        query = query.filter_by(is_owned=1)
    elif ownership_filter == 'away':
        query = query.filter_by(is_owned=0)
    # 'all' shows everything

    fields = query.order_by(Field.location_title).all()

    return render_template(
        'fields/properties.html',
        fields=fields,
        usage_types=Field.USAGE_TYPES,
        ownership_filter=ownership_filter
    )
