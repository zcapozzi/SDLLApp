"""Knowledge base and onboarding routes."""

from datetime import date
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.knowledge import knowledge_bp, board_member_required, logger
from app.extensions import db
from app.models.artifact import Artifact
from app.models.role_task import RoleTaskTemplate, RoleTaskInstance
from app.models.email_routing_config import EmailRoutingConfig
from app.models.org_season import OrgSeason
from app.models.user import User
from app.services.role_task_service import RoleTaskService
from app.services.email_routing_service import EmailRoutingService
from app.utils.auth import role_required


# =============================================================================
# KNOWLEDGE BASE - PUBLIC BROWSE
# =============================================================================

@knowledge_bp.route('/kb')
@login_required
@board_member_required
def browse():
    """Browse knowledge base."""
    category = request.args.get('category')
    artifact_type = request.args.get('type')
    search_query = request.args.get('q')

    if search_query:
        artifacts = Artifact.search(search_query, current_user)
    else:
        artifacts = Artifact.get_for_user(
            current_user,
            category=category,
            artifact_type=artifact_type
        )

    # Group by category
    grouped = {}
    for artifact in artifacts:
        cat = artifact.category or 'general'
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(artifact)

    return render_template(
        'knowledge/browse.html',
        artifacts=artifacts,
        grouped=grouped,
        categories=Artifact.CATEGORIES,
        types=Artifact.TYPES,
        current_category=category,
        current_type=artifact_type,
        search_query=search_query
    )


@knowledge_bp.route('/kb/<int:artifact_id>')
@login_required
@board_member_required
def view_artifact(artifact_id):
    """View a single artifact."""
    artifact = Artifact.query.get_or_404(artifact_id)

    if not artifact.can_view(current_user):
        flash('You do not have permission to view this artifact.', 'error')
        return redirect(url_for('knowledge.browse'))

    return render_template(
        'knowledge/view.html',
        artifact=artifact
    )


# =============================================================================
# MY TASKS
# =============================================================================

@knowledge_bp.route('/my-tasks')
@login_required
@board_member_required
def my_tasks():
    """View current user's tasks."""
    # Get current season
    org_season = OrgSeason.get_current_season()
    if not org_season:
        flash('No current season configured.', 'warning')
        return redirect(url_for('main.dashboard'))

    year = org_season.year
    is_spring = bool(org_season.is_spring)

    # Get tasks for user's roles
    tasks = RoleTaskInstance.get_for_user(current_user, year, is_spring)

    # Separate by status
    pending_tasks = [t for t in tasks if t.status in [
        RoleTaskInstance.STATUS_PENDING,
        RoleTaskInstance.STATUS_IN_PROGRESS
    ]]
    completed_tasks = [t for t in tasks if t.status in [
        RoleTaskInstance.STATUS_COMPLETED,
        RoleTaskInstance.STATUS_SKIPPED
    ]]

    # Sort pending by due date
    pending_tasks.sort(key=lambda t: (t.due_date or date.max))

    return render_template(
        'knowledge/my_tasks.html',
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
        org_season=org_season,
        today=date.today()
    )


@knowledge_bp.route('/my-tasks/<int:task_id>/complete', methods=['POST'])
@login_required
@board_member_required
def complete_task(task_id):
    """Mark a task as completed."""
    task = RoleTaskInstance.query.get_or_404(task_id)

    # Verify user has the role for this task
    if not current_user.has_role(task.template.role):
        flash('You do not have permission to complete this task.', 'error')
        return redirect(url_for('knowledge.my_tasks'))

    notes = request.form.get('notes', '').strip()
    task.mark_complete(current_user.ID, notes if notes else None)

    flash(f'Task "{task.title}" marked as completed.', 'success')
    return redirect(url_for('knowledge.my_tasks'))


@knowledge_bp.route('/my-tasks/<int:task_id>/skip', methods=['POST'])
@login_required
@board_member_required
def skip_task(task_id):
    """Mark a task as skipped."""
    task = RoleTaskInstance.query.get_or_404(task_id)

    if not current_user.has_role(task.template.role):
        flash('You do not have permission to skip this task.', 'error')
        return redirect(url_for('knowledge.my_tasks'))

    notes = request.form.get('notes', '').strip()
    task.mark_skipped(notes if notes else None)

    flash(f'Task "{task.title}" marked as skipped.', 'success')
    return redirect(url_for('knowledge.my_tasks'))


@knowledge_bp.route('/my-tasks/<int:task_id>/in-progress', methods=['POST'])
@login_required
@board_member_required
def start_task(task_id):
    """Mark a task as in progress."""
    task = RoleTaskInstance.query.get_or_404(task_id)

    if not current_user.has_role(task.template.role):
        flash('You do not have permission to update this task.', 'error')
        return redirect(url_for('knowledge.my_tasks'))

    task.mark_in_progress()

    flash(f'Task "{task.title}" marked as in progress.', 'success')
    return redirect(url_for('knowledge.my_tasks'))


# =============================================================================
# ONBOARDING
# =============================================================================

@knowledge_bp.route('/onboarding')
@login_required
@board_member_required
def onboarding():
    """Onboarding dashboard - role-aware."""
    # Get current season
    org_season = OrgSeason.get_current_season()
    if not org_season:
        flash('No current season configured.', 'warning')
        return redirect(url_for('main.dashboard'))

    year = org_season.year
    is_spring = bool(org_season.is_spring)

    # Get user's roles
    user_roles = current_user.roles_list

    # Get tasks for user's roles
    service = RoleTaskService()
    tasks = service.get_tasks_for_user(current_user, year, is_spring)

    # Filter to pending/in-progress tasks
    pending_tasks = [t for t in tasks if t.status in [
        RoleTaskInstance.STATUS_PENDING,
        RoleTaskInstance.STATUS_IN_PROGRESS
    ]]
    pending_tasks.sort(key=lambda t: (t.due_date or date.max))

    # Get artifacts for user's roles
    artifacts_by_role = {}
    for role in user_roles:
        role_artifacts = Artifact.get_for_role(role)
        if role_artifacts:
            artifacts_by_role[role] = role_artifacts

    # Get key contacts (other board members)
    routing_service = EmailRoutingService()
    role_holders = routing_service.get_all_role_holders()

    # Define role descriptions
    role_descriptions = {
        'admin': 'System administrator with full access to all features.',
        'scheduler': 'Manages game schedules, field allocations, and rainouts.',
        'umpire_coordinator': 'Coordinates umpire assignments, training, and partner organizations.',
        'coaching_coordinator': 'Manages coach onboarding, training, and resources.',
        'treasurer': 'Handles financial matters, payments, and budgets.',
        'facilities': 'Manages fields, equipment, and facility issues.',
        'BB_VP': 'Vice President overseeing baseball operations.',
        'SB_VP': 'Vice President overseeing softball operations.',
        'BoardExec': 'Board executive member.',
        'BBPlayerAgent': 'Baseball player agent handling registrations and rosters.',
        'SBPlayerAgent': 'Softball player agent handling registrations and rosters.',
    }

    return render_template(
        'knowledge/onboarding.html',
        user_roles=user_roles,
        pending_tasks=pending_tasks,
        artifacts_by_role=artifacts_by_role,
        role_holders=role_holders,
        role_descriptions=role_descriptions,
        org_season=org_season
    )


# =============================================================================
# ADMIN - ARTIFACTS
# =============================================================================

@knowledge_bp.route('/admin/artifacts')
@login_required
@role_required('admin')
def admin_artifacts():
    """List all artifacts."""
    artifacts = Artifact.query.filter_by(org_id=1).order_by(
        Artifact.category, Artifact.sort_order, Artifact.title
    ).all()

    return render_template(
        'admin/artifacts.html',
        artifacts=artifacts,
        categories=Artifact.CATEGORIES,
        types=Artifact.TYPES
    )


@knowledge_bp.route('/admin/artifacts/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_artifact_new():
    """Create new artifact."""
    if request.method == 'POST':
        artifact = Artifact(
            org_id=1,
            artifact_type=request.form.get('artifact_type'),
            category=request.form.get('category'),
            title=request.form.get('title'),
            description=request.form.get('description'),
            content=request.form.get('content'),
            external_url=request.form.get('external_url'),
            visibility=request.form.get('visibility', 'role'),
            allowed_roles=request.form.get('allowed_roles'),
            tags=request.form.get('tags'),
            sort_order=int(request.form.get('sort_order', 0)),
            created_by_user_id=current_user.ID
        )
        db.session.add(artifact)
        db.session.commit()

        flash(f'Artifact "{artifact.title}" created.', 'success')
        return redirect(url_for('knowledge.admin_artifacts'))

    return render_template(
        'admin/artifact_form.html',
        artifact=None,
        categories=Artifact.CATEGORIES,
        types=Artifact.TYPES,
        visibilities=Artifact.VISIBILITIES,
        roles=User.ROLES
    )


@knowledge_bp.route('/admin/artifacts/<int:artifact_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_artifact_edit(artifact_id):
    """Edit artifact."""
    artifact = Artifact.query.get_or_404(artifact_id)

    if request.method == 'POST':
        artifact.artifact_type = request.form.get('artifact_type')
        artifact.category = request.form.get('category')
        artifact.title = request.form.get('title')
        artifact.description = request.form.get('description')
        artifact.content = request.form.get('content')
        artifact.external_url = request.form.get('external_url')
        artifact.visibility = request.form.get('visibility', 'role')
        artifact.allowed_roles = request.form.get('allowed_roles')
        artifact.tags = request.form.get('tags')
        artifact.sort_order = int(request.form.get('sort_order', 0))
        artifact.updated_by_user_id = current_user.ID

        db.session.commit()

        flash(f'Artifact "{artifact.title}" updated.', 'success')
        return redirect(url_for('knowledge.admin_artifacts'))

    return render_template(
        'admin/artifact_form.html',
        artifact=artifact,
        categories=Artifact.CATEGORIES,
        types=Artifact.TYPES,
        visibilities=Artifact.VISIBILITIES,
        roles=User.ROLES
    )


@knowledge_bp.route('/admin/artifacts/<int:artifact_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_artifact_delete(artifact_id):
    """Delete artifact."""
    artifact = Artifact.query.get_or_404(artifact_id)
    title = artifact.title

    db.session.delete(artifact)
    db.session.commit()

    flash(f'Artifact "{title}" deleted.', 'success')
    return redirect(url_for('knowledge.admin_artifacts'))


# =============================================================================
# ADMIN - ROLE TASKS
# =============================================================================

@knowledge_bp.route('/admin/role-tasks')
@login_required
@role_required('admin')
def admin_role_tasks():
    """List role task templates."""
    templates = RoleTaskTemplate.get_all_for_org(org_id=1)

    # Group by role
    by_role = {}
    for template in templates:
        if template.role not in by_role:
            by_role[template.role] = []
        by_role[template.role].append(template)

    return render_template(
        'admin/role_tasks.html',
        templates=templates,
        by_role=by_role,
        milestones=RoleTaskTemplate.MILESTONES,
        roles=User.ROLES
    )


@knowledge_bp.route('/admin/role-tasks/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_role_task_new():
    """Create new role task template."""
    if request.method == 'POST':
        template = RoleTaskTemplate(
            org_id=1,
            role=request.form.get('role'),
            title=request.form.get('title'),
            description=request.form.get('description'),
            trigger_milestone=request.form.get('trigger_milestone'),
            days_offset=int(request.form.get('days_offset', 0)),
            artifact_id=int(request.form.get('artifact_id')) if request.form.get('artifact_id') else None,
            reminder_days_before=request.form.get('reminder_days_before'),
            sort_order=int(request.form.get('sort_order', 0)),
            active=request.form.get('active') == '1'
        )
        db.session.add(template)
        db.session.commit()

        flash(f'Task template "{template.title}" created.', 'success')
        return redirect(url_for('knowledge.admin_role_tasks'))

    artifacts = Artifact.query.filter_by(org_id=1).order_by(Artifact.title).all()

    return render_template(
        'admin/role_task_form.html',
        template=None,
        milestones=RoleTaskTemplate.MILESTONES,
        roles=User.ROLES,
        artifacts=artifacts
    )


@knowledge_bp.route('/admin/role-tasks/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_role_task_edit(template_id):
    """Edit role task template."""
    template = RoleTaskTemplate.query.get_or_404(template_id)

    if request.method == 'POST':
        template.role = request.form.get('role')
        template.title = request.form.get('title')
        template.description = request.form.get('description')
        template.trigger_milestone = request.form.get('trigger_milestone')
        template.days_offset = int(request.form.get('days_offset', 0))
        template.artifact_id = int(request.form.get('artifact_id')) if request.form.get('artifact_id') else None
        template.reminder_days_before = request.form.get('reminder_days_before')
        template.sort_order = int(request.form.get('sort_order', 0))
        template.active = request.form.get('active') == '1'

        db.session.commit()

        flash(f'Task template "{template.title}" updated.', 'success')
        return redirect(url_for('knowledge.admin_role_tasks'))

    artifacts = Artifact.query.filter_by(org_id=1).order_by(Artifact.title).all()

    return render_template(
        'admin/role_task_form.html',
        template=template,
        milestones=RoleTaskTemplate.MILESTONES,
        roles=User.ROLES,
        artifacts=artifacts
    )


@knowledge_bp.route('/admin/role-tasks/<int:template_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_role_task_delete(template_id):
    """Delete role task template."""
    template = RoleTaskTemplate.query.get_or_404(template_id)
    title = template.title

    # Delete all instances first
    RoleTaskInstance.query.filter_by(template_id=template_id).delete()

    db.session.delete(template)
    db.session.commit()

    flash(f'Task template "{title}" deleted.', 'success')
    return redirect(url_for('knowledge.admin_role_tasks'))


@knowledge_bp.route('/admin/role-tasks/generate/<int:year>/<int:is_spring>', methods=['POST'])
@login_required
@role_required('admin')
def admin_generate_tasks(year, is_spring):
    """Generate task instances for a season."""
    service = RoleTaskService()
    created = service.generate_season_tasks(year, bool(is_spring))

    if created:
        flash(f'Generated {len(created)} task instance(s) for {"Spring" if is_spring else "Fall"} {year}.', 'success')
    else:
        flash('No new tasks to generate (all already exist).', 'info')

    return redirect(url_for('knowledge.admin_role_tasks'))


@knowledge_bp.route('/admin/role-tasks/instances/<int:year>/<int:is_spring>')
@login_required
@role_required('admin')
def admin_task_instances(year, is_spring):
    """View task instances for a season."""
    instances = RoleTaskInstance.query.join(RoleTaskTemplate).filter(
        RoleTaskTemplate.org_id == 1,
        RoleTaskInstance.year == year,
        RoleTaskInstance.is_spring == bool(is_spring)
    ).options(
        joinedload(RoleTaskInstance.template),
        joinedload(RoleTaskInstance.completed_by)
    ).order_by(
        RoleTaskTemplate.role,
        RoleTaskInstance.due_date
    ).all()

    # Group by role
    by_role = {}
    for instance in instances:
        role = instance.template.role
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(instance)

    # Get summary
    service = RoleTaskService()
    summary = service.get_dashboard_summary(year, bool(is_spring))

    return render_template(
        'admin/task_instances.html',
        instances=instances,
        by_role=by_role,
        summary=summary,
        year=year,
        is_spring=is_spring,
        statuses=RoleTaskInstance.STATUSES,
        today=date.today()
    )


# =============================================================================
# ADMIN - EMAIL ROUTING
# =============================================================================

@knowledge_bp.route('/admin/email-routing')
@login_required
@role_required('admin')
def admin_email_routing():
    """Manage email routing configuration."""
    # Ensure defaults exist
    EmailRoutingConfig.ensure_defaults()

    configs = EmailRoutingConfig.get_all_for_org(org_id=1)

    # Get role holders for reference
    routing_service = EmailRoutingService()
    role_holders = routing_service.get_all_role_holders()

    return render_template(
        'admin/email_routing.html',
        configs=configs,
        email_types=EmailRoutingConfig.EMAIL_TYPES,
        role_holders=role_holders,
        roles=User.ROLES
    )


@knowledge_bp.route('/admin/email-routing/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_email_routing_edit(config_id):
    """Edit email routing configuration."""
    config = EmailRoutingConfig.query.get_or_404(config_id)

    if request.method == 'POST':
        config.from_name = request.form.get('from_name') or None
        config.reply_to_email = request.form.get('reply_to_email') or None
        config.reply_to_role = request.form.get('reply_to_role') or None
        config.cc_emails = request.form.get('cc_emails') or None
        config.cc_roles = request.form.get('cc_roles') or None
        config.bcc_emails = request.form.get('bcc_emails') or None
        config.active = request.form.get('active') == '1'

        db.session.commit()

        flash(f'Email routing for "{config.email_type_display}" updated.', 'success')
        return redirect(url_for('knowledge.admin_email_routing'))

    # Get role holders for reference
    routing_service = EmailRoutingService()
    role_holders = routing_service.get_all_role_holders()

    return render_template(
        'admin/email_routing_form.html',
        config=config,
        role_holders=role_holders,
        roles=User.ROLES
    )
