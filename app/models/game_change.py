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

    # Pre-release acknowledgment - changes before schedule release don't show "Originally..."
    acknowledged = db.Column(db.SmallInteger, default=0)

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

    @classmethod
    def get_original_values(cls, game_id):
        """
        Get the original values for a game before any changes.

        Looks at the oldest NON-ACKNOWLEDGED change record and extracts the 'old' values
        to reconstruct what the game was originally scheduled as.

        Args:
            game_id: ID of the game

        Returns:
            Dictionary with original values (date, time, field) or None if no changes
        """
        # Get the oldest non-acknowledged change that has relevant info
        changes = cls.query.filter_by(game_id=game_id, acknowledged=0).filter(
            cls.change_type.in_(['update', 'reschedule'])
        ).order_by(cls.changed_at.asc()).all()

        if not changes:
            return None

        # Build original values from the oldest changes
        original = {}

        for change in changes:
            changes_dict = change.changes_dict
            if not changes_dict:
                continue

            # For each field, take the oldest 'old' value we find
            for field in ['date', 'time', 'field', 'location']:
                if field in changes_dict and field not in original:
                    old_val = changes_dict[field].get('old')
                    if old_val:
                        # Normalize 'location' to 'field'
                        key = 'field' if field == 'location' else field
                        original[key] = old_val

        return original if original else None

    @classmethod
    def get_change_display(cls, game_id, current_game=None):
        """
        Get a human-readable string describing relevant game changes.

        Logic:
        - If changes are more than 24 hours apart, each is considered "communicated"
        - If the most recent change was > 24 hours after the previous one, show
          "Changed from [previous value]" even if current == original
        - If changes are within 24 hours, collapse them and only compare to original

        Args:
            game_id: ID of the game
            current_game: Game object to compare against

        Returns:
            String like "Originally Sep 15 at 5:30 PM" or "Changed from 6:00 PM" or None
        """
        from datetime import timedelta

        # Get all non-acknowledged changes ordered newest first
        changes = cls.query.filter_by(game_id=game_id, acknowledged=0).filter(
            cls.change_type.in_(['update', 'reschedule'])
        ).order_by(cls.changed_at.desc()).all()

        if not changes:
            return None

        # Check if most recent change was > 24 hours after previous change
        if len(changes) >= 2:
            most_recent = changes[0]
            previous = changes[1]
            time_gap = most_recent.changed_at - previous.changed_at

            if time_gap > timedelta(hours=24):
                # The previous value was "communicated" - show what changed from
                prev_values = most_recent.changes_dict or {}
                return cls._format_changed_from(prev_values)

        # Fall back to comparing current to original
        return cls._get_original_display_internal(game_id, current_game)

    @classmethod
    def _format_changed_from(cls, changes_dict):
        """Format a 'Changed from...' message based on the old values in a change."""
        from datetime import datetime as dt

        parts = []

        # Get the 'old' values from the most recent change
        if 'date' in changes_dict:
            old_date = changes_dict['date'].get('old')
            if old_date:
                try:
                    d = dt.strptime(old_date, '%Y-%m-%d')
                    parts.append(d.strftime('%b %d'))
                except (ValueError, TypeError):
                    pass

        if 'time' in changes_dict:
            old_time = changes_dict['time'].get('old')
            if old_time:
                try:
                    t = dt.strptime(old_time, '%H:%M')
                    parts.append(f"at {t.strftime('%I:%M %p').lstrip('0')}")
                except (ValueError, TypeError):
                    pass

        for field_key in ['field', 'location']:
            if field_key in changes_dict:
                old_field = changes_dict[field_key].get('old')
                if old_field:
                    parts.append(f"at {old_field}")
                    break

        if not parts:
            return None

        return "Changed from " + " ".join(parts)

    @classmethod
    def _get_original_display_internal(cls, game_id, current_game=None):
        """Internal method to get original display, comparing to current game."""
        original = cls.get_original_values(game_id)
        if not original:
            return None

        # If we have the current game, compare and skip if values match
        if current_game:
            current_date = current_game.game_date.strftime('%Y-%m-%d') if current_game.game_date else None
            current_time = current_game.game_date.strftime('%H:%M') if current_game.game_date else None
            current_field = current_game.field_name or ''  # Use field_name property

            # Check if any original value differs from current
            has_diff = False
            if 'date' in original and original['date'] != current_date:
                has_diff = True
            if 'time' in original and original['time'] != current_time:
                has_diff = True
            if 'field' in original and original['field'] != current_field:
                has_diff = True

            if not has_diff:
                return None  # Game is back to original, no message needed

        parts = []

        # Format date
        if 'date' in original:
            try:
                from datetime import datetime
                d = datetime.strptime(original['date'], '%Y-%m-%d')
                parts.append(d.strftime('%b %d'))
            except (ValueError, TypeError):
                pass

        # Format time
        if 'time' in original:
            try:
                from datetime import datetime
                t = datetime.strptime(original['time'], '%H:%M')
                parts.append(f"at {t.strftime('%I:%M %p').lstrip('0')}")
            except (ValueError, TypeError):
                pass

        # Add field
        if 'field' in original:
            parts.append(f"at {original['field']}")

        if not parts:
            return None

        return "Originally " + " ".join(parts)

    @classmethod
    def get_original_display(cls, game_id, current_game=None):
        """
        Get a human-readable string describing game schedule changes.

        This is the main entry point. It handles:
        - Changes within 24 hours: collapsed, only shows if current != original
        - Changes > 24 hours apart: shows "Changed from..." for communicated values

        Args:
            game_id: ID of the game
            current_game: Optional Game object to compare against

        Returns:
            String like "Originally Sep 15 at 5:30 PM" or "Changed from 6:00 PM" or None
        """
        return cls.get_change_display(game_id, current_game)

    @classmethod
    def get_original_display_batch(cls, games):
        """
        Get original display strings for multiple games in a single query.

        This avoids N+1 queries when displaying schedules with many games.

        Args:
            games: List of Game objects

        Returns:
            Dict of {game_id: original_display_string} for games that have changes
        """
        from datetime import timedelta
        from collections import defaultdict

        if not games:
            return {}

        game_ids = [g.ID for g in games]
        game_lookup = {g.ID: g for g in games}

        # Fetch all non-acknowledged changes for these games in one query
        all_changes = cls.query.filter(
            cls.game_id.in_(game_ids),
            cls.acknowledged == 0,
            cls.change_type.in_(['update', 'reschedule'])
        ).order_by(cls.game_id, cls.changed_at.desc()).all()

        # Group changes by game_id
        changes_by_game = defaultdict(list)
        for change in all_changes:
            changes_by_game[change.game_id].append(change)

        # Process each game's changes
        result = {}
        for game_id, changes in changes_by_game.items():
            if not changes:
                continue

            current_game = game_lookup.get(game_id)

            # Check if most recent change was > 24 hours after previous change
            if len(changes) >= 2:
                most_recent = changes[0]
                previous = changes[1]
                time_gap = most_recent.changed_at - previous.changed_at

                if time_gap > timedelta(hours=24):
                    # The previous value was "communicated" - show what changed from
                    prev_values = most_recent.changes_dict or {}
                    display = cls._format_changed_from(prev_values)
                    if display:
                        result[game_id] = display
                    continue

            # Fall back to comparing current to original
            display = cls._get_original_display_internal_from_changes(changes, current_game)
            if display:
                result[game_id] = display

        return result

    @classmethod
    def _get_original_display_internal_from_changes(cls, changes, current_game):
        """
        Helper to compute original display from pre-fetched changes.
        """
        if not changes:
            return None

        # Build original values from the oldest changes
        original = {}
        for change in reversed(changes):  # Process oldest first
            changes_dict = change.changes_dict
            if not changes_dict:
                continue

            for field in ['date', 'time', 'field', 'location']:
                if field in changes_dict and field not in original:
                    old_val = changes_dict[field].get('old')
                    if old_val:
                        key = 'field' if field == 'location' else field
                        original[key] = old_val

        if not original:
            return None

        # Compare to current - if same, no need to show
        if current_game:
            current_date = current_game.game_date.strftime('%Y-%m-%d') if current_game.game_date else None
            current_time = current_game.game_date.strftime('%H:%M') if current_game.game_date else None
            current_field = current_game.field_name

            matches_current = True
            if 'date' in original and original['date'] != current_date:
                matches_current = False
            if 'time' in original and original['time'] != current_time:
                matches_current = False
            if 'field' in original and original['field'] != current_field:
                matches_current = False

            if matches_current:
                return None

        return cls._format_original_values(original)

    @classmethod
    def acknowledge_all_for_season(cls, year, is_spring):
        """
        Mark all changes for a season as acknowledged.

        This is called when the schedule is officially released.
        Acknowledged changes won't show "Originally..." on public pages.

        Args:
            year: Season year
            is_spring: 1 for spring, 0 for fall

        Returns:
            Number of changes acknowledged
        """
        from app.models.game import Game

        # Get all game IDs for this season
        game_ids = db.session.query(Game.ID).filter(
            Game.year == year,
            Game.is_spring == is_spring
        ).all()
        game_ids = [g[0] for g in game_ids]

        if not game_ids:
            return 0

        # Update all non-acknowledged changes for these games
        count = cls.query.filter(
            cls.game_id.in_(game_ids),
            cls.acknowledged == 0
        ).update({cls.acknowledged: 1}, synchronize_session=False)

        db.session.commit()
        return count
