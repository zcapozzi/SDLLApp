"""Role Task models - templates and instances for role-based tasks."""

from datetime import datetime, date, timedelta
from app.extensions import db


class RoleTaskTemplate(db.Model):
    """Template for recurring role-based tasks.

    Defines tasks that should be completed each season by
    a specific role holder. Tasks are triggered relative
    to season milestones.
    """
    __tablename__ = 'sdll_role_task_templates'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # What role this applies to
    role = db.Column(db.String(50), nullable=False)

    # Task details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    # Timing - relative to milestone
    trigger_milestone = db.Column(db.String(50), nullable=False)
    days_offset = db.Column(db.Integer, default=0)  # Negative = before, positive = after

    # Linked artifact (optional)
    artifact_id = db.Column(db.Integer, db.ForeignKey('sdll_artifacts.id'))

    # Reminder settings (comma-separated days before due)
    reminder_days_before = db.Column(db.String(50))

    # Metadata
    sort_order = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    artifact = db.relationship('Artifact')
    instances = db.relationship('RoleTaskInstance', back_populates='template')

    # Milestone constants
    MILESTONE_REGISTRATION_OPENS = 'registration_opens'
    MILESTONE_EVALUATIONS = 'evaluations'
    MILESTONE_DRAFT = 'draft'
    MILESTONE_FIRST_PRACTICE = 'first_practice'
    MILESTONE_TRAINING = 'training'
    MILESTONE_OPENING_DAY = 'opening_day'
    MILESTONE_SEASON_END = 'season_end'

    MILESTONES = [
        (MILESTONE_REGISTRATION_OPENS, 'Registration Opens'),
        (MILESTONE_EVALUATIONS, 'Evaluations'),
        (MILESTONE_DRAFT, 'Draft'),
        (MILESTONE_FIRST_PRACTICE, 'First Practice'),
        (MILESTONE_TRAINING, 'Training Date'),
        (MILESTONE_OPENING_DAY, 'Opening Day'),
        (MILESTONE_SEASON_END, 'Season End'),
    ]

    def __repr__(self):
        return f'<RoleTaskTemplate {self.id}: {self.title}>'

    @property
    def milestone_display(self):
        """Human-readable milestone name."""
        for code, label in self.MILESTONES:
            if code == self.trigger_milestone:
                return label
        return self.trigger_milestone

    @property
    def timing_display(self):
        """Human-readable timing description."""
        if self.days_offset == 0:
            return f'On {self.milestone_display}'
        elif self.days_offset < 0:
            return f'{abs(self.days_offset)} days before {self.milestone_display}'
        else:
            return f'{self.days_offset} days after {self.milestone_display}'

    @property
    def reminder_days_list(self):
        """Parse reminder days into list of integers."""
        if not self.reminder_days_before:
            return []
        try:
            return [int(d.strip()) for d in self.reminder_days_before.split(',') if d.strip()]
        except ValueError:
            return []

    def get_milestone_date(self, org_season):
        """Get the milestone date from OrgSeason.

        Args:
            org_season: OrgSeason instance

        Returns:
            date or None
        """
        milestone_map = {
            self.MILESTONE_REGISTRATION_OPENS: 'registration_opens_date',
            self.MILESTONE_EVALUATIONS: 'evaluations_date',
            self.MILESTONE_DRAFT: 'draft_date',
            self.MILESTONE_FIRST_PRACTICE: 'get_first_practice_date',
            self.MILESTONE_TRAINING: 'get_training_date',
            self.MILESTONE_OPENING_DAY: 'get_opening_day_date',
            self.MILESTONE_SEASON_END: 'get_season_end_date',
        }

        attr = milestone_map.get(self.trigger_milestone)
        if not attr:
            return None

        # Check if it's a method or attribute
        if attr.startswith('get_'):
            method = getattr(org_season, attr, None)
            return method() if method else None
        else:
            return getattr(org_season, attr, None)

    def calculate_due_date(self, org_season):
        """Calculate the due date for this task in a season.

        Args:
            org_season: OrgSeason instance

        Returns:
            date or None if milestone date not available
        """
        milestone_date = self.get_milestone_date(org_season)
        if not milestone_date:
            return None

        return milestone_date + timedelta(days=self.days_offset)

    @classmethod
    def get_for_role(cls, role, org_id=1, active_only=True):
        """Get templates for a specific role.

        Args:
            role: Role name
            org_id: Organization ID
            active_only: If True, only return active templates

        Returns:
            List of RoleTaskTemplate instances
        """
        query = cls.query.filter_by(role=role, org_id=org_id)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(cls.sort_order, cls.title).all()

    @classmethod
    def get_all_for_org(cls, org_id=1, active_only=False):
        """Get all templates for an org.

        Args:
            org_id: Organization ID
            active_only: If True, only return active templates

        Returns:
            List of RoleTaskTemplate instances
        """
        query = cls.query.filter_by(org_id=org_id)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(cls.role, cls.sort_order, cls.title).all()


class RoleTaskInstance(db.Model):
    """Instance of a role task for a specific season.

    Created from templates when a season is set up.
    Tracks completion status and reminders.
    """
    __tablename__ = 'sdll_role_task_instances'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('sdll_role_task_templates.id'), nullable=False)

    # Season context
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.Boolean, nullable=False)

    # Computed due date
    due_date = db.Column(db.Date)

    # Status tracking
    status = db.Column(db.String(20), default='pending')
    completed_at = db.Column(db.DateTime)
    completed_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Notes
    notes = db.Column(db.Text)

    # Reminder tracking
    last_reminder_sent = db.Column(db.DateTime)
    reminder_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    template = db.relationship('RoleTaskTemplate', back_populates='instances')
    completed_by = db.relationship('User')

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('template_id', 'year', 'is_spring', name='uq_role_task_season'),
    )

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_SKIPPED = 'skipped'

    STATUSES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    def __repr__(self):
        return f'<RoleTaskInstance {self.id}: {self.template.title if self.template else "?"}>'

    @property
    def status_display(self):
        """Human-readable status name."""
        for code, label in self.STATUSES:
            if code == self.status:
                return label
        return self.status

    @property
    def is_overdue(self):
        """Check if task is overdue."""
        if self.status in (self.STATUS_COMPLETED, self.STATUS_SKIPPED):
            return False
        if not self.due_date:
            return False
        return date.today() > self.due_date

    @property
    def days_until_due(self):
        """Days until due date (negative if overdue)."""
        if not self.due_date:
            return None
        return (self.due_date - date.today()).days

    @property
    def role(self):
        """Get role from template."""
        return self.template.role if self.template else None

    @property
    def title(self):
        """Get title from template."""
        return self.template.title if self.template else None

    @property
    def description(self):
        """Get description from template."""
        return self.template.description if self.template else None

    @property
    def season_name(self):
        """Human-readable season name."""
        return f'{"Spring" if self.is_spring else "Fall"} {self.year}'

    def mark_complete(self, user_id, notes=None):
        """Mark task as completed.

        Args:
            user_id: ID of user completing the task
            notes: Optional completion notes
        """
        self.status = self.STATUS_COMPLETED
        self.completed_at = datetime.utcnow()
        self.completed_by_user_id = user_id
        if notes:
            self.notes = notes
        db.session.commit()

    def mark_in_progress(self):
        """Mark task as in progress."""
        self.status = self.STATUS_IN_PROGRESS
        db.session.commit()

    def mark_skipped(self, notes=None):
        """Mark task as skipped.

        Args:
            notes: Optional reason for skipping
        """
        self.status = self.STATUS_SKIPPED
        if notes:
            self.notes = notes
        db.session.commit()

    @classmethod
    def get_for_role(cls, role, year, is_spring):
        """Get task instances for a role in a season.

        Args:
            role: Role name
            year: Season year
            is_spring: True for spring season

        Returns:
            List of RoleTaskInstance instances
        """
        from sqlalchemy.orm import joinedload

        return cls.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.role == role,
            cls.year == year,
            cls.is_spring == is_spring
        ).options(
            joinedload(cls.template)
        ).order_by(cls.due_date, RoleTaskTemplate.sort_order).all()

    @classmethod
    def get_for_user(cls, user, year, is_spring):
        """Get task instances for all roles a user holds.

        Args:
            user: User instance
            year: Season year
            is_spring: True for spring season

        Returns:
            List of RoleTaskInstance instances
        """
        from sqlalchemy.orm import joinedload

        user_roles = user.roles_list if user else []
        if not user_roles:
            return []

        return cls.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.role.in_(user_roles),
            cls.year == year,
            cls.is_spring == is_spring
        ).options(
            joinedload(cls.template)
        ).order_by(cls.due_date, RoleTaskTemplate.sort_order).all()

    @classmethod
    def get_overdue(cls, org_id=1):
        """Get all overdue tasks.

        Returns:
            List of overdue RoleTaskInstance instances
        """
        from sqlalchemy.orm import joinedload

        return cls.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.org_id == org_id,
            cls.due_date < date.today(),
            cls.status.in_([cls.STATUS_PENDING, cls.STATUS_IN_PROGRESS])
        ).options(
            joinedload(cls.template)
        ).order_by(cls.due_date).all()

    @classmethod
    def get_upcoming(cls, days=7, org_id=1):
        """Get tasks due in the next N days.

        Args:
            days: Number of days to look ahead
            org_id: Organization ID

        Returns:
            List of RoleTaskInstance instances
        """
        from sqlalchemy.orm import joinedload

        today = date.today()
        end_date = today + timedelta(days=days)

        return cls.query.join(RoleTaskTemplate).filter(
            RoleTaskTemplate.org_id == org_id,
            cls.due_date >= today,
            cls.due_date <= end_date,
            cls.status.in_([cls.STATUS_PENDING, cls.STATUS_IN_PROGRESS])
        ).options(
            joinedload(cls.template)
        ).order_by(cls.due_date).all()
