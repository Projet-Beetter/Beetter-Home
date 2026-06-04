from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from ...models import db, Alert, Beehive
from ..utils.status import STATUS_CONFIG, get_dot_color
from ..utils.alert_sources import ALERT_SOURCES
from . import alerts_bp

ALERTING_STATUSES = ('stressed', 'agitated', 'critical', 'swarming', 'queenless', 'predator', 'virgin_queen')

@alerts_bp.route('/')
@login_required
def index():
    today = datetime.utcnow().date()
    all_alerts_today = Alert.query.filter(
        Alert.created_at >= today
    ).order_by(Alert.created_at.desc()).all()

    for alert in all_alerts_today:
        if current_user not in alert.read_by:
            alert.read_by.append(current_user)
    db.session.commit()

    active_hives = Beehive.query.filter(
        Beehive.status.in_(ALERTING_STATUSES)
    ).order_by(Beehive.name).all()

    active_alerts = []
    for hive in active_hives:
        last_alert = Alert.query.filter_by(hive_id=hive.id).order_by(Alert.created_at.desc()).first()
        active_alerts.append({'hive': hive, 'alert': last_alert})

    all_hives = Beehive.query.order_by(Beehive.name).all()

    return render_template('alerts/index.html',
        active_alerts=active_alerts,
        today_alerts=all_alerts_today,
        all_hives=all_hives,
        status_config=STATUS_CONFIG,
        alert_sources=ALERT_SOURCES,
        get_dot_color=get_dot_color
    )

@alerts_bp.route('/history')
@login_required
def history():
    hive_id = request.args.get('hive_id', type=int)
    status_filter = request.args.get('status')
    source_filter = request.args.get('source')
    period = request.args.get('period', 'today')

    query = Alert.query
    if hive_id:
        query = query.filter(Alert.hive_id == hive_id)
    if status_filter:
        query = query.filter(Alert.new_status == status_filter)
    if source_filter:
        query = query.filter(Alert.source == source_filter)
    if period == '7d':
        query = query.filter(Alert.created_at >= datetime.utcnow() - timedelta(days=7))
    else:
        query = query.filter(Alert.created_at >= datetime.utcnow().date())

    alerts = query.order_by(Alert.created_at.desc()).all()
    all_hives = Beehive.query.order_by(Beehive.name).all()

    return render_template('alerts/history.html',
        alerts=alerts,
        all_hives=all_hives,
        status_config=STATUS_CONFIG,
        alert_sources=ALERT_SOURCES,
        get_dot_color=get_dot_color,
        current_filters={'hive_id': hive_id, 'status': status_filter, 'source': source_filter, 'period': period}
    )

@alerts_bp.route('/<int:alert_id>/delete', methods=['POST'])
@login_required
def delete_alert(alert_id):
    if not current_user.is_admin:
        abort(403)
    alert = Alert.query.get_or_404(alert_id)
    db.session.delete(alert)
    db.session.commit()
    flash('Alert deleted.', 'info')
    return redirect(url_for('alerts.history'))

@alerts_bp.route('/clear', methods=['POST'])
@login_required
def clear_alerts():
    if not current_user.is_admin:
        abort(403)
    today = datetime.utcnow().date()
    for alert in Alert.query.filter(Alert.created_at >= today).all():
        if alert.new_status not in ALERTING_STATUSES:
            db.session.delete(alert)
    db.session.commit()
    flash("Today's condensed alerts cleared.", 'info')
    return redirect(url_for('alerts.index'))
