from datetime import datetime
from flask import render_template
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

