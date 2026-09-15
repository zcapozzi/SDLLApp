"""AccessRequest model - self-service access request system with encrypted PII."""

from datetime import datetime, timedelta
import secrets

from app.extensions import db
from app.utils.encryption import encrypt_value, decrypt_value, hash_for_lookup


class AccessRequest(db.Model):
    """Access request for parent/coach/admin roles.

    Workflow:
    - Parent: Submit form -> verify email -> auto-approve -> account created
    - Coach: Submit form -> admin reviews -> approve/reject -> account created
    - Admin: Submit form -> admin reviews -> assign roles -> account created
    """
    __tablename__ = 'sdll_access_requests'

    # Request types
    TYPE_PARENT = 'parent'
    TYPE_COACH = 'coach'
    TYPE_ADMIN = 'admin'

    TYPES = [TYPE_PARENT, TYPE_COACH, TYPE_ADMIN]

    # Status values
    STATUS_EMAIL_PENDING = 'email_pending'  # Parent: waiting for email verification
    STATUS_PENDING = 'pending'              # Coach/Admin: waiting for admin review
    STATUS_APPROVED = 'approved'            # Request approved, account created
    STATUS_REJECTED = 'rejected'            # Request rejected
    STATUS_EXPIRED = 'expired'              # Verification token expired

    STATUSES = [STATUS_EMAIL_PENDING, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_EXPIRED]

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(20), nullable=False)  # parent, coach, admin
    status = db.Column(db.String(20), default=STATUS_PENDING)

    # Encrypted PII (same pattern as User model)
    _first_name = db.Column('first_name', db.String(500), nullable=False)
    _last_name = db.Column('last_name', db.String(500), nullable=False)
    _email = db.Column('email', db.String(500), nullable=False)
    email_hash = db.Column(db.String(64), nullable=False, index=True)
    _phone = db.Column('phone', db.String(500))

    # Email verification (for parent requests)
    verification_token = db.Column(db.String(64), unique=True)
    verification_expires = db.Column(db.DateTime)
    email_verified_at = db.Column(db.DateTime)

    # Coach-specific: which team they're requesting to coach
    team_id = db.Column(db.BigInteger, db.ForeignKey('sdll_team_seasons.team_ID'))
    team = db.relationship('TeamSeason', foreign_keys=[team_id])

    # Admin-specific: free-text description of requested roles/responsibilities
    requested_roles = db.Column(db.Text)

    # Processing info
    processed_at = db.Column(db.DateTime)
    processed_by = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    processor = db.relationship('User', foreign_keys=[processed_by])
    rejection_reason = db.Column(db.Text)

    # Link to created user (set after approval)
    created_user_id = db.Column(db.BigInteger, db.ForeignKey('sdll_users.ID'))
    created_user = db.relationship('User', foreign_keys=[created_user_id])

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Organization (for multi-org support)
    org_id = db.Column(db.BigInteger, default=1)

    def __repr__(self):
        return f'<AccessRequest {self.id} ({self.request_type}, {self.status})>'

    # Encrypted property: first_name
    @property
    def first_name(self):
        return decrypt_value(self._first_name)

    @first_name.setter
    def first_name(self, value):
        self._first_name = encrypt_value(value)

    # Encrypted property: last_name
    @property
    def last_name(self):
        return decrypt_value(self._last_name)

    @last_name.setter
    def last_name(self, value):
        self._last_name = encrypt_value(value)

    # Encrypted property: email
    @property
    def email(self):
        return decrypt_value(self._email)

    @email.setter
    def email(self, value):
        self._email = encrypt_value(value)
        self.email_hash = hash_for_lookup(value)

    # Encrypted property: phone
    @property
    def phone(self):
        return decrypt_value(self._phone)

    @phone.setter
    def phone(self, value):
        self._phone = encrypt_value(value) if value else None

    @property
    def full_name(self):
        """Return full name."""
        return f'{self.first_name} {self.last_name}'

    @property
    def is_pending(self):
        """Check if request is pending any action."""
        return self.status in (self.STATUS_PENDING, self.STATUS_EMAIL_PENDING)

    @property
    def needs_admin_review(self):
        """Check if this request needs admin review."""
        return self.status == self.STATUS_PENDING

    @property
    def type_display(self):
        """Human-readable request type."""
        displays = {
            self.TYPE_PARENT: 'Parent/Fan',
            self.TYPE_COACH: 'Coach',
            self.TYPE_ADMIN: 'League Admin'
        }
        return displays.get(self.request_type, self.request_type)

    @property
    def status_display(self):
        """Human-readable status."""
        displays = {
            self.STATUS_EMAIL_PENDING: 'Email Verification Pending',
            self.STATUS_PENDING: 'Pending Review',
            self.STATUS_APPROVED: 'Approved',
            self.STATUS_REJECTED: 'Rejected',
            self.STATUS_EXPIRED: 'Expired'
        }
        return displays.get(self.status, self.status)

    def generate_verification_token(self, hours=24):
        """Generate email verification token (default 24 hour expiry)."""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_expires = datetime.utcnow() + timedelta(hours=hours)
        db.session.commit()
        return self.verification_token

    def verify_email(self, token):
        """Verify email with token. Returns True if successful."""
        if not self.verification_token or not self.verification_expires:
            return False
        if self.verification_token != token:
            return False
        if datetime.utcnow() > self.verification_expires:
            self.status = self.STATUS_EXPIRED
            db.session.commit()
            return False

        self.email_verified_at = datetime.utcnow()
        self.status = self.STATUS_APPROVED  # Parent requests auto-approve on verification
        db.session.commit()
        return True

    def approve(self, processor_id, created_user_id=None):
        """Mark request as approved."""
        self.status = self.STATUS_APPROVED
        self.processed_at = datetime.utcnow()
        self.processed_by = processor_id
        if created_user_id:
            self.created_user_id = created_user_id
        db.session.commit()

    def reject(self, processor_id, reason=None):
        """Mark request as rejected."""
        self.status = self.STATUS_REJECTED
        self.processed_at = datetime.utcnow()
        self.processed_by = processor_id
        if reason:
            self.rejection_reason = reason
        db.session.commit()

    @classmethod
    def get_by_verification_token(cls, token):
        """Find request by verification token."""
        return cls.query.filter_by(verification_token=token).first()

    @classmethod
    def get_by_email(cls, email):
        """Find request by email using hash lookup."""
        email_hash = hash_for_lookup(email)
        return cls.query.filter_by(email_hash=email_hash).first()

    @classmethod
    def get_pending_by_email(cls, email):
        """Find pending request by email."""
        email_hash = hash_for_lookup(email)
        return cls.query.filter(
            cls.email_hash == email_hash,
            cls.status.in_([cls.STATUS_PENDING, cls.STATUS_EMAIL_PENDING])
        ).first()

    @classmethod
    def get_pending_requests(cls):
        """Get all requests pending admin review."""
        return cls.query.filter_by(status=cls.STATUS_PENDING).order_by(cls.created_at.desc()).all()

    @classmethod
    def get_requests_by_type(cls, request_type, status=None):
        """Get requests filtered by type and optionally status."""
        query = cls.query.filter_by(request_type=request_type)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def get_recent_approved_parents(cls, since_date=None):
        """Get recently approved parent requests (for daily digest)."""
        query = cls.query.filter(
            cls.request_type == cls.TYPE_PARENT,
            cls.status == cls.STATUS_APPROVED
        )
        if since_date:
            query = query.filter(cls.processed_at >= since_date)
        return query.order_by(cls.processed_at.desc()).all()

    @classmethod
    def create_parent_request(cls, first_name, last_name, email, org_id=1):
        """Create a parent access request (email verification required)."""
        request = cls(
            request_type=cls.TYPE_PARENT,
            status=cls.STATUS_EMAIL_PENDING,
            org_id=org_id
        )
        request.first_name = first_name
        request.last_name = last_name
        request.email = email

        db.session.add(request)
        db.session.commit()

        # Generate verification token
        request.generate_verification_token()

        return request

    @classmethod
    def create_coach_request(cls, first_name, last_name, email, phone=None, team_id=None, org_id=1):
        """Create a coach access request (admin approval required)."""
        request = cls(
            request_type=cls.TYPE_COACH,
            status=cls.STATUS_PENDING,
            team_id=team_id,
            org_id=org_id
        )
        request.first_name = first_name
        request.last_name = last_name
        request.email = email
        request.phone = phone

        db.session.add(request)
        db.session.commit()

        return request

    @classmethod
    def create_admin_request(cls, first_name, last_name, email, phone=None, requested_roles=None, org_id=1):
        """Create an admin access request (admin approval required)."""
        request = cls(
            request_type=cls.TYPE_ADMIN,
            status=cls.STATUS_PENDING,
            requested_roles=requested_roles,
            org_id=org_id
        )
        request.first_name = first_name
        request.last_name = last_name
        request.email = email
        request.phone = phone

        db.session.add(request)
        db.session.commit()

        return request

    @classmethod
    def expire_old_verification_tokens(cls):
        """Mark expired email verification requests as expired.
        Call from a scheduled job."""
        expired = cls.query.filter(
            cls.status == cls.STATUS_EMAIL_PENDING,
            cls.verification_expires < datetime.utcnow()
        ).all()

        count = 0
        for req in expired:
            req.status = cls.STATUS_EXPIRED
            count += 1

        if count > 0:
            db.session.commit()

        return count
