"""Pitching stats model - tracks pitch counts and pitching performance in post-game reports."""

from datetime import datetime
from app.extensions import db


class PitchingStats(db.Model):
    """Pitching statistics for a player in a post-game report.

    Used to track pitch counts for Little League compliance and
    player performance metrics. Each row represents one pitcher's
    performance in one game.
    """
    __tablename__ = 'sdll_pitching_stats'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('sdll_post_game_reports.id', ondelete='CASCADE'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('sdll_players.id'), nullable=False)

    # Core pitch tracking (required for Little League compliance)
    pitch_count = db.Column(db.SmallInteger, nullable=False, default=0)
    strikes = db.Column(db.SmallInteger)

    # Innings pitched (e.g., 2.1 = 2 and 1/3 innings)
    innings_pitched = db.Column(db.Numeric(3, 1))

    # Results against
    batters_faced = db.Column(db.SmallInteger)
    hits_allowed = db.Column(db.SmallInteger)
    walks = db.Column(db.SmallInteger)     # BB
    strikeouts = db.Column(db.SmallInteger)  # K

    # Runs
    runs_allowed = db.Column(db.SmallInteger)
    earned_runs = db.Column(db.SmallInteger)  # ER

    # Metadata
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    report = db.relationship('PostGameReport', backref=db.backref('pitching_stats', lazy='dynamic'))
    player = db.relationship('Player', backref=db.backref('pitching_stats', lazy='dynamic'))

    # Unique constraint enforced in DB
    __table_args__ = (
        db.UniqueConstraint('report_id', 'player_id', name='uq_pitching_report_player'),
    )

    def __repr__(self):
        return f'<PitchingStats report={self.report_id} player={self.player_id} pitches={self.pitch_count}>'

    @property
    def innings_pitched_display(self):
        """Display innings pitched in standard format (e.g., 2.1 -> '2.1')."""
        if self.innings_pitched is None:
            return '-'
        return str(float(self.innings_pitched))

    @property
    def stat_line(self):
        """Return a compact stat line like '45 P, 3.0 IP, 4 K, 2 BB'."""
        parts = [f'{self.pitch_count} P']
        if self.innings_pitched is not None:
            parts.append(f'{float(self.innings_pitched)} IP')
        if self.strikeouts is not None:
            parts.append(f'{self.strikeouts} K')
        if self.walks is not None:
            parts.append(f'{self.walks} BB')
        return ', '.join(parts)

    @classmethod
    def get_for_report(cls, report_id):
        """Get all pitching stats for a specific report."""
        return cls.query.filter_by(report_id=report_id).all()

    @classmethod
    def get_for_player(cls, player_id, limit=None):
        """Get pitching stats history for a player, most recent first."""
        query = cls.query.filter_by(player_id=player_id).order_by(cls.created_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    @classmethod
    def get_recent_for_player(cls, player_id, days=7):
        """Get player's pitching stats from the last N days."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        return cls.query.filter(
            cls.player_id == player_id,
            cls.created_at >= cutoff
        ).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_or_create(cls, report_id, player_id):
        """Get existing stats or create new empty record."""
        stats = cls.query.filter_by(report_id=report_id, player_id=player_id).first()
        if not stats:
            stats = cls(report_id=report_id, player_id=player_id, pitch_count=0)
            db.session.add(stats)
        return stats
