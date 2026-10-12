"""Draft models - DraftSession and DraftPick for managing drafts."""

from datetime import datetime
from app.extensions import db


class DraftSession(db.Model):
    """Represents a draft session for a league in a season."""
    __tablename__ = 'sdll_draft_sessions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'), nullable=False)
    league_id = db.Column(db.BigInteger, db.ForeignKey('sdll_leagues.ID'), nullable=False)
    name = db.Column(db.String(100))

    # Status: pending, active, paused, completed
    status = db.Column(db.String(20), default='pending')

    # Draft configuration
    draft_order_type = db.Column(db.String(20), default='snake')  # snake, linear
    rounds = db.Column(db.Integer, default=12)  # Number of rounds

    # Current state
    current_round = db.Column(db.Integer, default=1)
    current_pick_number = db.Column(db.Integer, default=1)
    current_team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=True)

    # Timestamps
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Creator
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=True)

    # Relationships
    org_season = db.relationship('OrgSeason', backref='draft_sessions')
    league = db.relationship('League', backref='draft_sessions')
    picks = db.relationship('DraftPick', backref='session', lazy='dynamic',
                           order_by='DraftPick.pick_number')
    current_team = db.relationship('TeamSeason', foreign_keys=[current_team_id])

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'

    # Draft order constants
    ORDER_SNAKE = 'snake'
    ORDER_LINEAR = 'linear'

    def __repr__(self):
        return f'<DraftSession {self.id}: {self.name or "Unnamed"} ({self.status})>'

    @property
    def is_active(self):
        """Check if draft is currently active."""
        return self.status == self.STATUS_ACTIVE

    @property
    def is_completed(self):
        """Check if draft is completed."""
        return self.status == self.STATUS_COMPLETED

    @property
    def can_make_picks(self):
        """Check if picks can be made."""
        return self.status in (self.STATUS_ACTIVE, self.STATUS_PAUSED)

    @property
    def total_picks(self):
        """Get total number of picks made."""
        return self.picks.count()

    @property
    def league_display_name(self):
        """Get league display name for the season."""
        if self.league and self.org_season:
            return self.league.get_seasonal_name(self.org_season.is_spring)
        return self.league.display_name if self.league else 'Unknown'

    def start(self):
        """Start the draft."""
        if self.status != self.STATUS_PENDING:
            raise ValueError("Can only start a pending draft")
        self.status = self.STATUS_ACTIVE
        self.started_at = datetime.utcnow()
        db.session.commit()

    def pause(self):
        """Pause the draft."""
        if self.status != self.STATUS_ACTIVE:
            raise ValueError("Can only pause an active draft")
        self.status = self.STATUS_PAUSED
        db.session.commit()

    def resume(self):
        """Resume a paused draft."""
        if self.status != self.STATUS_PAUSED:
            raise ValueError("Can only resume a paused draft")
        self.status = self.STATUS_ACTIVE
        db.session.commit()

    def complete(self):
        """Mark draft as completed."""
        self.status = self.STATUS_COMPLETED
        self.completed_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def get_active_for_league(cls, org_season_id, league_id):
        """Get active draft session for a league."""
        return cls.query.filter_by(
            org_season_id=org_season_id,
            league_id=league_id,
            status=cls.STATUS_ACTIVE
        ).first()


class DraftPick(db.Model):
    """Represents a single pick in a draft."""
    __tablename__ = 'sdll_draft_picks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sdll_draft_sessions.id', ondelete='CASCADE'),
                          nullable=False)
    pick_number = db.Column(db.Integer, nullable=False)  # Overall pick number (1, 2, 3, ...)
    round_number = db.Column(db.Integer, nullable=False)

    # Team making the pick
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)

    # Player picked (NULL until pick is made)
    player_id = db.Column(db.Integer, db.ForeignKey('sdll_players.id'), nullable=True)

    # When the pick was made
    picked_at = db.Column(db.DateTime)

    # Draft trade tracking
    is_traded = db.Column(db.SmallInteger, default=0)
    original_team_id = db.Column(db.BigInteger)  # Team that originally had this pick

    # Notes (for manual adjustments, etc.)
    notes = db.Column(db.Text)

    # Relationships
    team = db.relationship('TeamSeason', foreign_keys=[team_id], backref='draft_picks')
    player = db.relationship('Player', backref='draft_picks')

    # Unique constraint: one pick per pick_number per session
    __table_args__ = (
        db.UniqueConstraint('session_id', 'pick_number', name='uq_session_pick'),
    )

    def __repr__(self):
        return f'<DraftPick #{self.pick_number} R{self.round_number}>'

    @property
    def is_made(self):
        """Check if this pick has been made."""
        return self.player_id is not None

    @property
    def team_display_name(self):
        """Get team display name."""
        if self.team:
            return self.team.scheduler_display_name
        return 'Unknown'

    @property
    def player_display_name(self):
        """Get player display name."""
        if self.player:
            return f"{self.player.last_name}, {self.player.first_name}"
        return None

    def make_pick(self, player_id):
        """Make this pick."""
        if self.player_id is not None:
            raise ValueError("Pick already made")

        self.player_id = player_id
        self.picked_at = datetime.utcnow()
        db.session.commit()


class DraftOrder(db.Model):
    """Represents the draft order for a session."""
    __tablename__ = 'sdll_draft_order'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sdll_draft_sessions.id', ondelete='CASCADE'),
                          nullable=False)
    position = db.Column(db.Integer, nullable=False)  # 1, 2, 3, ... for draft order
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)

    # Relationships
    session = db.relationship('DraftSession', backref='draft_order')
    team = db.relationship('TeamSeason')

    # Unique constraint: one position per session
    __table_args__ = (
        db.UniqueConstraint('session_id', 'position', name='uq_session_position'),
        db.UniqueConstraint('session_id', 'team_id', name='uq_session_team'),
    )

    def __repr__(self):
        return f'<DraftOrder #{self.position} Team {self.team_id}>'


class DraftProtection(db.Model):
    """Represents a protected draft pick (e.g., coach's child must be drafted in round N)."""
    __tablename__ = 'sdll_draft_protections'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sdll_draft_sessions.id', ondelete='CASCADE'),
                          nullable=False)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('sdll_players.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)  # Round this player must be drafted

    # Reason for protection (display purposes)
    reason = db.Column(db.String(100), default="Coach's child")

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    session = db.relationship('DraftSession', backref='protections')
    team = db.relationship('TeamSeason', backref='draft_protections')
    player = db.relationship('Player', backref='draft_protections')

    # Unique constraint: one protection per player per session
    __table_args__ = (
        db.UniqueConstraint('session_id', 'player_id', name='uq_session_player_protection'),
    )

    def __repr__(self):
        return f'<DraftProtection Player {self.player_id} -> Team {self.team_id} R{self.round_number}>'

    @property
    def player_display_name(self):
        """Get player display name."""
        if self.player:
            return f"{self.player.last_name}, {self.player.first_name}"
        return 'Unknown'

    @property
    def team_display_name(self):
        """Get team display name."""
        if self.team:
            return self.team.scheduler_display_name
        return 'Unknown'
