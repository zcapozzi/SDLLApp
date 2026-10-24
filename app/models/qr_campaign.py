"""QR Campaign model - QR code-based onboarding for coaches, umpire mentors, sponsors."""

from datetime import datetime
import secrets

from app.extensions import db


class QRCampaign(db.Model):
    """A QR campaign for in-person onboarding events.

    Used at coach meetings, sponsor events, umpire mentor signups, etc.
    Each campaign generates a unique QR code that routes users to the
    appropriate onboarding flow.
    """
    __tablename__ = 'sdll_qr_campaigns'

    # Campaign types
    TYPE_COACH_MEETING = 'coach_meeting'
    TYPE_UMPIRE_MENTOR = 'umpire_mentor'
    TYPE_SPONSOR = 'sponsor'
    TYPE_VOLUNTEER = 'volunteer'
    TYPE_GENERAL = 'general'

    TYPES = [
        (TYPE_COACH_MEETING, 'Coach Meeting'),
        (TYPE_UMPIRE_MENTOR, 'Umpire Mentor Signup'),
        (TYPE_SPONSOR, 'Sponsor Registration'),
        (TYPE_VOLUNTEER, 'Volunteer Signup'),
        (TYPE_GENERAL, 'General Access'),
    ]

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    campaign_type = db.Column(db.String(30), nullable=False)

    # Unique token for QR code URL
    token = db.Column(db.String(32), unique=True, nullable=False, index=True)

    # Season context (optional, for seasonal campaigns)
    org_season_id = db.Column(db.BigInteger, db.ForeignKey('sdll_org_seasons.ID'))
    org_season = db.relationship('OrgSeason', backref='qr_campaigns')

    # Optional sport filter (for coach campaigns)
    sport = db.Column(db.String(20))  # 'baseball', 'softball', or None for both

    # Campaign settings
    active = db.Column(db.SmallInteger, default=1)
    expires_at = db.Column(db.DateTime)  # Optional expiration

    # Welcome message shown after scanning
    welcome_message = db.Column(db.Text)

    # Redirect URL after completion (optional override)
    completion_redirect_url = db.Column(db.String(500))

    # Analytics
    scan_count = db.Column(db.Integer, default=0)
    registration_count = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    creator = db.relationship('User', foreign_keys=[created_by])
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Organization (for multi-org support)
    org_id = db.Column(db.BigInteger, default=1)

    def __repr__(self):
        return f'<QRCampaign {self.id} ({self.name})>'

    @property
    def is_active(self):
        """Check if campaign is currently active."""
        if self.active != 1:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def type_display(self):
        """Human-readable campaign type."""
        for code, label in self.TYPES:
            if code == self.campaign_type:
                return label
        return self.campaign_type

    @property
    def qr_url(self):
        """URL for QR code (relative, append to base URL)."""
        return f'/s/qr/{self.token}'

    @property
    def conversion_rate(self):
        """Calculate conversion rate (scans -> registrations)."""
        if self.scan_count == 0:
            return 0
        return round((self.registration_count / self.scan_count) * 100, 1)

    def record_scan(self):
        """Increment scan count."""
        self.scan_count = (self.scan_count or 0) + 1
        db.session.commit()

    def record_registration(self):
        """Increment registration count."""
        self.registration_count = (self.registration_count or 0) + 1
        db.session.commit()

    @classmethod
    def generate_token(cls):
        """Generate unique token for QR code URL."""
        while True:
            token = secrets.token_urlsafe(16)[:16]  # 16 char alphanumeric
            if not cls.query.filter_by(token=token).first():
                return token

    @classmethod
    def get_by_token(cls, token):
        """Find campaign by token."""
        return cls.query.filter_by(token=token).first()

    @classmethod
    def get_active(cls, org_id=1):
        """Get all active campaigns."""
        return cls.query.filter(
            cls.org_id == org_id,
            cls.active == 1
        ).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_by_type(cls, campaign_type, org_id=1):
        """Get campaigns of a specific type."""
        return cls.query.filter(
            cls.org_id == org_id,
            cls.campaign_type == campaign_type
        ).order_by(cls.created_at.desc()).all()

    @classmethod
    def create(cls, name, campaign_type, created_by, description=None,
               org_season_id=None, sport=None, welcome_message=None,
               expires_at=None, org_id=1):
        """Create a new QR campaign."""
        campaign = cls(
            name=name,
            campaign_type=campaign_type,
            description=description,
            token=cls.generate_token(),
            org_season_id=org_season_id,
            sport=sport,
            welcome_message=welcome_message,
            expires_at=expires_at,
            created_by=created_by,
            org_id=org_id
        )
        db.session.add(campaign)
        db.session.commit()
        return campaign


class QRCampaignScan(db.Model):
    """Individual scan records for QR campaigns.

    Tracks each scan for detailed analytics.
    """
    __tablename__ = 'sdll_qr_campaign_scans'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('sdll_qr_campaigns.id',
                                                       ondelete='CASCADE'), nullable=False)
    campaign = db.relationship('QRCampaign', backref='scans')

    # User who scanned (if logged in)
    user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    user = db.relationship('User', foreign_keys=[user_id])

    # Outcome tracking
    outcome = db.Column(db.String(30))  # 'viewed', 'registered', 'already_registered', 'logged_in'

    # Context
    user_agent = db.Column(db.String(500))
    ip_hash = db.Column(db.String(64))  # Hashed IP for unique visitor tracking

    # Timestamp
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<QRCampaignScan {self.id} campaign={self.campaign_id}>'

    @classmethod
    def record(cls, campaign_id, user_id=None, outcome=None, user_agent=None, ip_hash=None):
        """Record a scan."""
        scan = cls(
            campaign_id=campaign_id,
            user_id=user_id,
            outcome=outcome,
            user_agent=user_agent,
            ip_hash=ip_hash
        )
        db.session.add(scan)
        db.session.commit()
        return scan
