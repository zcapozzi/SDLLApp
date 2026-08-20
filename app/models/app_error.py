"""AppError model - stores application errors for Tier I/II reporting.

Tier I: Critical errors requiring immediate attention (sent via Telegram)
Tier II: Non-critical errors summarized in periodic digest emails

Errors are always logged but NEVER block the user from their intended action.
"""

from datetime import datetime, timedelta
from app.extensions import db


class AppError(db.Model):
    """Stores application errors for monitoring and reporting."""
    __tablename__ = 'sdll_app_errors'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Error classification
    tier = db.Column(db.SmallInteger, nullable=False, default=2)  # 1=immediate, 2=digest
    context = db.Column(db.String(100), nullable=False)  # e.g., "page_view_tracking", "ad_click"
    error_type = db.Column(db.String(100), nullable=False)  # Exception class name
    error_message = db.Column(db.Text, nullable=False)
    traceback = db.Column(db.Text)

    # Request context (if available)
    request_method = db.Column(db.String(10))
    request_path = db.Column(db.String(500))
    request_user_agent = db.Column(db.String(500))
    user_id = db.Column(db.Integer)  # Logged-in user ID if available

    # Status tracking
    notified = db.Column(db.Boolean, default=False)  # Has this error been reported?
    notified_at = db.Column(db.DateTime)
    resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer)  # user_id of admin who resolved

    # For grouping similar errors
    error_hash = db.Column(db.String(64))  # Hash of context + error_type + error_message

    def __repr__(self):
        return f'<AppError {self.id}: T{self.tier} {self.context} - {self.error_type}>'

    @classmethod
    def log(cls, tier, context, error, request=None, user_id=None, traceback_str=None):
        """
        Log an error to the database.

        Args:
            tier: 1 for critical (immediate alert), 2 for digest
            context: String describing what was happening
            error: The exception that occurred
            request: Optional Flask request object
            user_id: Optional user ID if logged in
            traceback_str: Optional formatted traceback string

        Returns:
            AppError instance or None if logging failed
        """
        import hashlib

        try:
            error_type = type(error).__name__
            error_message = str(error)

            # Create hash for grouping similar errors
            hash_input = f"{context}:{error_type}:{error_message}"
            error_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:64]

            app_error = cls(
                tier=tier,
                context=context,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback_str,
                error_hash=error_hash,
                user_id=user_id
            )

            if request:
                app_error.request_method = request.method
                app_error.request_path = request.path[:500] if request.path else None
                app_error.request_user_agent = request.headers.get('User-Agent', '')[:500]

            db.session.add(app_error)
            db.session.commit()

            return app_error

        except Exception:
            # Never let error logging crash
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    @classmethod
    def get_unnotified_tier1(cls):
        """Get all Tier I errors that haven't been notified yet."""
        return cls.query.filter_by(
            tier=1,
            notified=False
        ).order_by(cls.created_at).all()

    @classmethod
    def get_unnotified_tier2(cls):
        """Get all Tier II errors that haven't been included in a digest."""
        return cls.query.filter_by(
            tier=2,
            notified=False
        ).order_by(cls.created_at).all()

    @classmethod
    def get_unresolved(cls, tier=None, limit=100):
        """Get unresolved errors, optionally filtered by tier."""
        query = cls.query.filter_by(resolved=False)
        if tier is not None:
            query = query.filter_by(tier=tier)
        return query.order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def get_digest_summary(cls, since_hours=24):
        """
        Get a summary of errors for digest email.

        Returns dict with:
            - total_count: Total errors in period
            - by_context: Count grouped by context
            - by_type: Count grouped by error type
            - sample_errors: A few example errors
        """
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(hours=since_hours)

        # Total count
        total = cls.query.filter(
            cls.created_at >= cutoff,
            cls.tier == 2
        ).count()

        # By context
        context_counts = db.session.query(
            cls.context,
            func.count(cls.id)
        ).filter(
            cls.created_at >= cutoff,
            cls.tier == 2
        ).group_by(cls.context).all()

        # By error type
        type_counts = db.session.query(
            cls.error_type,
            func.count(cls.id)
        ).filter(
            cls.created_at >= cutoff,
            cls.tier == 2
        ).group_by(cls.error_type).all()

        # Sample errors (latest 5 unique by hash)
        samples = db.session.query(cls).filter(
            cls.created_at >= cutoff,
            cls.tier == 2
        ).order_by(cls.created_at.desc()).limit(10).all()

        # Dedupe by hash
        seen_hashes = set()
        unique_samples = []
        for err in samples:
            if err.error_hash not in seen_hashes:
                seen_hashes.add(err.error_hash)
                unique_samples.append(err)
            if len(unique_samples) >= 5:
                break

        return {
            'total_count': total,
            'by_context': {ctx: count for ctx, count in context_counts},
            'by_type': {etype: count for etype, count in type_counts},
            'sample_errors': unique_samples
        }

    @classmethod
    def mark_notified(cls, error_ids):
        """Mark errors as notified."""
        if not error_ids:
            return
        cls.query.filter(cls.id.in_(error_ids)).update(
            {'notified': True, 'notified_at': datetime.utcnow()},
            synchronize_session=False
        )
        db.session.commit()

    @classmethod
    def mark_resolved(cls, error_id, user_id=None):
        """Mark a single error as resolved."""
        error = cls.query.get(error_id)
        if error:
            error.resolved = True
            error.resolved_at = datetime.utcnow()
            error.resolved_by = user_id
            db.session.commit()
        return error

    @classmethod
    def get_recent_counts(cls, hours=24):
        """Get error counts for the dashboard."""
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        tier1_count = cls.query.filter(
            cls.created_at >= cutoff,
            cls.tier == 1
        ).count()

        tier2_count = cls.query.filter(
            cls.created_at >= cutoff,
            cls.tier == 2
        ).count()

        return {'tier1': tier1_count, 'tier2': tier2_count}

    @classmethod
    def cleanup_old(cls, days=90):
        """Delete resolved errors older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = cls.query.filter(
            cls.resolved == True,
            cls.created_at < cutoff
        ).delete(synchronize_session=False)
        db.session.commit()
        return deleted
