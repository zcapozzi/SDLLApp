"""FieldCaptain model - links users to fields they manage.

Field captains are responsible for maintaining specific fields,
reporting issues, and coordinating field preparation.
"""

from datetime import datetime
from app.extensions import db


class FieldCaptain(db.Model):
    """Links a user with fieldCaptain role to fields they manage."""
    __tablename__ = 'sdll_field_captains'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='CASCADE'),
                        nullable=False)
    field_id = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID', ondelete='CASCADE'),
                         nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.BigInteger)

    # Relationships
    user = db.relationship('User', backref=db.backref('field_assignments', lazy='dynamic'))
    field = db.relationship('Field', backref=db.backref('captains', lazy='dynamic'))

    def __repr__(self):
        return f'<FieldCaptain user={self.user_id} field={self.field_id}>'

    @classmethod
    def get_captains_for_field(cls, field_id):
        """Get all captains for a specific field."""
        return cls.query.filter_by(field_id=field_id).all()

    @classmethod
    def get_fields_for_user(cls, user_id):
        """Get all fields a user is captain of."""
        from app.models.field import Field
        assignments = cls.query.filter_by(user_id=user_id).all()
        field_ids = [a.field_id for a in assignments]
        if not field_ids:
            return []
        return Field.query.filter(Field.ID.in_(field_ids)).all()

    @classmethod
    def assign_captain(cls, user_id, field_id, created_by=None):
        """Assign a user as captain of a field.

        Args:
            user_id: The user's ID
            field_id: The field's ID
            created_by: ID of user making the assignment

        Returns:
            FieldCaptain object or None if already exists
        """
        existing = cls.query.filter_by(user_id=user_id, field_id=field_id).first()
        if existing:
            return None

        assignment = cls(
            user_id=user_id,
            field_id=field_id,
            created_by=created_by
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment

    @classmethod
    def remove_captain(cls, user_id, field_id):
        """Remove a captain assignment.

        Returns:
            True if removed, False if not found
        """
        assignment = cls.query.filter_by(user_id=user_id, field_id=field_id).first()
        if not assignment:
            return False

        db.session.delete(assignment)
        db.session.commit()
        return True

    @classmethod
    def is_captain_of(cls, user_id, field_id):
        """Check if a user is captain of a specific field."""
        return cls.query.filter_by(user_id=user_id, field_id=field_id).first() is not None

    @classmethod
    def get_fields_without_captains(cls):
        """Get all active fields that don't have any captains assigned."""
        from app.models.field import Field

        # Get field IDs that have captains
        fields_with_captains = db.session.query(cls.field_id).distinct().all()
        captain_field_ids = [f[0] for f in fields_with_captains]

        # Return active fields not in that list
        if captain_field_ids:
            return Field.query.filter(
                Field.active == 1,
                ~Field.ID.in_(captain_field_ids)
            ).order_by(Field.location_title).all()
        else:
            return Field.query.filter_by(active=1).order_by(Field.location_title).all()
