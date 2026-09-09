"""UmpireGamePayment model - game-specific payment multipliers for umpires."""

from datetime import datetime
from app.extensions import db


class UmpireGamePayment(db.Model):
    """Tracks game-specific payment multipliers for umpires.

    Used for incentive games (2x pay), special events, or other
    non-standard payment situations.
    """
    __tablename__ = 'sdll_umpire_game_payments'

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID'), nullable=True)
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id'), nullable=True)
    assignr_official_id = db.Column(db.Integer, nullable=True)  # For Assignr-based lookups
    multiplier = db.Column(db.Numeric(3, 2), default=1.0)  # 1.0, 1.5, 2.0, etc.
    notes = db.Column(db.String(255), nullable=True)  # Reason for multiplier
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=True)

    # Relationships
    game = db.relationship('Game', backref='payment_adjustments')
    umpire_profile = db.relationship('UmpireProfile', backref='payment_adjustments')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<UmpireGamePayment game={self.game_id} multiplier={self.multiplier}>'

    @classmethod
    def get_for_game(cls, game_id, assignr_official_id=None):
        """Get payment adjustment for a specific game and umpire.

        Args:
            game_id: Local game ID
            assignr_official_id: Assignr official ID (optional)

        Returns:
            UmpireGamePayment or None
        """
        query = cls.query.filter_by(game_id=game_id)
        if assignr_official_id:
            query = query.filter_by(assignr_official_id=assignr_official_id)
        return query.first()

    @classmethod
    def get_multipliers_for_games(cls, game_ids):
        """Get all payment multipliers for a list of games.

        Args:
            game_ids: List of game IDs

        Returns:
            Dict mapping (game_id, assignr_official_id) -> multiplier
        """
        if not game_ids:
            return {}

        adjustments = cls.query.filter(cls.game_id.in_(game_ids)).all()
        result = {}
        for adj in adjustments:
            key = (adj.game_id, adj.assignr_official_id)
            result[key] = float(adj.multiplier)
        return result
