"""Service for logging game changes and queueing notifications"""

import json
from datetime import datetime
from app.extensions import db
from app.models.game import Game
from app.models.game_change import GameChange
from app.models.notification_queue import NotificationQueue
from app.models.umpire_assignment import UmpireAssignment
from app.models.team import TeamSeason
from app.models.user import User


class GameChangeService:
    """Handles logging game changes and queueing notifications"""

    @staticmethod
    def log_change(game_id, user_id, change_type, changes_dict=None, reason=None,
                   field_changed=None, old_value=None, new_value=None):
        """
        Log a game change to the database.

        Args:
            game_id: ID of the game that was changed
            user_id: ID of the user who made the change
            change_type: One of 'create', 'update', 'cancel', 'reschedule', 'delete'
            changes_dict: Dictionary of changes (e.g., {'date': {'old': '2026-09-01', 'new': '2026-09-02'}})
            reason: Optional reason/notes for the change
            field_changed: Optional single field name if only one field changed
            old_value: Optional old value (for single field changes)
            new_value: Optional new value (for single field changes)

        Returns:
            The created GameChange object
        """
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        change = GameChange(
            game_id=game_id,
            changed_by=user_id,
            changed_at=datetime.utcnow(),
            change_type=change_type,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            changes_json=changes_dict,
            reason=reason,
            game_date=game.game_date.date() if game.game_date else None,
            league=game.league,
            home_team_id=game.home_ID,
            away_team_id=game.away_ID
        )
        db.session.add(change)
        db.session.commit()

        return change

    @staticmethod
    def log_game_move(game_id, user_id, old_field=None, new_field=None,
                      old_time=None, new_time=None, old_date=None, new_date=None,
                      reason=None):
        """
        Log a game move (field/time/date change) from drag-and-drop.

        Returns:
            The created GameChange object
        """
        changes = {}

        if old_field != new_field and (old_field or new_field):
            changes['field'] = {'old': old_field, 'new': new_field}

        if old_time != new_time and (old_time or new_time):
            changes['time'] = {'old': old_time, 'new': new_time}

        if old_date != new_date and (old_date or new_date):
            changes['date'] = {'old': old_date, 'new': new_date}

        change_type = 'reschedule' if 'date' in changes else 'update'

        return GameChangeService.log_change(
            game_id=game_id,
            user_id=user_id,
            change_type=change_type,
            changes_dict=changes,
            reason=reason
        )

    @staticmethod
    def log_game_cancel(game_id, user_id, reason=None):
        """Log a game cancellation"""
        return GameChangeService.log_change(
            game_id=game_id,
            user_id=user_id,
            change_type='cancel',
            changes_dict={'status': {'old': 'scheduled', 'new': 'cancelled'}},
            reason=reason
        )

    @staticmethod
    def capture_old_values(game):
        """
        Capture current game values before an update.

        Args:
            game: Game object

        Returns:
            Dictionary of current values
        """
        return {
            'date': game.game_date.strftime('%Y-%m-%d') if game.game_date else None,
            'time': game.game_date.strftime('%H:%M') if game.game_date else None,
            'field': game.location,
            'status': game.status,
            'home_team': game.home_ID,
            'away_team': game.away_ID,
            'game_type': game.game_type,
            'is_scrimmage': game.is_scrimmage,
            'no_time_limit': game.no_time_limit
        }

    @staticmethod
    def compare_and_log(game, old_values, user_id, reason=None):
        """
        Compare current game values to old values and log changes.

        Args:
            game: Game object (after update)
            old_values: Dictionary from capture_old_values()
            user_id: ID of user making the change
            reason: Optional reason for the change

        Returns:
            GameChange object if there were changes, None otherwise
        """
        new_values = {
            'date': game.game_date.strftime('%Y-%m-%d') if game.game_date else None,
            'time': game.game_date.strftime('%H:%M') if game.game_date else None,
            'field': game.location,
            'status': game.status,
            'home_team': game.home_ID,
            'away_team': game.away_ID,
            'game_type': game.game_type,
            'is_scrimmage': game.is_scrimmage,
            'no_time_limit': game.no_time_limit
        }

        changes = {}
        for key, old_val in old_values.items():
            new_val = new_values.get(key)
            if old_val != new_val:
                changes[key] = {'old': old_val, 'new': new_val}

        if not changes:
            return None

        # Determine change type
        if 'status' in changes and changes['status']['new'] == 'cancelled':
            change_type = 'cancel'
        elif 'date' in changes:
            change_type = 'reschedule'
        else:
            change_type = 'update'

        return GameChangeService.log_change(
            game_id=game.ID,
            user_id=user_id,
            change_type=change_type,
            changes_dict=changes,
            reason=reason
        )

    @staticmethod
    def queue_notifications_for_change(change, game):
        """
        Queue notifications for all affected parties after a game change.

        Args:
            change: GameChange object
            game: Game object

        Returns:
            Number of notifications queued
        """
        notifications_queued = 0

        # Queue for coaches of both teams
        # Note: coach_email/coach_name will be available when coach management is implemented
        for team_id in [game.home_ID, game.away_ID]:
            if team_id:
                team = TeamSeason.query.get(team_id)
                # Check for coach attributes (not yet implemented on TeamSeason)
                coach_email = getattr(team, 'coach_email', None) if team else None
                if coach_email:
                    try:
                        NotificationQueue.create_for_change(
                            change=change,
                            game=game,
                            recipient_type='coach',
                            recipient_email=coach_email,
                            recipient_name=getattr(team, 'coach_name', None),
                            recipient_id=None  # Coaches aren't necessarily users
                        )
                        notifications_queued += 1
                    except Exception:
                        pass  # Don't fail if notification creation fails

        # Queue for assigned umpires
        umpire_ids = UmpireAssignment.get_affected_by_game_change(game.ID)
        for umpire_id in umpire_ids:
            umpire = User.query.get(umpire_id)
            if umpire and umpire.email:
                try:
                    NotificationQueue.create_for_change(
                        change=change,
                        game=game,
                        recipient_type='umpire',
                        recipient_email=umpire.decrypted_email,
                        recipient_name=umpire.name,
                        recipient_id=umpire.user_id
                    )
                    notifications_queued += 1
                except Exception:
                    pass

        # Queue for admins (users with admin or scheduler role)
        admins = User.query.filter(User.role.in_(['admin', 'scheduler'])).all()
        for admin in admins:
            if admin.email:
                try:
                    NotificationQueue.create_for_change(
                        change=change,
                        game=game,
                        recipient_type='admin',
                        recipient_email=admin.decrypted_email,
                        recipient_name=admin.name,
                        recipient_id=admin.user_id
                    )
                    notifications_queued += 1
                except Exception:
                    pass

        return notifications_queued

    @staticmethod
    def move_game(game_id, user_id, new_field=None, new_time=None, new_date=None, reason=None):
        """
        Move a game to a new field/time/date and log the change.

        Args:
            game_id: ID of the game to move
            user_id: ID of user making the change
            new_field: New field/location (optional)
            new_time: New time as 'HH:MM' string (optional)
            new_date: New date as 'YYYY-MM-DD' string (optional)
            reason: Optional reason for the move

        Returns:
            Tuple of (updated Game, GameChange, notifications_queued)
        """
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        old_values = GameChangeService.capture_old_values(game)

        # Apply changes
        if new_field is not None:
            game.location = new_field

        if new_date is not None or new_time is not None:
            # Parse existing date/time
            if game.game_date:
                current_date = game.game_date.date()
                current_time = game.game_date.time()
            else:
                current_date = None
                current_time = None

            # Apply new date if provided
            if new_date is not None:
                from datetime import date as date_type
                if isinstance(new_date, str):
                    current_date = datetime.strptime(new_date, '%Y-%m-%d').date()
                else:
                    current_date = new_date

            # Apply new time if provided
            if new_time is not None:
                from datetime import time as time_type
                if isinstance(new_time, str):
                    parts = new_time.split(':')
                    current_time = datetime.strptime(new_time, '%H:%M').time()

            # Combine date and time
            if current_date and current_time:
                game.game_date = datetime.combine(current_date, current_time)
            elif current_date:
                game.game_date = datetime.combine(current_date, datetime.min.time())

        db.session.commit()

        # Log the change
        change = GameChangeService.compare_and_log(game, old_values, user_id, reason)

        # Queue notifications if there was a change
        notifications_queued = 0
        if change:
            notifications_queued = GameChangeService.queue_notifications_for_change(change, game)

        return game, change, notifications_queued

    @staticmethod
    def cancel_game(game_id, user_id, reason=None):
        """
        Cancel a game and log the change.

        Args:
            game_id: ID of the game to cancel
            user_id: ID of user making the change
            reason: Optional reason for cancellation

        Returns:
            Tuple of (updated Game, GameChange, notifications_queued)
        """
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        old_status = game.status
        game.status = 'cancelled'
        db.session.commit()

        change = GameChangeService.log_change(
            game_id=game_id,
            user_id=user_id,
            change_type='cancel',
            changes_dict={'status': {'old': old_status, 'new': 'cancelled'}},
            reason=reason
        )

        notifications_queued = GameChangeService.queue_notifications_for_change(change, game)

        return game, change, notifications_queued
