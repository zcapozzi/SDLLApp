"""Role Task Service - manages role-based task generation and tracking."""

from datetime import date, datetime, timedelta
from typing import List, Optional, Dict
from app.extensions import db
from app.models.role_task import RoleTaskTemplate, RoleTaskInstance
from app.models.org_season import OrgSeason
from app.models.user import User


class RoleTaskService:
    """Service for managing role-based tasks.

    Handles task generation, completion tracking, and reminders.
    """

    def __init__(self, org_id: int = 1):
        self.org_id = org_id

    def generate_season_tasks(self, year: int, is_spring: bool) -> List[RoleTaskInstance]:
        """Generate task instances for a season.

        Creates task instances for all active templates.
        Safe to call multiple times - skips existing instances.

        Args:
            year: Season year
            is_spring: True for spring season

        Returns:
            List of newly created RoleTaskInstance objects
        """
        # Get the OrgSeason for milestone dates
        org_season = OrgSeason.query.filter_by(
            org_id=self.org_id,
            year=year,
            is_spring=1 if is_spring else 0
        ).first()

        if not org_season:
            return []

        # Get all active templates
        templates = RoleTaskTemplate.get_all_for_org(self.org_id, active_only=True)

        created = []
        for template in templates:
            # Check if instance already exists
            existing = RoleTaskInstance.query.filter_by(
                template_id=template.id,
                year=year,
                is_spring=is_spring
            ).first()

            if existing:
                continue

            # Calculate due date
            due_date = template.calculate_due_date(org_season)

            # Create instance
            instance = RoleTaskInstance(
                template_id=template.id,
                year=year,
                is_spring=is_spring,
                due_date=due_date,
                status=RoleTaskInstance.STATUS_PENDING
            )
            db.session.add(instance)
            created.append(instance)

        db.session.commit()
        return created

    def recalculate_due_dates(self, year: int, is_spring: bool):
        """Recalculate due dates for all tasks in a season.

        Call this after milestone dates are updated.

        Args:
            year: Season year
            is_spring: True for spring season
        """
        org_season = OrgSeason.query.filter_by(
            org_id=self.org_id,
            year=year,
            is_spring=1 if is_spring else 0
        ).first()

        if not org_season:
            return

        instances = RoleTaskInstance.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.org_id == self.org_id,
            RoleTaskInstance.year == year,
            RoleTaskInstance.is_spring == is_spring
        ).all()

        for instance in instances:
            new_due_date = instance.template.calculate_due_date(org_season)
            if new_due_date != instance.due_date:
                instance.due_date = new_due_date

        db.session.commit()

    def get_tasks_for_role(self, role: str, year: int, is_spring: bool) -> List[RoleTaskInstance]:
        """Get all tasks for a role in a season.

        Args:
            role: Role name
            year: Season year
            is_spring: True for spring season

        Returns:
            List of RoleTaskInstance objects
        """
        return RoleTaskInstance.get_for_role(role, year, is_spring)

    def get_tasks_for_user(self, user: User, year: int, is_spring: bool) -> List[RoleTaskInstance]:
        """Get all tasks for a user based on their roles.

        Args:
            user: User instance
            year: Season year
            is_spring: True for spring season

        Returns:
            List of RoleTaskInstance objects
        """
        return RoleTaskInstance.get_for_user(user, year, is_spring)

    def mark_complete(self, task_instance_id: int, user_id: int, notes: str = None):
        """Mark a task as completed.

        Args:
            task_instance_id: Task instance ID
            user_id: ID of user completing the task
            notes: Optional completion notes
        """
        instance = RoleTaskInstance.query.get(task_instance_id)
        if instance:
            instance.mark_complete(user_id, notes)

    def mark_in_progress(self, task_instance_id: int):
        """Mark a task as in progress.

        Args:
            task_instance_id: Task instance ID
        """
        instance = RoleTaskInstance.query.get(task_instance_id)
        if instance:
            instance.mark_in_progress()

    def mark_skipped(self, task_instance_id: int, notes: str = None):
        """Mark a task as skipped.

        Args:
            task_instance_id: Task instance ID
            notes: Optional reason for skipping
        """
        instance = RoleTaskInstance.query.get(task_instance_id)
        if instance:
            instance.mark_skipped(notes)

    def get_overdue_tasks(self) -> List[RoleTaskInstance]:
        """Get all overdue tasks.

        Returns:
            List of overdue RoleTaskInstance objects
        """
        return RoleTaskInstance.get_overdue(self.org_id)

    def get_upcoming_tasks(self, days: int = 7) -> List[RoleTaskInstance]:
        """Get tasks due in the next N days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of RoleTaskInstance objects
        """
        return RoleTaskInstance.get_upcoming(days, self.org_id)

    def get_tasks_needing_reminder(self) -> List[RoleTaskInstance]:
        """Get tasks that need reminder emails sent.

        Returns tasks where:
        - Due date is within reminder window
        - Haven't sent a reminder recently (or at all)

        Returns:
            List of RoleTaskInstance objects needing reminders
        """
        from sqlalchemy.orm import joinedload

        today = date.today()

        # Get all pending/in-progress tasks with due dates
        instances = RoleTaskInstance.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.org_id == self.org_id,
            RoleTaskInstance.due_date.isnot(None),
            RoleTaskInstance.status.in_([
                RoleTaskInstance.STATUS_PENDING,
                RoleTaskInstance.STATUS_IN_PROGRESS
            ])
        ).options(
            joinedload(RoleTaskInstance.template)
        ).all()

        result = []
        for instance in instances:
            if not instance.template.reminder_days_before:
                continue

            reminder_days = instance.template.reminder_days_list
            if not reminder_days:
                continue

            days_until = instance.days_until_due
            if days_until is None:
                continue

            # Check if we should send a reminder
            should_remind = False
            for reminder_day in reminder_days:
                if days_until == reminder_day:
                    should_remind = True
                    break
                # Also remind if overdue and we haven't reminded recently
                if days_until < 0 and reminder_day == min(reminder_days):
                    # Overdue - check if we sent a reminder in the last 3 days
                    if instance.last_reminder_sent:
                        days_since_reminder = (datetime.utcnow() - instance.last_reminder_sent).days
                        if days_since_reminder >= 3:
                            should_remind = True
                    else:
                        should_remind = True

            if should_remind:
                result.append(instance)

        return result

    def send_task_reminders(self) -> int:
        """Send reminder emails for upcoming/overdue tasks.

        Returns:
            Number of reminders sent
        """
        from app.services.notification_service import GmailService
        from app.services.email_routing_service import EmailRoutingService

        tasks = self.get_tasks_needing_reminder()
        if not tasks:
            return 0

        email_service = GmailService()
        routing_service = EmailRoutingService(self.org_id)
        sent_count = 0

        # Group tasks by role
        tasks_by_role = {}
        for task in tasks:
            role = task.template.role
            if role not in tasks_by_role:
                tasks_by_role[role] = []
            tasks_by_role[role].append(task)

        for role, role_tasks in tasks_by_role.items():
            # Find role holder
            role_holder = routing_service.get_role_holder(role)
            if not role_holder or not role_holder.email:
                continue

            # Build email content
            subject = f"Task Reminder: {len(role_tasks)} task(s) need attention"

            task_list_html = ""
            for task in role_tasks:
                status = "OVERDUE" if task.is_overdue else f"Due in {task.days_until_due} day(s)"
                task_list_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{task.title}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{task.due_date.strftime('%b %d, %Y') if task.due_date else 'No date'}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">
                        <span style="color: {'#dc3545' if task.is_overdue else '#28a745'}; font-weight: bold;">{status}</span>
                    </td>
                </tr>
                """

            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #2e5a2e;">Task Reminder</h2>
                <p>Hello {role_holder.name},</p>
                <p>The following tasks for your role as <strong>{role.replace('_', ' ').title()}</strong> need your attention:</p>

                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Task</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Due Date</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {task_list_html}
                    </tbody>
                </table>

                <p>Log in to view and complete your tasks.</p>

                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    This is an automated reminder from the SDLL Management System.
                </p>
            </body>
            </html>
            """

            try:
                email_service.send_email(
                    to=role_holder.email,
                    subject=subject,
                    body_html=body_html
                )

                # Update reminder tracking
                for task in role_tasks:
                    task.last_reminder_sent = datetime.utcnow()
                    task.reminder_count += 1
                db.session.commit()

                sent_count += 1
            except Exception as e:
                print(f"Failed to send reminder to {role_holder.email}: {e}")

        return sent_count

    def get_dashboard_summary(self, year: int, is_spring: bool) -> Dict:
        """Get summary statistics for the tasks dashboard.

        Args:
            year: Season year
            is_spring: True for spring season

        Returns:
            Dict with summary statistics
        """
        from sqlalchemy.orm import joinedload

        instances = RoleTaskInstance.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.org_id == self.org_id,
            RoleTaskInstance.year == year,
            RoleTaskInstance.is_spring == is_spring
        ).options(
            joinedload(RoleTaskInstance.template)
        ).all()

        today = date.today()

        summary = {
            'total': len(instances),
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'skipped': 0,
            'overdue': 0,
            'due_this_week': 0,
            'by_role': {}
        }

        for instance in instances:
            # Count by status
            if instance.status == RoleTaskInstance.STATUS_PENDING:
                summary['pending'] += 1
            elif instance.status == RoleTaskInstance.STATUS_IN_PROGRESS:
                summary['in_progress'] += 1
            elif instance.status == RoleTaskInstance.STATUS_COMPLETED:
                summary['completed'] += 1
            elif instance.status == RoleTaskInstance.STATUS_SKIPPED:
                summary['skipped'] += 1

            # Count overdue
            if instance.is_overdue:
                summary['overdue'] += 1

            # Count due this week
            if instance.due_date:
                days_until = (instance.due_date - today).days
                if 0 <= days_until <= 7 and instance.status in [
                    RoleTaskInstance.STATUS_PENDING,
                    RoleTaskInstance.STATUS_IN_PROGRESS
                ]:
                    summary['due_this_week'] += 1

            # Count by role
            role = instance.template.role
            if role not in summary['by_role']:
                summary['by_role'][role] = {'total': 0, 'completed': 0}
            summary['by_role'][role]['total'] += 1
            if instance.status == RoleTaskInstance.STATUS_COMPLETED:
                summary['by_role'][role]['completed'] += 1

        return summary
