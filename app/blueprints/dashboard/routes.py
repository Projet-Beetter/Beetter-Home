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

    hive_data = []
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass
        uhi = UserHiveIndicator.query.filter_by(user_id=current_user.id, hive_id=hive.id).first()
        if uhi and uhi.indicators:
            indicators = [s for s in uhi.indicators.split(',') if s]
        else:
            indicators = ['temperature_int', 'humidity_int']

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

        INDICATOR_ORDER = [
            'temperature_int', 'humidity_int', 'sound_freq_int',
            'temperature_ext', 'humidity_ext', 'sound_freq_ext',
            'sound_amp_int', 'sound_amp_ext', 'light_ext',
        ]
        indicators_data.sort(key=lambda x: INDICATOR_ORDER.index(x['key']) if x['key'] in INDICATOR_ORDER else 99)
        hive_data.append({'hive': hive, 'latest': latest, 'indicators': indicators_data})

    return render_template('dashboard/index.html',
                       hive_data=hive_data,
                       status_config=STATUS_CONFIG)
