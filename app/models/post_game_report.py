"""Post-Game Report model - captures coach submissions after games."""

from datetime import datetime, timedelta
from app.extensions import db


class PostGameReport(db.Model):
    """Post-game report submitted by a coach for their team.

    Each team submits their own report for a game. Reports include:
    - Score (from team's perspective)
    - Innings played
    - Umpire evaluation
    - Optional "not played" status with reason
    """
    __tablename__ = 'sdll_post_game_reports'

    # Status values
    STATUS_PENDING = 'pending'
    STATUS_SUBMITTED = 'submitted'
    STATUS_NOT_PLAYED = 'not_played'

    # Umpire rating values
    RATING_EXCELLENT = 'excellent'
    RATING_GOOD = 'good'
    RATING_OK = 'ok'
    RATING_POOR = 'poor'
    RATINGS = [RATING_EXCELLENT, RATING_GOOD, RATING_OK, RATING_POOR]
    RATING_LABELS = {
        RATING_EXCELLENT: 'Excellent',
        RATING_GOOD: 'Good',
        RATING_OK: 'OK',
        RATING_POOR: 'Poor'
    }

    # Not played reason values
    REASON_RAINOUT = 'rainout'
    REASON_CANCELLED = 'cancelled'
    REASON_FORFEIT = 'forfeit'
    REASON_OTHER = 'other'
    NOT_PLAYED_REASONS = [REASON_RAINOUT, REASON_CANCELLED, REASON_FORFEIT, REASON_OTHER]
    REASON_LABELS = {
        REASON_RAINOUT: 'Rainout',
        REASON_CANCELLED: 'Cancelled',
        REASON_FORFEIT: 'Forfeit',
        REASON_OTHER: 'Other'
    }

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.BigInteger, db.ForeignKey('sdll_games.ID', ondelete='CASCADE'),
                        nullable=False, index=True)
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID', ondelete='CASCADE'),
                        nullable=False, index=True)

    # Status: pending, submitted, not_played
    status = db.Column(db.String(20), default=STATUS_PENDING, index=True)

    # Score (from this team's perspective)
    our_score = db.Column(db.SmallInteger)
    opponent_score = db.Column(db.SmallInteger)

    # Innings
    innings_batted = db.Column(db.SmallInteger)
    innings_fielded = db.Column(db.SmallInteger)

    # Umpire evaluation
    umpire_name = db.Column(db.String(100))
    umpire_rating = db.Column(db.String(20))  # excellent, good, ok, poor
    umpire_comments = db.Column(db.Text)

    # Not played tracking
    not_played_reason = db.Column(db.String(50))  # rainout, cancelled, forfeit, other
    not_played_notes = db.Column(db.Text)

    # Submission tracking
    submitted_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID', ondelete='SET NULL'))
    submitted_by_role = db.Column(db.String(20))  # head or assistant
    submitted_at = db.Column(db.DateTime)

    # Email tracking
    email_sent_at = db.Column(db.DateTime)
    email_opened_at = db.Column(db.DateTime)

    # Flagged for review (unusual rating pattern)
    is_flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(200))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    game = db.relationship('Game', backref=db.backref('post_game_reports', lazy='dynamic'))
    team = db.relationship('TeamSeason', backref=db.backref('post_game_reports', lazy='dynamic'))
    submitted_by = db.relationship('User', backref=db.backref('submitted_reports', lazy='dynamic'))

    # Unique constraint: one report per team per game
    __table_args__ = (
        db.UniqueConstraint('game_id', 'team_id', name='uq_postgame_game_team'),
    )

    def __repr__(self):
        return f'<PostGameReport {self.id}: game={self.game_id} team={self.team_id} status={self.status}>'

    @property
    def is_editable(self):
        """Editable within 24 hours of submission."""
        if self.status != self.STATUS_SUBMITTED or not self.submitted_at:
            return True  # Pending reports are always editable
        return datetime.utcnow() < self.submitted_at + timedelta(hours=24)

    @property
    def edit_window_expired(self):
        """Check if edit window has expired for submitted reports."""
        if self.status != self.STATUS_SUBMITTED or not self.submitted_at:
            return False
        return datetime.utcnow() >= self.submitted_at + timedelta(hours=24)

    @property
    def rating_display(self):
        """Get human-readable rating label."""
        return self.RATING_LABELS.get(self.umpire_rating, self.umpire_rating)

    @property
    def not_played_reason_display(self):
        """Get human-readable not-played reason label."""
        return self.REASON_LABELS.get(self.not_played_reason, self.not_played_reason)

    @property
    def is_home_team(self):
        """Check if this report's team is the home team for the game."""
        if self.game:
            return self.team_id == self.game.home_ID
        return False

    @property
    def opponent_team_id(self):
        """Get the opponent team's ID."""
        if not self.game:
            return None
        if self.team_id == self.game.home_ID:
            return self.game.away_ID
        return self.game.home_ID

    @classmethod
    def get_or_create(cls, game_id, team_id):
        """Get existing report or create a pending one."""
        report = cls.query.filter_by(game_id=game_id, team_id=team_id).first()
        if not report:
            report = cls(
                game_id=game_id,
                team_id=team_id,
                status=cls.STATUS_PENDING
            )
            db.session.add(report)
            db.session.commit()
        return report

    @classmethod
    def get_for_game(cls, game_id):
        """Get all reports for a game (both teams)."""
        return cls.query.filter_by(game_id=game_id).all()

    @classmethod
    def get_pending_for_coach(cls, user_id, year=None, is_spring=None):
        """Get pending reports for games where user is a coach.

        Returns games where the coach hasn't submitted a report yet.
        """
        from app.models.coach import CoachSeason
        from app.models.game import Game

        # Get teams this user coaches
        coach_assignments = CoachSeason.query.filter_by(coach_id=user_id).all()
        if not coach_assignments:
            # Try finding by user_id through CoachUser
            from app.models.coach import CoachUser
            coach_user = CoachUser.get_by_user(user_id)
            if coach_user:
                coach_assignments = CoachSeason.query.filter_by(coach_id=coach_user.id).all()

        if not coach_assignments:
            return []

        team_ids = [a.team_id for a in coach_assignments]

        # Find completed games for these teams
        query = db.session.query(Game, cls).outerjoin(
            cls,
            db.and_(
                cls.game_id == Game.ID,
                cls.team_id.in_(team_ids)
            )
        ).filter(
            Game.active == 1,
            Game.game_date < datetime.utcnow(),
            db.or_(
                Game.home_ID.in_(team_ids),
                Game.away_ID.in_(team_ids)
            )
        )

        if year is not None:
            query = query.filter(Game.year == year)
        if is_spring is not None:
            query = query.filter(Game.is_spring == is_spring)

        results = query.order_by(Game.game_date.desc()).all()

        # Filter to games without submitted reports
        pending_games = []
        for game, report in results:
            # Determine which team the coach is on for this game
            coach_team_id = None
            for team_id in team_ids:
                if team_id == game.home_ID or team_id == game.away_ID:
                    coach_team_id = team_id
                    break

            if coach_team_id:
                # Check if there's a report for this team
                existing = cls.query.filter_by(
                    game_id=game.ID,
                    team_id=coach_team_id
                ).first()

                if not existing or existing.status == cls.STATUS_PENDING:
                    pending_games.append({
                        'game': game,
                        'team_id': coach_team_id,
                        'report': existing
                    })

        return pending_games

    @classmethod
    def get_by_umpire(cls, umpire_name=None, year=None, is_spring=None):
        """Get reports with umpire evaluations, optionally filtered by umpire name."""
        from app.models.game import Game

        query = cls.query.join(Game).filter(
            cls.status == cls.STATUS_SUBMITTED,
            cls.umpire_name.isnot(None)
        )

        if umpire_name:
            query = query.filter(cls.umpire_name.ilike(f'%{umpire_name}%'))

        if year is not None:
            query = query.filter(Game.year == year)
        if is_spring is not None:
            query = query.filter(Game.is_spring == is_spring)

        return query.order_by(Game.game_date.desc()).all()

    @classmethod
    def get_flagged_reports(cls, year=None, is_spring=None):
        """Get reports flagged for review."""
        from app.models.game import Game

        query = cls.query.join(Game).filter(cls.is_flagged == True)

        if year is not None:
            query = query.filter(Game.year == year)
        if is_spring is not None:
            query = query.filter(Game.is_spring == is_spring)

        return query.order_by(Game.game_date.desc()).all()

    @classmethod
    def get_umpire_summary(cls, year=None, is_spring=None):
        """Get aggregated umpire ratings.

        Returns dict: {umpire_name: {'count': N, 'avg_rating': X, 'ratings': {...}}}
        """
        from app.models.game import Game
        from sqlalchemy import func

        query = db.session.query(
            cls.umpire_name,
            cls.umpire_rating,
            func.count(cls.id).label('count')
        ).join(Game).filter(
            cls.status == cls.STATUS_SUBMITTED,
            cls.umpire_name.isnot(None),
            cls.umpire_rating.isnot(None)
        )

        if year is not None:
            query = query.filter(Game.year == year)
        if is_spring is not None:
            query = query.filter(Game.is_spring == is_spring)

        results = query.group_by(cls.umpire_name, cls.umpire_rating).all()

        # Convert to nested dict
        summary = {}
        rating_values = {
            cls.RATING_EXCELLENT: 4,
            cls.RATING_GOOD: 3,
            cls.RATING_OK: 2,
            cls.RATING_POOR: 1
        }

        for umpire_name, rating, count in results:
            if umpire_name not in summary:
                summary[umpire_name] = {
                    'count': 0,
                    'total_value': 0,
                    'ratings': {r: 0 for r in cls.RATINGS}
                }
            summary[umpire_name]['count'] += count
            summary[umpire_name]['ratings'][rating] = count
            summary[umpire_name]['total_value'] += count * rating_values.get(rating, 0)

        # Calculate average ratings
        for umpire_name, data in summary.items():
            if data['count'] > 0:
                data['avg_rating'] = data['total_value'] / data['count']
                # Convert to label
                if data['avg_rating'] >= 3.5:
                    data['avg_label'] = 'Excellent'
                elif data['avg_rating'] >= 2.5:
                    data['avg_label'] = 'Good'
                elif data['avg_rating'] >= 1.5:
                    data['avg_label'] = 'OK'
                else:
                    data['avg_label'] = 'Poor'
            else:
                data['avg_rating'] = 0
                data['avg_label'] = 'N/A'

        return summary

    @classmethod
    def get_completion_stats(cls, year, is_spring, league=None):
        """Get report completion statistics.

        Returns dict with counts of pending, submitted, and not_played.
        """
        from app.models.game import Game
        from sqlalchemy import func

        # Get all completed games count
        games_query = db.session.query(func.count(Game.ID)).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.active == 1,
            Game.game_date < datetime.utcnow(),
            Game.game_type.in_(['regular', 'playoff']),
            Game.home_ID.isnot(None),
            Game.away_ID.isnot(None)
        )

        if league:
            games_query = games_query.filter(Game.league == league)

        total_games = games_query.scalar() or 0
        # Each game has 2 potential reports (one per team)
        total_expected = total_games * 2

        # Get report counts by status
        reports_query = db.session.query(
            cls.status,
            func.count(cls.id)
        ).join(Game).filter(
            Game.year == year,
            Game.is_spring == is_spring,
            Game.active == 1
        )

        if league:
            reports_query = reports_query.filter(Game.league == league)

        report_counts = dict(reports_query.group_by(cls.status).all())

        return {
            'total_games': total_games,
            'total_expected_reports': total_expected,
            'submitted': report_counts.get(cls.STATUS_SUBMITTED, 0),
            'not_played': report_counts.get(cls.STATUS_NOT_PLAYED, 0),
            'pending': report_counts.get(cls.STATUS_PENDING, 0),
            'not_started': total_expected - sum(report_counts.values())
        }
