"""Artifact model - knowledge base documents, templates, and checklists."""

from datetime import datetime
from app.extensions import db


class Artifact(db.Model):
    """Institutional knowledge artifact.

    Stores documents, templates, checklists, and external links
    that help board members perform their roles effectively.
    """
    __tablename__ = 'sdll_artifacts'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.BigInteger, db.ForeignKey('sdll_organizations.ID'), nullable=False)

    # Classification
    artifact_type = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(50))

    # Content
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)  # For templates/checklists
    external_url = db.Column(db.String(500))  # For links
    file_path = db.Column(db.String(500))  # For uploaded documents

    # Access control
    visibility = db.Column(db.String(20), default='role')
    allowed_roles = db.Column(db.String(255))  # Pipe-separated

    # Metadata
    tags = db.Column(db.String(255))  # Comma-separated
    sort_order = db.Column(db.Integer, default=0)

    # Audit
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    updated_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    updated_by = db.relationship('User', foreign_keys=[updated_by_user_id])

    # Type constants
    TYPE_DOCUMENT = 'document'
    TYPE_TEMPLATE = 'template'
    TYPE_CHECKLIST = 'checklist'
    TYPE_LINK = 'link'

    TYPES = [
        (TYPE_DOCUMENT, 'Document'),
        (TYPE_TEMPLATE, 'Template'),
        (TYPE_CHECKLIST, 'Checklist'),
        (TYPE_LINK, 'External Link'),
    ]

    # Category constants
    CATEGORY_UMPIRES = 'umpires'
    CATEGORY_COACHES = 'coaches'
    CATEGORY_SCHEDULING = 'scheduling'
    CATEGORY_FACILITIES = 'facilities'
    CATEGORY_FINANCE = 'finance'
    CATEGORY_GENERAL = 'general'

    CATEGORIES = [
        (CATEGORY_UMPIRES, 'Umpires'),
        (CATEGORY_COACHES, 'Coaches'),
        (CATEGORY_SCHEDULING, 'Scheduling'),
        (CATEGORY_FACILITIES, 'Facilities'),
        (CATEGORY_FINANCE, 'Finance'),
        (CATEGORY_GENERAL, 'General'),
    ]

    # Visibility constants
    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_ROLE = 'role'
    VISIBILITY_ADMIN = 'admin'

    VISIBILITIES = [
        (VISIBILITY_PUBLIC, 'All Board Members'),
        (VISIBILITY_ROLE, 'Specific Roles'),
        (VISIBILITY_ADMIN, 'Admins Only'),
    ]

    def __repr__(self):
        return f'<Artifact {self.id}: {self.title}>'

    @property
    def type_display(self):
        """Human-readable type name."""
        for code, label in self.TYPES:
            if code == self.artifact_type:
                return label
        return self.artifact_type

    @property
    def category_display(self):
        """Human-readable category name."""
        for code, label in self.CATEGORIES:
            if code == self.category:
                return label
        return self.category or 'Uncategorized'

    @property
    def visibility_display(self):
        """Human-readable visibility name."""
        for code, label in self.VISIBILITIES:
            if code == self.visibility:
                return label
        return self.visibility

    @property
    def allowed_role_list(self):
        """Parse allowed roles into list."""
        if not self.allowed_roles:
            return []
        return [r.strip() for r in self.allowed_roles.split('|') if r.strip()]

    @property
    def tag_list(self):
        """Parse tags into list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def can_view(self, user):
        """Check if user can view this artifact.

        Args:
            user: User instance to check

        Returns:
            True if user can view, False otherwise
        """
        if not user or not user.is_authenticated:
            return False

        # Admins can see everything
        if user.is_admin():
            return True

        # Public visibility - any authenticated user
        if self.visibility == self.VISIBILITY_PUBLIC:
            return True

        # Admin-only visibility
        if self.visibility == self.VISIBILITY_ADMIN:
            return user.is_admin()

        # Role-based visibility
        if self.visibility == self.VISIBILITY_ROLE:
            if not self.allowed_roles:
                return True  # No roles specified = all roles
            return user.has_role(*self.allowed_role_list)

        return False

    @classmethod
    def get_for_user(cls, user, org_id=1, category=None, artifact_type=None):
        """Get artifacts visible to a user.

        Args:
            user: User to filter for
            org_id: Organization ID
            category: Optional category filter
            artifact_type: Optional type filter

        Returns:
            List of Artifact instances
        """
        query = cls.query.filter_by(org_id=org_id)

        if category:
            query = query.filter_by(category=category)
        if artifact_type:
            query = query.filter_by(artifact_type=artifact_type)

        artifacts = query.order_by(cls.category, cls.sort_order, cls.title).all()

        # Filter by visibility
        return [a for a in artifacts if a.can_view(user)]

    @classmethod
    def get_for_role(cls, role, org_id=1):
        """Get artifacts relevant to a specific role.

        Args:
            role: Role name to filter for
            org_id: Organization ID

        Returns:
            List of Artifact instances
        """
        all_artifacts = cls.query.filter_by(org_id=org_id).order_by(
            cls.category, cls.sort_order, cls.title
        ).all()

        result = []
        for artifact in all_artifacts:
            # Public artifacts
            if artifact.visibility == cls.VISIBILITY_PUBLIC:
                result.append(artifact)
            # Role-specific artifacts
            elif artifact.visibility == cls.VISIBILITY_ROLE:
                if not artifact.allowed_roles or role in artifact.allowed_role_list:
                    result.append(artifact)

        return result

    @classmethod
    def search(cls, query_str, user, org_id=1):
        """Search artifacts by title, description, and tags.

        Args:
            query_str: Search query
            user: User to filter visibility for
            org_id: Organization ID

        Returns:
            List of matching Artifact instances
        """
        query_lower = query_str.lower()

        all_artifacts = cls.get_for_user(user, org_id)

        return [
            a for a in all_artifacts
            if (query_lower in a.title.lower() or
                (a.description and query_lower in a.description.lower()) or
                (a.tags and query_lower in a.tags.lower()))
        ]
