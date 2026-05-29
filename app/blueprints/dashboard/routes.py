from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from ...models import Beehive
from ..utils.influxdb import query_latest_values
from . import dashboard_bp


@dashboard_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()
    fav_ids = {h.id for h in current_user.favorite_hives}

    favorite_data = []
    other_data = []
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass
        entry = {'hive': hive, 'latest': latest}
        if hive.id in fav_ids:
            favorite_data.append(entry)
        else:
            other_data.append(entry)

    return render_template('dashboard/index.html',
                           favorite_data=favorite_data,
                           other_data=other_data)

