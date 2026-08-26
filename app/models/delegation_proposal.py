"""Delegation Proposal models - workflow for reviewing and accepting umpire delegations."""

import json
from datetime import datetime
from app.extensions import db


class DelegationProposal(db.Model):
    """A proposal for delegating undelegated games to umpire partners.

    Proposals are generated when new games need umpire delegation. Admins can
    review the suggested allocations, make adjustments, and accept the proposal
    to update all games at once.
    """
    __tablename__ = 'sdll_delegation_proposals'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)
    status = db.Column(db.Enum('pending', 'accepted', 'rejected'), default='pending', nullable=False)
    accepted_at = db.Column(db.DateTime)
    accepted_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))
    game_count = db.Column(db.Integer, default=0, nullable=False)
    tier1_violations = db.Column(db.Integer, default=0, nullable=False)
    tier2_violations = db.Column(db.Integer, default=0, nullable=False)
    summary_json = db.Column(db.Text)

    # Relationships
    games = db.relationship('DelegationProposalGame', back_populates='proposal',
                            cascade='all, delete-orphan', lazy='joined')
    creator = db.relationship('User', foreign_keys=[created_by])
    acceptor = db.relationship('User', foreign_keys=[accepted_by])

    def __repr__(self):
        return f'<DelegationProposal {self.id}: {self.game_count} games, {self.status}>'

    @property
    def summary(self):
        """Parse summary_json into dict."""
        if self.summary_json:
            try:
                return json.loads(self.summary_json)
            except json.JSONDecodeError:
                return {}
        return {}

    @summary.setter
    def summary(self, value):
        """Serialize dict to summary_json."""
        self.summary_json = json.dumps(value) if value else None

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_accepted(self):
        return self.status == 'accepted'

    @property
    def has_violations(self):
        return self.tier1_violations > 0 or self.tier2_violations > 0

    @property
    def has_tier1_violations(self):
        return self.tier1_violations > 0

    def get_games_by_partner(self):
        """Group proposal games by their assigned partner.

        Returns:
            dict: {partner_id: [DelegationProposalGame, ...]}
        """
        by_partner = {}
        for pg in self.games:
            partner_id = pg.final_partner_id or pg.suggested_partner_id
            if partner_id not in by_partner:
                by_partner[partner_id] = []
            by_partner[partner_id].append(pg)
        return by_partner

    def get_sequences(self):
        """Get back-to-back sequences.

        Returns:
            dict: {sequence_id: [DelegationProposalGame, ...]}
        """
        sequences = {}
        for pg in self.games:
            if pg.sequence_id is not None:
                if pg.sequence_id not in sequences:
                    sequences[pg.sequence_id] = []
                sequences[pg.sequence_id].append(pg)
        return sequences

    @classmethod
    def get_pending_for_season(cls, year, is_spring):
        """Get pending proposal for a season, if any."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring,
            status='pending'
        ).first()

    @classmethod
    def get_for_season(cls, year, is_spring):
        """Get all proposals for a season, ordered by created_at desc."""
        return cls.query.filter_by(
            year=year,
            is_spring=is_spring
        ).order_by(cls.created_at.desc()).all()


class DelegationProposalGame(db.Model):
    """A game included in a delegation proposal with its suggested assignment.

    Links a game to a proposal with the suggested partner and optional override.
    Tracks back-to-back sequences for Tier I constraint enforcement.
    """
    __tablename__ = 'sdll_delegation_proposal_games'

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('sdll_delegation_proposals.id', ondelete='CASCADE'), nullable=False)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'), nullable=False)
    suggested_partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'), nullable=False)
    final_partner_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_partners.id'))
    is_back_to_back = db.Column(db.Boolean, default=False)
    sequence_id = db.Column(db.Integer)

    # Relationships
    proposal = db.relationship('DelegationProposal', back_populates='games')
    game = db.relationship('Game')
    suggested_partner = db.relationship('UmpirePartner', foreign_keys=[suggested_partner_id])
    final_partner = db.relationship('UmpirePartner', foreign_keys=[final_partner_id])

    def __repr__(self):
        partner_id = self.final_partner_id or self.suggested_partner_id
        return f'<DelegationProposalGame game={self.game_id} partner={partner_id}>'

    @property
    def assigned_partner_id(self):
        """Get the partner this game will be assigned to (final or suggested)."""
        return self.final_partner_id or self.suggested_partner_id

    @property
    def assigned_partner(self):
        """Get the partner object this game will be assigned to."""
        return self.final_partner or self.suggested_partner

    @property
    def is_overridden(self):
        """Check if admin has overridden the suggested assignment."""
        return self.final_partner_id is not None and self.final_partner_id != self.suggested_partner_id

    @property
    def is_in_sequence(self):
        """Check if this game is part of a back-to-back sequence."""
        return self.sequence_id is not None
