"""Umpire feedback routes - view post-game umpire evaluations."""

from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload

from . import umpires_bp, umpire_coordinator_required
from app.extensions import db
from app.models.post_game_report import PostGameReport
from app.models.game import Game
from app.models.org_season import OrgSeason


@umpires_bp.route('/feedback')
@login_required
@umpire_coordinator_required
def postgame_feedback():
    """View umpire feedback from post-game reports."""
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No current season configured.', 'error')
        return redirect(url_for('main.dashboard'))

    year = request.args.get('year', current_season.year, type=int)
    is_spring = request.args.get('is_spring', current_season.is_spring, type=int)
    umpire_filter = request.args.get('umpire', '')
    rating_filter = request.args.get('rating', '')

    # Build query
    query = PostGameReport.query.join(Game).options(
        joinedload(PostGameReport.game).joinedload(Game.home_team),
        joinedload(PostGameReport.game).joinedload(Game.away_team),
        joinedload(PostGameReport.team)
    ).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
        PostGameReport.umpire_name.isnot(None)
    )

    if umpire_filter:
        query = query.filter(PostGameReport.umpire_name.ilike(f'%{umpire_filter}%'))
    if rating_filter:
        query = query.filter(PostGameReport.umpire_rating == rating_filter)

    reports = query.order_by(Game.game_date.desc()).all()

    # Get unique umpire names for filter dropdown
    umpire_names = db.session.query(PostGameReport.umpire_name).join(Game).filter(
        Game.year == year,
        Game.is_spring == is_spring,
        PostGameReport.status == PostGameReport.STATUS_SUBMITTED,
        PostGameReport.umpire_name.isnot(None)
    ).distinct().order_by(PostGameReport.umpire_name).all()
    umpire_names = [u[0] for u in umpire_names]

    return render_template(
        'umpires/postgame_feedback.html',
        reports=reports,
        umpire_names=umpire_names,
        umpire_filter=umpire_filter,
        rating_filter=rating_filter,
        ratings=PostGameReport.RATINGS,
        rating_labels=PostGameReport.RATING_LABELS,
        year=year,
        is_spring=is_spring
    )


@umpires_bp.route('/feedback/summary')
@login_required
@umpire_coordinator_required
def postgame_feedback_summary():
    """Summary view of umpire ratings."""
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No current season configured.', 'error')
        return redirect(url_for('main.dashboard'))

    year = request.args.get('year', current_season.year, type=int)
    is_spring = request.args.get('is_spring', current_season.is_spring, type=int)

    # Get umpire summary
    umpire_summary = PostGameReport.get_umpire_summary(year, is_spring)

    return render_template(
        'umpires/postgame_summary.html',
        umpire_summary=umpire_summary,
        year=year,
        is_spring=is_spring
    )


@umpires_bp.route('/feedback/flagged')
@login_required
@umpire_coordinator_required
def postgame_flagged():
    """View flagged reports (unusual feedback patterns)."""
    current_season = OrgSeason.get_current_season()
    if not current_season:
        flash('No current season configured.', 'error')
        return redirect(url_for('main.dashboard'))

    year = request.args.get('year', current_season.year, type=int)
    is_spring = request.args.get('is_spring', current_season.is_spring, type=int)

    # Get flagged reports
    reports = PostGameReport.get_flagged_reports(year, is_spring)

    return render_template(
        'umpires/postgame_flagged.html',
        reports=reports,
        year=year,
        is_spring=is_spring
    )


@umpires_bp.route('/feedback/<int:report_id>/clear-flag', methods=['POST'])
@login_required
@umpire_coordinator_required
def clear_flag(report_id):
    """Clear a flag from a report after review."""
    report = PostGameReport.query.get(report_id)
    if not report:
        flash('Report not found.', 'error')
        return redirect(url_for('umpires.postgame_flagged'))

    report.is_flagged = False
    report.flag_reason = None
    db.session.commit()

    flash('Flag cleared.', 'success')
    return redirect(url_for('umpires.postgame_flagged'))
