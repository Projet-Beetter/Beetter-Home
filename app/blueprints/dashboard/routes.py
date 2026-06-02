from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from ...models import Beehive
from ...models import UserHiveIndicator
from ..utils.influxdb import query_latest_values
from ..utils.status import STATUS_CONFIG
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
        # determine which indicators this user wants for this hive
        uhi = UserHiveIndicator.query.filter_by(user_id=current_user.id, hive_id=hive.id).first()
        if uhi and uhi.indicators:
            indicators = [s for s in uhi.indicators.split(',') if s]
        else:
            indicators = ['temperature_int', 'humidity_int']

        # build indicator dicts with label/icon/suffix and latest value
        mapping = {
            'temperature_int': {'icon':'thermometer-half','suffix':'°C','label':'Int. Temp','color':'text-danger'},
            'temperature_ext': {'icon':'thermometer-half','suffix':'°C','label':'Ext. Temp','color':'text-danger'},
            'humidity_int': {'icon':'droplet-half','suffix':'%','label':'Int. Humidity','color':'text-primary'},
            'humidity_ext': {'icon':'droplet-half','suffix':'%','label':'Ext. Humidity','color':'text-primary'},
            'sound_freq_int': {'icon':'music-note-beamed','suffix':'Hz','label':'Int. Peak Freq','color':'text-secondary'},
            'sound_amp_int': {'icon':'volume-up','suffix':'','label':'Int. Amplitude','color':'text-secondary'},
            'sound_freq_ext': {'icon':'music-note-beamed','suffix':'Hz','label':'Ext. Peak Freq','color':'text-secondary'},
            'sound_amp_ext': {'icon':'volume-up','suffix':'','label':'Ext. Amplitude','color':'text-secondary'},
            'light_ext': {'icon':'brightness-high','suffix':'lx','label':'Ext. Light','color':'text-warning'},
        }

        indicators_data = []
        for key in indicators:
            info = mapping.get(key, {'icon':'dash','suffix':'','label':key})
            indicators_data.append({
                'key': key,
                'icon': info['icon'],
                'suffix': info['suffix'],
                'label': info['label'],
                'color': info.get('color',''),
                'value': latest.get(key).value if latest.get(key) else None
            })

        entry = {'hive': hive, 'latest': latest, 'indicators': indicators_data}
        if hive.id in fav_ids:
            favorite_data.append(entry)
        else:
            other_data.append(entry)

    return render_template('dashboard/index.html',
                       favorite_data=favorite_data,
                       other_data=other_data,
                       status_config=STATUS_CONFIG)
