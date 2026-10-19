"""UmpireSurvey model - end of season umpire feedback surveys."""

from datetime import datetime
from app.extensions import db


class UmpireSurveyResponse(db.Model):
    """End-of-season survey response from an umpire.

    Captures feedback about their season experience:
    - Whether they wanted more games
    - Whether they want to return next season
    - Open-ended feedback
    """
    __tablename__ = 'sdll_umpire_survey_responses'

    id = db.Column(db.Integer, primary_key=True)

    # Who submitted
    umpire_profile_id = db.Column(db.Integer, db.ForeignKey('sdll_umpire_profiles.id'), nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))

    # Which season this survey is for
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'), nullable=False)

    # Survey responses
    wanted_more_games = db.Column(db.Boolean)  # Would you have liked to do more games?
    returning_next_season = db.Column(db.Boolean)  # Do you want to come back next season?
    feedback = db.Column(db.Text)  # Open-ended feedback

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    umpire_profile = db.relationship('UmpireProfile', backref='survey_responses')
    user = db.relationship('User', backref='umpire_survey_responses')
    org_season = db.relationship('OrgSeason', backref='umpire_surveys')

    def __repr__(self):
        return f'<UmpireSurveyResponse {self.id}: profile={self.umpire_profile_id} season={self.org_season_id}>'

    @classmethod
    def get_for_umpire_season(cls, umpire_profile_id, org_season_id):
        """Get existing survey response for an umpire and season."""
        return cls.query.filter_by(
            umpire_profile_id=umpire_profile_id,
            org_season_id=org_season_id
        ).first()

    @classmethod
    def has_responded(cls, umpire_profile_id, org_season_id):
        """Check if umpire has already responded for this season."""
        return cls.query.filter_by(
            umpire_profile_id=umpire_profile_id,
            org_season_id=org_season_id
        ).count() > 0

    @classmethod
    def get_season_summary(cls, org_season_id):
        """Get summary statistics for a season's survey responses."""
        responses = cls.query.filter_by(org_season_id=org_season_id).all()

        if not responses:
            return None

        total = len(responses)
        wanted_more = sum(1 for r in responses if r.wanted_more_games)
        returning = sum(1 for r in responses if r.returning_next_season)
        with_feedback = sum(1 for r in responses if r.feedback and r.feedback.strip())

        return {
            'total_responses': total,
            'wanted_more_games': wanted_more,
            'wanted_more_games_pct': round(wanted_more / total * 100) if total > 0 else 0,
            'returning_next_season': returning,
            'returning_next_season_pct': round(returning / total * 100) if total > 0 else 0,
            'with_feedback': with_feedback,
        }
