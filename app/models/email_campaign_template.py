"""Email Campaign Template model - reusable email templates with variable placeholders."""

from datetime import datetime
from app.extensions import db


class EmailCampaignTemplate(db.Model):
    """Stores reusable email templates with {{variable}} placeholders.

    Templates define the structure and timing of email campaigns.
    Each template can be triggered by season milestones or manually.
    """
    __tablename__ = 'sdll_email_campaign_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)

    # Template content with {{variable}} placeholders
    subject_template = db.Column(db.String(255), nullable=False)
    body_html_template = db.Column(db.Text, nullable=False)
    body_text_template = db.Column(db.Text)

    # Trigger settings
    trigger_type = db.Column(db.Enum('milestone', 'manual'), default='milestone')
    trigger_milestone = db.Column(db.String(50))  # first_practice, opening_day, training_date
    trigger_days_offset = db.Column(db.Integer, default=0)  # Days before (-) or after (+)

    # Audience targeting
    recipient_type = db.Column(db.String(50), nullable=False)  # partner, lead, active_umpire, etc.
    recipient_status_filter = db.Column(db.String(100))  # e.g., "prospective,contacted"

    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    instances = db.relationship('EmailCampaignInstance', back_populates='template',
                                cascade='all, delete-orphan')

    # Category constants
    CATEGORY_PARTNER = 'partner'
    CATEGORY_PROSPECTIVE = 'prospective'
    CATEGORY_RETURNING = 'returning'
    CATEGORY_ADMIN_MARKETING = 'admin_marketing'

    CATEGORIES = [
        (CATEGORY_PARTNER, 'Partner Coordination'),
        (CATEGORY_PROSPECTIVE, 'Prospective Umpire'),
        (CATEGORY_RETURNING, 'Returning Umpire'),
        (CATEGORY_ADMIN_MARKETING, 'League Admin Marketing'),
    ]

    # Milestone constants
    MILESTONE_FIRST_PRACTICE = 'first_practice'
    MILESTONE_OPENING_DAY = 'opening_day'
    MILESTONE_TRAINING_DATE = 'training_date'
    MILESTONE_SEASON_END = 'season_end'

    MILESTONES = [
        (MILESTONE_FIRST_PRACTICE, 'First Practice'),
        (MILESTONE_OPENING_DAY, 'Opening Day'),
        (MILESTONE_TRAINING_DATE, 'Training Date'),
        (MILESTONE_SEASON_END, 'Season End'),
    ]

    # Recipient type constants
    RECIPIENT_PARTNER = 'partner'
    RECIPIENT_LEAD = 'lead'
    RECIPIENT_ACTIVE_UMPIRE = 'active_umpire'
    RECIPIENT_LEAGUE_ADMIN = 'league_admin'
    RECIPIENT_COORDINATOR = 'coordinator'

    def __repr__(self):
        return f'<EmailCampaignTemplate {self.code}>'

    @property
    def is_active(self):
        return self.active == 1

    @property
    def category_display(self):
        """Human-readable category name."""
        for code, label in self.CATEGORIES:
            if code == self.category:
                return label
        return self.category

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
        if self.trigger_type == 'manual':
            return 'Manual trigger'

        if not self.trigger_milestone:
            return 'No milestone set'

        milestone = self.milestone_display
        offset = self.trigger_days_offset or 0

        if offset == 0:
            return f'On {milestone}'
        elif offset < 0:
            return f'{abs(offset)} days before {milestone}'
        else:
            return f'{offset} days after {milestone}'

    @property
    def recipient_status_list(self):
        """Parse recipient_status_filter into a list."""
        if not self.recipient_status_filter:
            return []
        return [s.strip() for s in self.recipient_status_filter.split(',') if s.strip()]

    @classmethod
    def get_active(cls):
        """Get all active templates."""
        return cls.query.filter_by(active=1).order_by(cls.category, cls.name).all()

    @classmethod
    def get_by_code(cls, code):
        """Find template by unique code."""
        return cls.query.filter_by(code=code).first()

    @classmethod
    def get_by_category(cls, category):
        """Get active templates in a category."""
        return cls.query.filter_by(category=category, active=1).order_by(cls.name).all()

    @classmethod
    def get_milestone_templates(cls):
        """Get all templates triggered by milestones."""
        return cls.query.filter_by(trigger_type='milestone', active=1).all()

    def get_available_variables(self):
        """Return list of variables available for this template.

        Returns dict of variable_name -> description.
        """
        # Common variables available to all templates
        variables = {
            'season_name': 'Full season name (e.g., "Spring 2026")',
            'year': 'Season year (e.g., "2026")',
            'first_practice_date': 'Earliest first practice date',
            'opening_day_date': 'Earliest opening day date',
            'season_end_date': 'Latest season end date',
            'training_date': 'Umpire training session date',
            'coordinator_email': 'Umpire coordinator email',
            'coordinator_phone': 'Umpire coordinator phone number',
        }

        # Add recipient-specific variables
        if self.recipient_type == self.RECIPIENT_PARTNER:
            variables['partner_name'] = 'Partner company name'
            variables['recipient_name'] = 'Partner contact name'
        elif self.recipient_type in (self.RECIPIENT_LEAD, self.RECIPIENT_ACTIVE_UMPIRE):
            variables['recipient_name'] = 'Umpire name'
        else:
            variables['recipient_name'] = 'Recipient name'

        return variables
