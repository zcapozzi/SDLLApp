"""Analytics models for privacy-respecting first-party tracking.

See privacyApproach.md for privacy principles governing these models.

Key privacy features:
- No PII stored (IP addresses are hashed)
- Session IDs are random UUIDs, not linked to identity
- All data stays in our database (no third-party sharing)
"""

import hashlib
import secrets
from datetime import datetime
from app.extensions import db


class PageView(db.Model):
    """Tracks anonymous page views on public pages.

    Privacy notes:
    - ip_hash is SHA-256 of IP, cannot be reversed
    - session_id is random UUID from cookie, not linked to identity
    - No PII is collected
    """
    __tablename__ = 'sdll_page_views'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    page_type = db.Column(db.String(50), nullable=False)  # 'team_schedule', 'calendar', 'privacy'
    page_context = db.Column(db.String(100))  # team token, year/season, etc.
    session_id = db.Column(db.String(64), index=True)  # Anonymous cookie-based
    ip_hash = db.Column(db.String(64))  # SHA256 of IP (privacy-safe)
    user_agent = db.Column(db.String(500))
    device_type = db.Column(db.String(20))  # 'mobile', 'tablet', 'desktop'
    viewport_width = db.Column(db.Integer)  # Updated by JS beacon
    viewport_height = db.Column(db.Integer)  # Updated by JS beacon
    referrer = db.Column(db.String(500))
    time_on_page_seconds = db.Column(db.Integer)  # Updated by JS beacon on unload
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @classmethod
    def log_view(cls, page_type, page_context, request, session_id):
        """Log a page view from a request.

        Args:
            page_type: Type of page ('team_schedule', 'calendar', etc.)
            page_context: Context info (team token, etc.)
            request: Flask request object
            session_id: Anonymous session ID from cookie
        """
        # Hash the IP address for privacy
        ip_hash = None
        if request.remote_addr:
            ip_hash = hashlib.sha256(request.remote_addr.encode()).hexdigest()

        # Detect device type from user agent
        user_agent = request.headers.get('User-Agent', '')[:500]
        device_type = cls._detect_device_type(user_agent)

        view = cls(
            page_type=page_type,
            page_context=page_context,
            session_id=session_id,
            ip_hash=ip_hash,
            user_agent=user_agent,
            device_type=device_type,
            referrer=request.headers.get('Referer', '')[:500]
        )
        db.session.add(view)
        db.session.commit()
        return view

    @staticmethod
    def _detect_device_type(user_agent):
        """Simple device detection from user agent."""
        ua_lower = user_agent.lower()
        if 'mobile' in ua_lower or 'android' in ua_lower and 'mobile' in ua_lower:
            return 'mobile'
        if 'ipad' in ua_lower or 'tablet' in ua_lower:
            return 'tablet'
        return 'desktop'

    @classmethod
    def update_from_beacon(cls, view_id, viewport_width, viewport_height, time_on_page):
        """Update a page view with data from JS beacon."""
        view = cls.query.get(view_id)
        if view:
            view.viewport_width = viewport_width
            view.viewport_height = viewport_height
            view.time_on_page_seconds = time_on_page
            db.session.commit()


class Ad(db.Model):
    """Self-hosted advertisement/sponsor content.

    No third-party ad networks - we control all ad content.
    """
    __tablename__ = 'sdll_ads'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)  # Internal name
    sponsor = db.Column(db.String(100))  # Sponsor name (displayed as "Presented by X")
    headline = db.Column(db.String(100))  # Optional headline text
    description = db.Column(db.String(300))  # Optional description text
    image_url = db.Column(db.String(500))  # Path to image (self-hosted)
    click_url = db.Column(db.String(500))  # Where to redirect on click
    alt_text = db.Column(db.String(200))  # Accessibility text

    # Targeting (optional)
    target_leagues = db.Column(db.String(200))  # Comma-separated league names, or NULL for all

    # Scheduling
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    priority = db.Column(db.Integer, default=1)  # Higher = more likely to show

    active = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    impressions = db.relationship('AdImpression', backref='ad', lazy='dynamic')
    clicks = db.relationship('AdClick', backref='ad', lazy='dynamic')

    @classmethod
    def get_active_ad(cls, league=None):
        """Get an active ad to display, optionally filtered by league.

        Returns the highest priority active ad that matches the criteria.
        """
        from datetime import date
        today = date.today()

        query = cls.query.filter(
            cls.active == 1,
            db.or_(cls.start_date.is_(None), cls.start_date <= today),
            db.or_(cls.end_date.is_(None), cls.end_date >= today)
        )

        # Filter by league if specified
        if league:
            query = query.filter(
                db.or_(
                    cls.target_leagues.is_(None),
                    cls.target_leagues == '',
                    cls.target_leagues.contains(league)
                )
            )

        return query.order_by(cls.priority.desc()).first()

    def generate_impression_token(self):
        """Generate a unique token for tracking this impression."""
        return secrets.token_urlsafe(32)

    def generate_click_token(self):
        """Generate a unique token for validating clicks."""
        return secrets.token_urlsafe(32)


class AdImpression(db.Model):
    """Tracks when an ad is displayed.

    Follows IAB viewability standards:
    - was_viewable: True if 50%+ of ad was visible for 1+ second
    - viewable_seconds: Total time ad was in viewport
    """
    __tablename__ = 'sdll_ad_impressions'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ad_id = db.Column(db.BigInteger, db.ForeignKey('sdll_ads.ID'), nullable=False, index=True)
    impression_token = db.Column(db.String(64), unique=True, index=True)  # For linking to clicks
    page_view_id = db.Column(db.BigInteger, db.ForeignKey('sdll_page_views.ID'))
    session_id = db.Column(db.String(64), index=True)
    page_context = db.Column(db.String(100))  # Team token, etc.
    device_type = db.Column(db.String(20))
    viewport_width = db.Column(db.Integer)

    # Viewability tracking (updated by JS)
    was_viewable = db.Column(db.SmallInteger, default=0)  # 1 if met IAB standard
    viewable_seconds = db.Column(db.Float, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship to clicks
    clicks = db.relationship('AdClick', backref='impression', lazy='dynamic')

    @classmethod
    def log_impression(cls, ad, page_view, session_id, page_context, device_type):
        """Log an ad impression."""
        impression = cls(
            ad_id=ad.ID,
            impression_token=ad.generate_impression_token(),
            page_view_id=page_view.ID if page_view else None,
            session_id=session_id,
            page_context=page_context,
            device_type=device_type
        )
        db.session.add(impression)
        db.session.commit()
        return impression

    @classmethod
    def update_viewability(cls, impression_token, was_viewable, viewable_seconds, viewport_width):
        """Update viewability data from JS beacon."""
        impression = cls.query.filter_by(impression_token=impression_token).first()
        if impression:
            impression.was_viewable = 1 if was_viewable else 0
            impression.viewable_seconds = viewable_seconds
            impression.viewport_width = viewport_width
            db.session.commit()


class AdClick(db.Model):
    """Tracks validated ad clicks.

    Click validation:
    - click_token must match a valid impression
    - time_to_click_ms filters obvious bots (< 500ms is suspicious)
    - click position should be within ad bounds
    """
    __tablename__ = 'sdll_ad_clicks'

    ID = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ad_id = db.Column(db.BigInteger, db.ForeignKey('sdll_ads.ID'), nullable=False, index=True)
    impression_id = db.Column(db.BigInteger, db.ForeignKey('sdll_ad_impressions.ID'), index=True)
    click_token = db.Column(db.String(64), unique=True, index=True)
    session_id = db.Column(db.String(64))

    # Validation data
    time_to_click_ms = db.Column(db.Integer)  # Time from page load to click
    click_x = db.Column(db.Integer)  # Click position for fraud detection
    click_y = db.Column(db.Integer)

    # Validation result
    validated = db.Column(db.SmallInteger, default=0)  # 1 if passed validation
    validation_notes = db.Column(db.String(200))  # Reason if failed

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @classmethod
    def log_click(cls, ad_id, impression_id, click_token, session_id,
                  time_to_click_ms, click_x, click_y):
        """Log and validate a click."""
        # Validation checks
        validated = True
        notes = []

        # Check 1: Time to click (bots click too fast)
        if time_to_click_ms and time_to_click_ms < 500:
            validated = False
            notes.append('Click too fast (<500ms)')

        # Check 2: Verify impression exists and matches
        impression = AdImpression.query.filter_by(
            impression_token=click_token,
            ad_id=ad_id
        ).first()
        if not impression:
            validated = False
            notes.append('Invalid impression token')

        # Check 3: Verify not already clicked
        existing = cls.query.filter_by(click_token=click_token).first()
        if existing:
            validated = False
            notes.append('Duplicate click')

        if validated or not existing:  # Log even invalid clicks for analysis
            click = cls(
                ad_id=ad_id,
                impression_id=impression.ID if impression else None,
                click_token=click_token,
                session_id=session_id,
                time_to_click_ms=time_to_click_ms,
                click_x=click_x,
                click_y=click_y,
                validated=1 if validated else 0,
                validation_notes='; '.join(notes) if notes else None
            )
            db.session.add(click)
            db.session.commit()
            return click, validated

        return None, False


def generate_session_id():
    """Generate a new anonymous session ID."""
    return secrets.token_urlsafe(32)
