"""UmpireDelegationAllocation model - allocation percentage for a partner within a delegation rule.

This model allows flexible allocation of umpire assignments across any number of partners,
replacing the hardcoded academy_pct, diamond_pct, dynamic_pct columns in the delegation rules table.
"""

from datetime import datetime
from app.extensions import db


class UmpireDelegationAllocation(db.Model):
    """Allocation percentage for a partner within a delegation rule.

    Each rule can have multiple allocations (one per active partner).
    All partners (including SDL/Academy) have records in sdll_umpire_partners,
    so partner_id is always required (not nullable).
    """
    __tablename__ = 'sdll_umpire_delegation_allocations'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(
        db.Integer,
        db.ForeignKey('sdll_umpire_delegation_rules.id', ondelete='CASCADE'),
        nullable=False
    )
    partner_id = db.Column(
        db.Integer,
        db.ForeignKey('sdll_umpire_partners.id', ondelete='CASCADE'),
        nullable=False
    )
    percentage = db.Column(db.SmallInteger, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    rule = db.relationship('UmpireDelegationRule', back_populates='allocations')
    partner = db.relationship('UmpirePartner')

    # Unique constraint: one allocation per partner per rule
    __table_args__ = (
        db.UniqueConstraint('rule_id', 'partner_id', name='uk_rule_partner'),
    )

    def __repr__(self):
        partner_code = self.partner.short_code if self.partner else '?'
        return f'<UmpireDelegationAllocation rule={self.rule_id} {partner_code}={self.percentage}%>'

    @property
    def source_name(self):
        """Human-readable source name (from partner record)."""
        if self.partner:
            # Show "Academy (SDLL)" for SDL partner
            if self.partner.short_code == 'SDL':
                return 'Academy (SDLL)'
            return self.partner.name
        return 'Unknown'

    @property
    def source_code(self):
        """Short code for this source (from partner record), lowercase."""
        return self.partner.short_code.lower() if self.partner else 'unknown'

    @property
    def is_academy(self):
        """Check if this allocation is for the Academy (SDL)."""
        return self.partner and self.partner.short_code == 'SDL'

    @classmethod
    def get_for_rule(cls, rule_id):
        """Get all allocations for a rule.

        Args:
            rule_id: Delegation rule ID

        Returns:
            List of UmpireDelegationAllocation objects
        """
        return cls.query.filter_by(rule_id=rule_id).all()

    @classmethod
    def get_for_rule_and_partner(cls, rule_id, partner_id):
        """Get allocation for a specific rule and partner.

        Args:
            rule_id: Delegation rule ID
            partner_id: Partner ID

        Returns:
            UmpireDelegationAllocation or None
        """
        return cls.query.filter_by(
            rule_id=rule_id,
            partner_id=partner_id
        ).first()
