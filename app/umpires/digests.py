"""Weekly digest management routes.

Handles:
- Listing weekly digests by season
- Previewing digest content
- Approving, sending, skipping digests
- Generating new digests
- Digest settings (auto-send per partner)
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from collections import defaultdict

from app.extensions import db
from app.models.umpire_partner import UmpirePartner

from . import umpires_bp, umpire_coordinator_required


@umpires_bp.route('/<int:year>/<int:is_spring>/digests')
@login_required
@umpire_coordinator_required
def weekly_digests(year, is_spring):
    """List weekly digests for the season (partners + Academy umpires)."""
    from app.models.weekly_digest import WeeklyDigest
    from app.models.umpire_digest import UmpireDigest
    from app.models.league_season import LeagueSeason

    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    # Get partner digests for this season
    partner_digests = WeeklyDigest.get_for_season(year, is_spring, limit=100)

    # Get Academy umpire digests for this season
    umpire_digests = UmpireDigest.get_for_season(year, is_spring, limit=200)

    # Group partner digests by week
    digests_by_week = defaultdict(list)
    for digest in partner_digests:
        digests_by_week[digest.week_start].append(digest)

    # Group umpire digests by week
    umpire_digests_by_week = defaultdict(list)
    for digest in umpire_digests:
        umpire_digests_by_week[digest.week_start].append(digest)

    # Get all weeks (union of both)
    all_weeks = set(digests_by_week.keys()) | set(umpire_digests_by_week.keys())
    weeks = sorted(all_weeks, reverse=True)

    # Get available seasons
    seasons = db.session.query(
        LeagueSeason.year, LeagueSeason.is_spring
    ).filter_by(active=1).distinct().order_by(
        LeagueSeason.year.desc(), LeagueSeason.is_spring.desc()
    ).all()
    seasons = [
        {'year': y, 'is_spring': s, 'name': f'{"Spring" if s else "Fall"} {y}'}
        for y, s in seasons
    ]

    return render_template(
        'umpires/weekly_digests.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        weeks=weeks,
        digests_by_week=digests_by_week,
        umpire_digests_by_week=umpire_digests_by_week,
        seasons=seasons
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/<int:id>')
@login_required
@umpire_coordinator_required
def digest_preview(year, is_spring, id):
    """Preview a specific digest."""
    from app.models.weekly_digest import WeeklyDigest

    digest = WeeklyDigest.query.get_or_404(id)
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    return render_template(
        'umpires/digest_preview.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        digest=digest
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/<int:id>', methods=['POST'])
@login_required
@umpire_coordinator_required
def digest_action(year, is_spring, id):
    """Handle digest actions: approve, send, skip, regenerate."""
    from app.models.weekly_digest import WeeklyDigest
    from app.services.weekly_digest_service import WeeklyDigestService

    digest = WeeklyDigest.query.get_or_404(id)
    action = request.form.get('action')

    service = WeeklyDigestService()

    if action == 'approve':
        digest.approve(current_user.ID)
        flash(f'Digest approved for {digest.partner_name}', 'success')

    elif action == 'send':
        if service.send_digest(digest, current_user.ID):
            flash(f'Digest sent to {digest.partner_name}', 'success')
        else:
            flash(f'Failed to send digest. Check email configuration.', 'error')

    elif action == 'skip':
        digest.mark_skipped(current_user.ID)
        flash(f'Digest skipped for {digest.partner_name}', 'success')

    elif action == 'regenerate':
        service.generate_digest_for_partner(
            digest.partner_code,
            digest.week_start,
            digest.year,
            digest.is_spring
        )
        flash(f'Digest regenerated for {digest.partner_name}', 'success')

    elif action == 'revert':
        digest.revert_to_draft()
        flash(f'Digest reverted to draft', 'success')

    return redirect(url_for('umpires.digest_preview', year=year, is_spring=is_spring, id=id))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/generate', methods=['POST'])
@login_required
@umpire_coordinator_required
def generate_digests(year, is_spring):
    """Manually generate digests for the upcoming week (partners + Academy umpires)."""
    from app.services.weekly_digest_service import WeeklyDigestService

    service = WeeklyDigestService()

    # Get target week from form or default to next week
    week_str = request.form.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            week_start = service.get_next_week_monday()
    else:
        week_start = service.get_next_week_monday()

    # Generate partner digests
    partner_digests = service.generate_all_digests(week_start, year, is_spring)

    sent_count = sum(1 for d in partner_digests if d.status == 'sent')
    draft_count = sum(1 for d in partner_digests if d.status == 'draft')
    skipped_count = sum(1 for d in partner_digests if d.status == 'skipped')

    msg_parts = []
    if draft_count:
        msg_parts.append(f'{draft_count} partner draft(s)')
    if sent_count:
        msg_parts.append(f'{sent_count} partner auto-sent')
    if skipped_count:
        msg_parts.append(f'{skipped_count} partner skipped')

    # Generate Academy umpire digests
    try:
        umpire_digests = service.generate_academy_umpire_digests(
            week_start, year, is_spring, auto_send=False
        )
        umpire_count = len([d for d in umpire_digests if d.status == 'draft'])
        if umpire_count:
            msg_parts.append(f'{umpire_count} Academy umpire digest(s)')
    except Exception as e:
        # Don't fail the whole operation if Academy digests fail
        flash(f'Warning: Could not generate Academy umpire digests: {e}', 'warning')

    flash(f'Generated digests for week of {week_start.strftime("%B %d")}: {", ".join(msg_parts)}', 'success')

    return redirect(url_for('umpires.weekly_digests', year=year, is_spring=is_spring))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/umpire/<int:id>')
@login_required
@umpire_coordinator_required
def umpire_digest_preview(year, is_spring, id):
    """Preview a specific Academy umpire digest."""
    from app.models.umpire_digest import UmpireDigest

    digest = UmpireDigest.query.get_or_404(id)
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'

    return render_template(
        'umpires/umpire_digest_preview.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        digest=digest
    )


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/umpire/<int:id>', methods=['POST'])
@login_required
@umpire_coordinator_required
def umpire_digest_action(year, is_spring, id):
    """Handle Academy umpire digest actions: send, skip."""
    from app.models.umpire_digest import UmpireDigest
    from app.services.weekly_digest_service import WeeklyDigestService

    digest = UmpireDigest.query.get_or_404(id)
    action = request.form.get('action')

    service = WeeklyDigestService()

    if action == 'send':
        if service.send_umpire_digest(digest, current_user.ID):
            flash(f'Digest sent to {digest.umpire_name}', 'success')
        else:
            flash('Failed to send digest. Check email configuration.', 'error')

    elif action == 'skip':
        digest.mark_skipped()
        flash(f'Digest skipped for {digest.umpire_name}', 'success')

    return redirect(url_for('umpires.umpire_digest_preview', year=year, is_spring=is_spring, id=id))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/umpires/send-all', methods=['POST'])
@login_required
@umpire_coordinator_required
def send_all_umpire_digests(year, is_spring):
    """Send all pending Academy umpire digests for a week."""
    from app.services.weekly_digest_service import WeeklyDigestService

    service = WeeklyDigestService()

    # Get week from form
    week_str = request.form.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid week date', 'error')
            return redirect(url_for('umpires.weekly_digests', year=year, is_spring=is_spring))
    else:
        week_start = service.get_next_week_monday()

    sent, failed = service.send_all_umpire_digests(week_start, current_user.ID)

    if sent > 0:
        flash(f'Sent {sent} Academy umpire digest(s)', 'success')
    if failed > 0:
        flash(f'Failed to send {failed} digest(s)', 'error')
    if sent == 0 and failed == 0:
        flash('No pending Academy umpire digests to send', 'info')

    return redirect(url_for('umpires.weekly_digests', year=year, is_spring=is_spring))


@umpires_bp.route('/<int:year>/<int:is_spring>/digests/settings', methods=['GET', 'POST'])
@login_required
@umpire_coordinator_required
def digest_settings(year, is_spring):
    """Configure digest settings (auto-send per partner)."""
    season_name = f'{"Spring" if is_spring else "Fall"} {year}'
    partners = UmpirePartner.query.filter_by(active=True).order_by(UmpirePartner.name).all()

    if request.method == 'POST':
        for partner in partners:
            auto_send = request.form.get(f'auto_send_{partner.id}') == 'on'
            partner.auto_send_digest = auto_send

        db.session.commit()
        flash('Digest settings updated', 'success')
        return redirect(url_for('umpires.digest_settings', year=year, is_spring=is_spring))

    return render_template(
        'umpires/digest_settings.html',
        year=year,
        is_spring=is_spring,
        season_name=season_name,
        partners=partners
    )
