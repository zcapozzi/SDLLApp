"""OrgEvent model for organization-wide events, evaluations, signups, etc."""

from datetime import datetime, date, time
from app.extensions import db


class OrgEvent(db.Model):
    """Organization events that appear on team/division schedules.

    Events can be scoped to:
    - Entire organization (scope='org')
    - A sport (scope='sport', sport='baseball')
    - A league (scope='league', league='BB AA')
    - A specific team (scope='team', team_id=123)

    Events are included in ICS calendar feeds alongside games.
    """
    __tablename__ = 'sdll_org_events'

    id = db.Column(db.Integer, primary_key=True)

    # Event details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    event_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    location = db.Column(db.String(200))  # Field name or free text
    field_id = db.Column(db.BigInteger, db.ForeignKey('sdll_fields.ID'))  # Optional link to field
    url = db.Column(db.String(500))  # Optional link (signup form, registration, etc.)

    # Event type for display/filtering
    EVENT_TYPE_EVALUATION = 'evaluation'
    EVENT_TYPE_SIGNUP = 'signup'
    EVENT_TYPE_MEETING = 'meeting'
    EVENT_TYPE_CEREMONY = 'ceremony'
    EVENT_TYPE_PRACTICE = 'practice'  # League-wide practice like "Final Inning"
    EVENT_TYPE_OTHER = 'other'

    EVENT_TYPES = [
        (EVENT_TYPE_EVALUATION, 'Evaluation'),
        (EVENT_TYPE_SIGNUP, 'Sign-up / Registration'),
        (EVENT_TYPE_MEETING, 'Meeting'),
        (EVENT_TYPE_CEREMONY, 'Ceremony / Event'),
        (EVENT_TYPE_PRACTICE, 'League Practice'),
        (EVENT_TYPE_OTHER, 'Other'),
    ]

    event_type = db.Column(db.String(30), default=EVENT_TYPE_OTHER)

    # Scope determines who sees this event
    SCOPE_ORG = 'org'        # Everyone in the organization
    SCOPE_SPORT = 'sport'    # Everyone in a sport (baseball/softball)
    SCOPE_LEAGUE = 'league'  # Everyone in a specific league
    SCOPE_TEAM = 'team'      # Just one team

    SCOPES = [
        (SCOPE_ORG, 'Entire Organization'),
        (SCOPE_SPORT, 'Sport (Baseball or Softball)'),
        (SCOPE_LEAGUE, 'Specific League'),
        (SCOPE_TEAM, 'Specific Team'),
    ]

    scope = db.Column(db.String(20), default=SCOPE_ORG)
    sport = db.Column(db.String(20))  # 'baseball', 'softball', or null
    league = db.Column(db.String(50))  # League name or null
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_teams.ID'))

    # Season context
    year = db.Column(db.Integer, nullable=False)
    is_spring = db.Column(db.SmallInteger, nullable=False)  # 0=Fall, 1=Spring

    # Status
    STATUS_ACTIVE = 'active'
    STATUS_CANCELLED = 'cancelled'

    status = db.Column(db.String(20), default=STATUS_ACTIVE)
    active = db.Column(db.SmallInteger, default=1)

    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    field = db.relationship('Field', foreign_keys=[field_id])
    team = db.relationship('TeamSeason', foreign_keys=[team_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    def __repr__(self):
        return f'<OrgEvent {self.id}: {self.title} on {self.event_date}>'

    @property
    def event_type_display(self):
        """Get display name for event type."""
        for code, name in self.EVENT_TYPES:
            if code == self.event_type:
                return name
        return self.event_type

    @property
    def scope_display(self):
        """Get display name for scope."""
        for code, name in self.SCOPES:
            if code == self.scope:
                return name
        return self.scope

    @property
    def time_display(self):
        """Get formatted time range."""
        if not self.start_time:
            return 'TBD'

        start = self.start_time.strftime('%I:%M %p').lstrip('0')
        if self.end_time:
            end = self.end_time.strftime('%I:%M %p').lstrip('0')
            return f'{start} - {end}'
        return start

    @property
    def duration_minutes(self):
        """Calculate duration in minutes."""
        if not self.start_time or not self.end_time:
            return 60  # Default 1 hour

        start_dt = datetime.combine(date.today(), self.start_time)
        end_dt = datetime.combine(date.today(), self.end_time)
        return int((end_dt - start_dt).total_seconds() / 60)

    @property
    def scope_description(self):
        """Get human-readable scope description."""
        if self.scope == self.SCOPE_ORG:
            return 'All teams'
        elif self.scope == self.SCOPE_SPORT:
            return f'All {self.sport} teams'
        elif self.scope == self.SCOPE_LEAGUE:
            return f'{self.league} teams'
        elif self.scope == self.SCOPE_TEAM and self.team:
            return f'{self.team.scheduler_display_name} only'
        return 'Unknown'

    def applies_to_team(self, team):
        """Check if this event should appear on a team's schedule.

        Args:
            team: TeamSeason instance

        Returns:
            True if event should appear on team's schedule
        """
        if self.status != self.STATUS_ACTIVE or not self.active:
            return False

        # Must match season
        if self.year != team.year or self.is_spring != team.is_spring:
            return False

        if self.scope == self.SCOPE_ORG:
            return True

        if self.scope == self.SCOPE_SPORT:
            # Get team's sport from league
            from app.models.league import League
            league_obj = League.get_by_name(team.league)
            team_sport = league_obj.sport if league_obj else None
            return team_sport == self.sport

        if self.scope == self.SCOPE_LEAGUE:
            return team.league == self.league

        if self.scope == self.SCOPE_TEAM:
            return team.team_ID == self.team_id

        return False

    def applies_to_league(self, league_name, sport=None):
        """Check if this event should appear on a division/league schedule.

        Args:
            league_name: Name of the league
            sport: Sport of the league (optional, will look up if not provided)

        Returns:
            True if event should appear on league's schedule
        """
        if self.status != self.STATUS_ACTIVE or not self.active:
            return False

        if self.scope == self.SCOPE_ORG:
            return True

        if self.scope == self.SCOPE_SPORT:
            if not sport:
                from app.models.league import League
                league_obj = League.get_by_name(league_name)
                sport = league_obj.sport if league_obj else None
            return sport == self.sport

        if self.scope == self.SCOPE_LEAGUE:
            return league_name == self.league

        # Team-scoped events don't show on division schedules
        return False

    @classmethod
    def get_for_team(cls, team, include_cancelled=False):
        """Get all events that apply to a team's schedule.

        Args:
            team: TeamSeason instance
            include_cancelled: Include cancelled events

        Returns:
            List of OrgEvent instances
        """
        from app.models.league import League

        # Get team's sport
        league_obj = League.get_by_name(team.league)
        team_sport = league_obj.sport if league_obj else None

        query = cls.query.filter(
            cls.year == team.year,
            cls.is_spring == team.is_spring,
            cls.active == 1
        )

        if not include_cancelled:
            query = query.filter(cls.status == cls.STATUS_ACTIVE)

        # Filter by scope
        from sqlalchemy import or_
        scope_filters = [
            cls.scope == cls.SCOPE_ORG,  # Org-wide
            db.and_(cls.scope == cls.SCOPE_TEAM, cls.team_id == team.team_ID),  # This team
            db.and_(cls.scope == cls.SCOPE_LEAGUE, cls.league == team.league),  # This league
        ]

        if team_sport:
            scope_filters.append(
                db.and_(cls.scope == cls.SCOPE_SPORT, cls.sport == team_sport)
            )

        query = query.filter(or_(*scope_filters))

        return query.order_by(cls.event_date, cls.start_time).all()

    @classmethod
    def get_for_league(cls, league_name, year, is_spring, include_cancelled=False):
        """Get all events that apply to a league/division schedule.

        Args:
            league_name: Name of the league
            year: Season year
            is_spring: Spring (1) or Fall (0)
            include_cancelled: Include cancelled events

        Returns:
            List of OrgEvent instances
        """
        from app.models.league import League

        # Get league's sport
        league_obj = League.get_by_name(league_name)
        league_sport = league_obj.sport if league_obj else None

        query = cls.query.filter(
            cls.year == year,
            cls.is_spring == is_spring,
            cls.active == 1
        )

        if not include_cancelled:
            query = query.filter(cls.status == cls.STATUS_ACTIVE)

        # Filter by scope (team-scoped events don't show on division schedules)
        from sqlalchemy import or_
        scope_filters = [
            cls.scope == cls.SCOPE_ORG,  # Org-wide
            db.and_(cls.scope == cls.SCOPE_LEAGUE, cls.league == league_name),  # This league
        ]

        if league_sport:
            scope_filters.append(
                db.and_(cls.scope == cls.SCOPE_SPORT, cls.sport == league_sport)
            )

        query = query.filter(or_(*scope_filters))

        return query.order_by(cls.event_date, cls.start_time).all()

    @classmethod
    def get_for_season(cls, year, is_spring, include_cancelled=False):
        """Get all events for a season (admin view).

        Args:
            year: Season year
            is_spring: Spring (1) or Fall (0)
            include_cancelled: Include cancelled events

        Returns:
            List of OrgEvent instances
        """
        query = cls.query.filter(
            cls.year == year,
            cls.is_spring == is_spring,
            cls.active == 1
        )

        if not include_cancelled:
            query = query.filter(cls.status == cls.STATUS_ACTIVE)

        return query.order_by(cls.event_date, cls.start_time).all()
