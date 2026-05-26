from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from ...models import Beehive
from ..utils.influxdb import query_latest_values
from . import dashboard_bp


@dashboard_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.filter_by(user_id=current_user.id).all()
    hive_data = []
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass
        hive_data.append({'hive': hive, 'latest': latest})
    return render_template('dashboard/index.html', hive_data=hive_data)
