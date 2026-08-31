"""Analytics dashboard routes for product admins."""

import os
from datetime import datetime, timedelta
from flask import render_template, request
from flask_login import login_required
from sqlalchemy import func, desc, and_, or_

from . import analytics_bp
from app.extensions import db
from app.models.analytics import PageView
from app.models.user import User
from app.utils.auth import product_admin_required
from app.utils.encryption import hash_for_lookup


def get_excluded_user_ids():
    """Get user IDs of product admins to exclude from analytics.

    Returns:
        list of user IDs to exclude
    """
    admin_emails = os.environ.get('PRODUCT_ADMIN_EMAILS', '').split(',')
    admin_emails = [e.strip().lower() for e in admin_emails if e.strip()]

    if not admin_emails:
        return []

    # Look up user IDs by email hash
    excluded_ids = []
    for email in admin_emails:
        email_hash = hash_for_lookup(email)
        user = User.query.filter_by(email_hash=email_hash).first()
        if user:
            excluded_ids.append(user.ID)

    return excluded_ids


def get_base_query_filter(cutoff, route_filter=None, excluded_user_ids=None):
    """Build base filter conditions for analytics queries.

    Returns:
        list of filter conditions
    """
    conditions = [PageView.created_at >= cutoff]

    if route_filter:
        conditions.append(PageView.page_type == route_filter)

    if excluded_user_ids:
        # Exclude views from product admins (by user_id)
        # But include anonymous views (user_id is NULL)
        conditions.append(
            or_(
                PageView.user_id.is_(None),
                ~PageView.user_id.in_(excluded_user_ids)
            )
        )

    return conditions


def calculate_pct_change(old_value, new_value):
    """Calculate percentage change between two values."""
    if old_value == 0:
        return 100 if new_value > 0 else 0
    return round(((new_value - old_value) / old_value) * 100, 1)


def get_traffic_summary(days=30, route_filter=None, excluded_user_ids=None):
    """Get traffic summary with period comparison.

    Returns:
        dict with views, sessions, active_users, avg_time and their % changes
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=days)
    prior_start = current_start - timedelta(days=days)

    # Current period stats
    current_filters = get_base_query_filter(current_start, route_filter, excluded_user_ids)
    current = db.session.query(
        func.count(PageView.ID),
        func.count(func.distinct(PageView.session_id)),
        func.count(func.distinct(PageView.user_id)),
        func.avg(PageView.time_on_page_seconds)
    ).filter(*current_filters).first()

    # Prior period stats
    prior_filters = [
        PageView.created_at >= prior_start,
        PageView.created_at < current_start
    ]
    if route_filter:
        prior_filters.append(PageView.page_type == route_filter)
    if excluded_user_ids:
        prior_filters.append(
            or_(
                PageView.user_id.is_(None),
                ~PageView.user_id.in_(excluded_user_ids)
            )
        )

    prior = db.session.query(
        func.count(PageView.ID),
        func.count(func.distinct(PageView.session_id)),
        func.count(func.distinct(PageView.user_id))
    ).filter(*prior_filters).first()

    return {
        'views': current[0] or 0,
        'sessions': current[1] or 0,
        'active_users': current[2] or 0,
        'avg_time': round(current[3] or 0, 1),
        'views_change': calculate_pct_change(prior[0] or 0, current[0] or 0),
        'sessions_change': calculate_pct_change(prior[1] or 0, current[1] or 0),
        'users_change': calculate_pct_change(prior[2] or 0, current[2] or 0)
    }


def get_daily_traffic(days=30, route_filter=None, excluded_user_ids=None):
    """Get daily page view counts for charting.

    Returns:
        list of dicts with date, views, sessions
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    filters = get_base_query_filter(cutoff, route_filter, excluded_user_ids)

    # Group by date
    results = db.session.query(
        func.date(PageView.created_at).label('date'),
        func.count(PageView.ID).label('views'),
        func.count(func.distinct(PageView.session_id)).label('sessions')
    ).filter(*filters).group_by(
        func.date(PageView.created_at)
    ).order_by('date').all()

    return [
        {
            'date': str(r.date),
            'views': r.views,
            'sessions': r.sessions
        }
        for r in results
    ]


def get_top_routes(days=30, limit=20, excluded_user_ids=None):
    """Get most visited routes/page types.

    Returns:
        list of dicts with page_type, views, sessions, avg_time
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    prior_start = cutoff - timedelta(days=days)

    # Build filters (no route_filter for this function - we're listing routes)
    filters = get_base_query_filter(cutoff, None, excluded_user_ids)

    # Current period stats by route
    current_results = db.session.query(
        PageView.page_type,
        func.count(PageView.ID).label('views'),
        func.count(func.distinct(PageView.session_id)).label('sessions'),
        func.avg(PageView.time_on_page_seconds).label('avg_time')
    ).filter(*filters).group_by(PageView.page_type).order_by(desc('views')).limit(limit).all()

    # Get prior period for trend calculation
    prior_filters = [
        PageView.created_at >= prior_start,
        PageView.created_at < cutoff
    ]
    if excluded_user_ids:
        prior_filters.append(
            or_(
                PageView.user_id.is_(None),
                ~PageView.user_id.in_(excluded_user_ids)
            )
        )

    prior_views = {}
    prior_results = db.session.query(
        PageView.page_type,
        func.count(PageView.ID).label('views')
    ).filter(*prior_filters).group_by(PageView.page_type).all()

    for r in prior_results:
        prior_views[r.page_type] = r.views

    return [
        {
            'page_type': r.page_type,
            'views': r.views,
            'sessions': r.sessions,
            'avg_time': round(r.avg_time or 0, 1),
            'trend': calculate_pct_change(prior_views.get(r.page_type, 0), r.views)
        }
        for r in current_results
    ]


def get_top_users(days=30, limit=20, route_filter=None, excluded_user_ids=None):
    """Get most active authenticated users.

    Returns:
        list of dicts with user_name, user_id, views, last_active, trend
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    prior_start = cutoff - timedelta(days=days)

    # Build filters
    filters = [
        PageView.created_at >= cutoff,
        PageView.user_id.isnot(None)
    ]
    if route_filter:
        filters.append(PageView.page_type == route_filter)
    if excluded_user_ids:
        filters.append(~PageView.user_id.in_(excluded_user_ids))

    # Current period stats by user
    current_results = db.session.query(
        User._name,
        PageView.user_id,
        func.count(PageView.ID).label('views'),
        func.max(PageView.created_at).label('last_active')
    ).join(
        User, User.ID == PageView.user_id
    ).filter(*filters).group_by(
        PageView.user_id, User._name
    ).order_by(desc('views')).limit(limit).all()

    # Get prior period for trend calculation
    prior_filters = [
        PageView.created_at >= prior_start,
        PageView.created_at < cutoff,
        PageView.user_id.isnot(None)
    ]
    if route_filter:
        prior_filters.append(PageView.page_type == route_filter)
    if excluded_user_ids:
        prior_filters.append(~PageView.user_id.in_(excluded_user_ids))

    prior_views = {}
    prior_results = db.session.query(
        PageView.user_id,
        func.count(PageView.ID).label('views')
    ).filter(*prior_filters).group_by(PageView.user_id).all()

    for r in prior_results:
        prior_views[r.user_id] = r.views

    # Decrypt user names
    from app.utils.encryption import decrypt_value

    users = []
    for r in current_results:
        # Decrypt the name (stored encrypted)
        try:
            name = decrypt_value(r[0]) if r[0] else f'User {r.user_id}'
        except Exception:
            name = f'User {r.user_id}'

        users.append({
            'name': name,
            'user_id': r.user_id,
            'views': r.views,
            'last_active': r.last_active,
            'trend': calculate_pct_change(prior_views.get(r.user_id, 0), r.views)
        })

    return users


def get_device_breakdown(days=30, route_filter=None, excluded_user_ids=None):
    """Get device type distribution.

    Returns:
        dict with mobile, tablet, desktop counts
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    filters = get_base_query_filter(cutoff, route_filter, excluded_user_ids)

    results = db.session.query(
        PageView.device_type,
        func.count(PageView.ID).label('count')
    ).filter(*filters).group_by(PageView.device_type).all()

    breakdown = {'mobile': 0, 'tablet': 0, 'desktop': 0}
    for r in results:
        device = r.device_type or 'desktop'
        if device in breakdown:
            breakdown[device] = r.count

    return breakdown


def get_available_routes(days=90):
    """Get list of page types that have been tracked.

    Returns:
        list of page_type strings
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    results = db.session.query(
        PageView.page_type
    ).filter(
        PageView.created_at >= cutoff,
        PageView.page_type.isnot(None)
    ).distinct().order_by(PageView.page_type).all()

    return [r.page_type for r in results]


def format_time_ago(dt):
    """Format a datetime as a human-readable 'time ago' string."""
    if not dt:
        return 'Never'

    now = datetime.utcnow()
    diff = now - dt

    if diff.days > 0:
        return f'{diff.days} day{"s" if diff.days > 1 else ""} ago'
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f'{hours} hour{"s" if hours > 1 else ""} ago'
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
    else:
        return 'Just now'


@analytics_bp.route('/')
@login_required
@product_admin_required
def dashboard():
    """Main analytics dashboard."""
    # Get query params
    days = request.args.get('days', 30, type=int)
    if days not in [7, 30, 90]:
        days = 30

    route_filter = request.args.get('route', '').strip() or None

    # Get excluded user IDs (product admins)
    excluded_user_ids = get_excluded_user_ids()

    # Get available routes for filter dropdown
    available_routes = get_available_routes(days=90)

    # Fetch all analytics data (excluding product admin views)
    summary = get_traffic_summary(days, route_filter, excluded_user_ids)
    daily_traffic = get_daily_traffic(days, route_filter, excluded_user_ids)
    top_routes = get_top_routes(days, excluded_user_ids=excluded_user_ids)
    top_users = get_top_users(days, route_filter=route_filter, excluded_user_ids=excluded_user_ids)
    devices = get_device_breakdown(days, route_filter, excluded_user_ids)

    # Format last_active for users
    for user in top_users:
        user['last_active_display'] = format_time_ago(user['last_active'])

    return render_template(
        'analytics/dashboard.html',
        summary=summary,
        daily_traffic=daily_traffic,
        top_routes=top_routes,
        top_users=top_users,
        devices=devices,
        days=days,
        route_filter=route_filter,
        available_routes=available_routes
    )
