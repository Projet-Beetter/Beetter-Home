from datetime import datetime
from flask import render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from ...models import db, Alert
from ..utils.status import STATUS_CONFIG
from ..utils.alert_sources import ALERT_SOURCES
from . import alerts_bp

ALERTS_DAYS = 1

@alerts_bp.route('/')
@login_required
def index():
    today = datetime.utcnow().date()
    alerts = Alert.query.filter(
        Alert.created_at >= today
    ).order_by(Alert.created_at.desc()).all()
    for alert in alerts:
        if current_user not in alert.read_by:
            alert.read_by.append(current_user)
    db.session.commit()
    return render_template('alerts/index.html', alerts=alerts, status_config=STATUS_CONFIG, alert_sources=ALERT_SOURCES)

@alerts_bp.route('/<int:alert_id>/delete', methods=['POST'])
@login_required
def delete_alert(alert_id):
    if not current_user.is_admin:
        abort(403)
    alert = Alert.query.get_or_404(alert_id)
    db.session.delete(alert)
    db.session.commit()
    flash('Alert deleted.', 'info')
    return redirect(url_for('alerts.index'))

@alerts_bp.route('/clear', methods=['POST'])
@login_required
def clear_alerts():
    if not current_user.is_admin:
        abort(403)
    today = datetime.utcnow().date()
    for alert in Alert.query.filter(Alert.created_at >= today).all():
        db.session.delete(alert)
    db.session.commit()
    flash("Today's alerts cleared.", 'info')
    return redirect(url_for('alerts.index'))


