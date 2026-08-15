"""UmpireAssignment model - tracks umpire assignments to games"""

from datetime import datetime
from app.extensions import db


class UmpireAssignment(db.Model):
    """Tracks which umpires are assigned to which games"""
    __tablename__ = 'sdll_umpire_assignments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'), nullable=False)
    umpire_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=False)
    role = db.Column(db.Enum('plate', 'base', 'field'), nullable=False, default='plate')
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    assigned_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Relationships
    game = db.relationship('Game', backref=db.backref('umpire_assignments', lazy='dynamic'))
    umpire = db.relationship('User', foreign_keys=[umpire_id], backref=db.backref('umpire_games', lazy='dynamic'))
    assigner = db.relationship('User', foreign_keys=[assigned_by])

    # Unique constraint: same umpire can't have same role on same game
    __table_args__ = (
        db.UniqueConstraint('game_id', 'umpire_id', 'role', name='unique_umpire_assignment'),
    )

    def __repr__(self):
        return f'<UmpireAssignment {self.id}: umpire {self.umpire_id} as {self.role} on game {self.game_id}>'

    @classmethod
    def get_for_game(cls, game_id):
        """Get all umpire assignments for a game"""
        return cls.query.filter_by(game_id=game_id).order_by(cls.role).all()

    @classmethod
    def get_for_umpire(cls, umpire_id, future_only=False):
        """Get all game assignments for an umpire"""
        from app.models.game import Game

        query = cls.query.filter_by(umpire_id=umpire_id)

        if future_only:
            query = query.join(Game).filter(Game.game_date > datetime.utcnow())

        return query.join(Game).order_by(Game.game_date).all()

    @classmethod
    def get_umpires_for_date(cls, date):
        """Get all umpire assignments for a specific date"""
        from app.models.game import Game
        from sqlalchemy import func

        return cls.query.join(Game).filter(
            func.date(Game.game_date) == date
        ).order_by(Game.game_date).all()

    @classmethod
    def assign(cls, game_id, umpire_id, role='plate', assigned_by=None):
        """Create or update an umpire assignment"""
        # Check if assignment already exists
        existing = cls.query.filter_by(
            game_id=game_id,
            umpire_id=umpire_id,
            role=role
        ).first()

        if existing:
            return existing

        assignment = cls(
            game_id=game_id,
            umpire_id=umpire_id,
            role=role,
            assigned_by=assigned_by
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment

    @classmethod
    def remove(cls, game_id, umpire_id, role=None):
        """Remove an umpire assignment"""
        query = cls.query.filter_by(game_id=game_id, umpire_id=umpire_id)
        if role:
            query = query.filter_by(role=role)

        count = query.delete()
        db.session.commit()
        return count

    @classmethod
    def get_affected_by_game_change(cls, game_id):
        """Get umpire user IDs affected by changes to a game"""
        assignments = cls.query.filter_by(game_id=game_id).all()
        return [a.umpire_id for a in assignments]
