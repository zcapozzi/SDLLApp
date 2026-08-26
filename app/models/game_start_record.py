"""Model for recording game start times (first pitch).

This allows users (coaches, parents) to record when a game actually started,
which is used to determine when the "no new inning" time window applies.
"""

from datetime import datetime
from app.extensions import db


class GameStartRecord(db.Model):
    """Record of when a game actually started (first pitch)."""

    __tablename__ = 'sdll_game_start_records'

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('sdll_games.ID'), nullable=False, index=True)

    # The reported first pitch time
    start_time = db.Column(db.DateTime, nullable=False)

    # Who reported it
    user_id = db.Column(db.Integer, db.ForeignKey('sdll_users.ID'), nullable=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)  # For anonymous users

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    game = db.relationship('Game', backref=db.backref('start_records', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('game_start_records', lazy='dynamic'))

    def __repr__(self):
        return f'<GameStartRecord game={self.game_id} start={self.start_time}>'

    @classmethod
    def get_for_game(cls, game_id):
        """Get all start records for a game, most recent first."""
        return cls.query.filter_by(game_id=game_id).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_for_game_by_session(cls, game_id, session_id):
        """Get start record for a game by session ID."""
        if not session_id:
            return None
        return cls.query.filter_by(game_id=game_id, session_id=session_id).first()

    @classmethod
    def get_for_game_by_user(cls, game_id, user_id):
        """Get start record for a game by user ID."""
        if not user_id:
            return None
        return cls.query.filter_by(game_id=game_id, user_id=user_id).first()

    @classmethod
    def record_start(cls, game_id, start_time, user_id=None, session_id=None):
        """Record or update a game start time.

        If the user/session already has a record for this game, update it.
        Otherwise, create a new record.

        Returns the record.
        """
        existing = None

        # Check for existing record by user first, then by session
        if user_id:
            existing = cls.get_for_game_by_user(game_id, user_id)
        if not existing and session_id:
            existing = cls.get_for_game_by_session(game_id, session_id)

        if existing:
            existing.start_time = start_time
            existing.updated_at = datetime.utcnow()
            # If user logged in after anonymous submission, associate with user
            if user_id and not existing.user_id:
                existing.user_id = user_id
            db.session.commit()
            return existing

        # Create new record
        record = cls(
            game_id=game_id,
            start_time=start_time,
            user_id=user_id,
            session_id=session_id
        )
        db.session.add(record)
        db.session.commit()
        return record

    @classmethod
    def get_latest_for_game(cls, game_id):
        """Get the most recent start record for a game."""
        return cls.query.filter_by(game_id=game_id).order_by(cls.updated_at.desc()).first()
