"""GameChange model - tracks all modifications to games"""

import json
from datetime import datetime
from app.extensions import db


class GameChange(db.Model):
    """Logs all changes to games for audit trail and notifications"""
    __tablename__ = 'sdll_game_changes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'), nullable=False)
    changed_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    change_type = db.Column(db.Enum('create', 'update', 'cancel', 'reschedule', 'delete'), nullable=False)

    # What changed
    field_changed = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)

    # All changes in one update as JSON
    changes_json = db.Column(db.JSON)

    # Optional reason/notes
    reason = db.Column(db.Text)

    # Denormalized for easier querying
    game_date = db.Column(db.Date)
    league = db.Column(db.String(50))
    home_team_id = db.Column(db.BigInteger)
    away_team_id = db.Column(db.BigInteger)

    # Relationships
    game = db.relationship('Game', backref=db.backref('changes', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('game_changes', lazy='dynamic'))

    def __repr__(self):
        return f'<GameChange {self.id}: {self.change_type} on game {self.game_id}>'

    @property
    def changes_dict(self):
        """Parse changes_json into a dictionary"""
        if self.changes_json:
            if isinstance(self.changes_json, dict):
                return self.changes_json
            return json.loads(self.changes_json)
        return {}

    def describe_change(self):
        """Return a human-readable description of the change"""
        if self.change_type == 'create':
            return 'Game created'
        elif self.change_type == 'delete':
            return 'Game deleted'
        elif self.change_type == 'cancel':
            return 'Game cancelled'
        elif self.change_type == 'reschedule':
            changes = self.changes_dict
            if 'date' in changes:
                old = changes['date'].get('old', 'unknown')
                new = changes['date'].get('new', 'unknown')
                return f'Rescheduled from {old} to {new}'
            return 'Game rescheduled'
        elif self.change_type == 'update':
            changes = self.changes_dict
            if not changes:
                return 'Game updated'

            descriptions = []
            field_labels = {
                'date': 'Date',
                'time': 'Time',
                'field': 'Field',
                'location': 'Field',
                'status': 'Status',
                'home_team': 'Home team',
                'away_team': 'Away team',
                'is_scrimmage': 'Scrimmage flag',
                'no_time_limit': 'Time limit',
                'game_type': 'Game type'
            }
            for field, change in changes.items():
                label = field_labels.get(field, field)
                if isinstance(change, dict):
                    old = change.get('old', 'none')
                    new = change.get('new', 'none')
                    descriptions.append(f'{label}: {old} -> {new}')
                else:
                    descriptions.append(f'{label} changed')

            return '; '.join(descriptions) if descriptions else 'Game updated'

        return 'Unknown change'

    @classmethod
    def get_for_game(cls, game_id):
        """Get all changes for a specific game, newest first"""
        return cls.query.filter_by(game_id=game_id).order_by(cls.changed_at.desc()).all()

    @classmethod
    def get_recent(cls, days=7, league=None, change_type=None, limit=100):
        """Get recent changes with optional filters"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = cls.query.filter(cls.changed_at >= cutoff)

        if league:
            query = query.filter_by(league=league)
        if change_type:
            query = query.filter_by(change_type=change_type)

        return query.order_by(cls.changed_at.desc()).limit(limit).all()

    @classmethod
    def get_by_user(cls, user_id, limit=100):
        """Get changes made by a specific user"""
        return cls.query.filter_by(changed_by=user_id).order_by(cls.changed_at.desc()).limit(limit).all()
