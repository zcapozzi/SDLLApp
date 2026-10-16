"""CallUpRequest model - tracks substitute/call-up requests for players to sub up."""

from datetime import datetime
from app.extensions import db


class CallUpRequest(db.Model):
    """
    Tracks when a player is asked to substitute in a game for a higher division.

    The Player Agent uses this to:
    - Track which players have been contacted for call-ups
    - Record responses (accepted, declined, no response)
    - Maintain equity by tracking call-up history
    """
    __tablename__ = 'sdll_callup_requests'

    id = db.Column(db.Integer, primary_key=True)

    # Context - which player for which game
    player_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_player_seasons.id'), nullable=False)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID'), nullable=False)
    target_team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'), nullable=False)

    # Request details
    requested_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    contact_email = db.Column(db.String(255))  # Which parent email was contacted

    # Status: pending -> accepted / declined / no_response / cancelled
    status = db.Column(db.String(20), default='pending')

    # Response tracking
    responded_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)  # Any notes (reason for decline, etc.)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    player_season = db.relationship('PlayerSeason', backref='callup_requests')
    game = db.relationship('Game', backref='callup_requests')
    target_team = db.relationship('TeamSeason', foreign_keys=[target_team_id])
    requester = db.relationship('User', foreign_keys=[requested_by])

    # Valid statuses
    STATUSES = ['pending', 'accepted', 'declined', 'no_response', 'cancelled']

    def __repr__(self):
        return f'<CallUpRequest {self.id}: player={self.player_season_id} game={self.game_id} status={self.status}>'

    @property
    def is_active(self):
        """Check if request is still pending."""
        return self.status == 'pending'

    @property
    def is_resolved(self):
        """Check if request has been resolved (accepted, declined, no_response, cancelled)."""
        return self.status in ('accepted', 'declined', 'no_response', 'cancelled')

    @property
    def status_display(self):
        """Get human-readable status."""
        return {
            'pending': 'Awaiting Response',
            'accepted': 'Accepted',
            'declined': 'Declined',
            'no_response': 'No Response',
            'cancelled': 'Cancelled'
        }.get(self.status, self.status.title())

    @property
    def status_color(self):
        """Get status badge color for UI."""
        return {
            'pending': '#f39c12',  # Orange
            'accepted': '#27ae60',  # Green
            'declined': '#e74c3c',  # Red
            'no_response': '#95a5a6',  # Gray
            'cancelled': '#7f8c8d'  # Dark gray
        }.get(self.status, '#888')

    def accept(self, notes=None):
        """Mark the request as accepted."""
        self.status = 'accepted'
        self.responded_at = datetime.utcnow()
        if notes:
            self.notes = notes
        db.session.commit()

    def decline(self, notes=None):
        """Mark the request as declined."""
        self.status = 'declined'
        self.responded_at = datetime.utcnow()
        if notes:
            self.notes = notes
        db.session.commit()

    def mark_no_response(self, notes=None):
        """Mark the request as no response received."""
        self.status = 'no_response'
        self.responded_at = datetime.utcnow()
        if notes:
            self.notes = notes
        db.session.commit()

    def cancel(self, notes=None):
        """Cancel the request."""
        self.status = 'cancelled'
        self.responded_at = datetime.utcnow()
        if notes:
            self.notes = notes
        db.session.commit()

    @classmethod
    def get_active_for_season(cls, org_season_id):
        """Get all active (pending) requests for a season."""
        from app.models.player import PlayerSeason
        return cls.query.join(
            PlayerSeason, cls.player_season_id == PlayerSeason.id
        ).filter(
            PlayerSeason.org_season_id == org_season_id,
            cls.status == 'pending'
        ).order_by(cls.requested_at.desc()).all()

    @classmethod
    def get_for_player(cls, player_season_id):
        """Get all call-up requests for a specific player season."""
        return cls.query.filter_by(
            player_season_id=player_season_id
        ).order_by(cls.requested_at.desc()).all()

    @classmethod
    def count_for_player(cls, player_season_id, status=None):
        """Count call-up requests for a player, optionally filtered by status."""
        query = cls.query.filter_by(player_season_id=player_season_id)
        if status:
            query = query.filter_by(status=status)
        return query.count()

    @classmethod
    def count_accepted_for_player(cls, player_season_id):
        """Count accepted call-ups for a player (for equity tracking)."""
        return cls.count_for_player(player_season_id, status='accepted')
