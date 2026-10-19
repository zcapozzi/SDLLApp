"""UmpireSurveySend model - tracks survey email sends to umpires."""

from datetime import datetime
from app.extensions import db


class UmpireSurveySend(db.Model):
    """Tracks when survey emails were sent to umpires.

    Each record represents one email send to one umpire for a season.
    Multiple sends are allowed (for resends).
    """
    __tablename__ = 'sdll_umpire_survey_sends'

    id = db.Column(db.Integer, primary_key=True)

    # Who received the email
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id'), nullable=False)

    # Which season's survey
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'), nullable=False)

    # When and by whom
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sent_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Relationships
    umpire_profile = db.relationship('UmpireProfile', backref='survey_sends')
    org_season = db.relationship('OrgSeason', backref='survey_sends')
    sent_by = db.relationship('User', backref='survey_sends_initiated')

    def __repr__(self):
        return f'<UmpireSurveySend {self.id}: profile={self.umpire_profile_id} sent={self.sent_at}>'

    @classmethod
    def get_sent_umpire_ids(cls, org_season_id):
        """Get set of umpire_profile_ids that have been sent the survey for this season."""
        results = cls.query.filter_by(org_season_id=org_season_id).with_entities(
            cls.umpire_profile_id
        ).distinct().all()
        return {r[0] for r in results}

    @classmethod
    def get_send_history(cls, umpire_profile_id, org_season_id):
        """Get all sends for an umpire in a season, ordered by date."""
        return cls.query.filter_by(
            umpire_profile_id=umpire_profile_id,
            org_season_id=org_season_id
        ).order_by(cls.sent_at.desc()).all()

    @classmethod
    def record_send(cls, umpire_profile_id, org_season_id, sent_by_user_id=None):
        """Record that a survey email was sent."""
        send = cls(
            umpire_profile_id=umpire_profile_id,
            org_season_id=org_season_id,
            sent_by_user_id=sent_by_user_id
        )
        db.session.add(send)
        return send
