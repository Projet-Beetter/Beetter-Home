from flask import render_template
from flask_login import login_required, current_user
from ...models import Beehive, UserHiveIndicator
from ..utils.influxdb import query_latest_values
from ..utils.status import STATUS_CONFIG, STATUS_FAMILIES
from . import dashboard_bp

INDICATOR_ORDER = [
    'temperature_int', 'humidity_int', 'sound_freq_int',
    'temperature_ext', 'humidity_ext', 'sound_freq_ext',
    'sound_amp_int', 'sound_amp_ext', 'light_ext',
]

INDICATOR_MAPPING = {
    'temperature_int': {'icon': 'thermometer-half', 'suffix': '°C', 'label': 'dash_ind_temp_int', 'color': 'text-danger'},
    'temperature_ext': {'icon': 'thermometer-half', 'suffix': '°C', 'label': 'dash_ind_temp_ext', 'color': 'text-danger'},
    'humidity_int':    {'icon': 'droplet-half',     'suffix': '%',  'label': 'dash_ind_hum_int',  'color': 'text-primary'},
    'humidity_ext':    {'icon': 'droplet-half',     'suffix': '%',  'label': 'dash_ind_hum_ext',  'color': 'text-primary'},
    'sound_freq_int':  {'icon': 'music-note-beamed','suffix': 'Hz', 'label': 'dash_ind_freq_int', 'color': 'text-secondary'},
    'sound_amp_int':   {'icon': 'volume-up',        'suffix': '',   'label': 'dash_ind_amp_int',  'color': 'text-secondary'},
    'sound_freq_ext':  {'icon': 'music-note-beamed','suffix': 'Hz', 'label': 'dash_ind_freq_ext', 'color': 'text-secondary'},
    'sound_amp_ext':   {'icon': 'volume-up',        'suffix': '',   'label': 'dash_ind_amp_ext',  'color': 'text-secondary'},
    'light_ext':       {'icon': 'brightness-high',  'suffix': '%',  'label': 'dash_ind_light_ext','color': 'text-warning'},
}

@dashboard_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()

    total = len(beehives)
    alerts_count = sum(1 for h in beehives if STATUS_CONFIG.get(h.status, {}).get('family') == 'critical')
    agitated_count = sum(1 for h in beehives if STATUS_CONFIG.get(h.status, {}).get('family') == 'agitated')
    calm_count = sum(1 for h in beehives if STATUS_CONFIG.get(h.status, {}).get('family') == 'calm')
    silent_count = sum(1 for h in beehives if STATUS_CONFIG.get(h.status, {}).get('family') is None)

    hive_data = []
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass
        uhi = UserHiveIndicator.query.filter_by(user_id=current_user.id, hive_id=hive.id).first()
        indicators = [s for s in uhi.indicators.split(',') if s] if uhi and uhi.indicators else ['temperature_int', 'humidity_int']

        indicators_data = []
        for key in indicators:
            info = INDICATOR_MAPPING.get(key, {'icon': 'dash', 'suffix': '', 'label': key, 'color': ''})
            indicators_data.append({
                'key': key,
                'icon': info['icon'],
                'suffix': info['suffix'],
                'label': info['label'],
                'color': info.get('color', ''),
                'value': latest.get(key)['value'] if latest.get(key) else None
            })
        indicators_data.sort(key=lambda x: INDICATOR_ORDER.index(x['key']) if x['key'] in INDICATOR_ORDER else 99)
        hive_data.append({'hive': hive, 'indicators': indicators_data})

    return render_template('dashboard/index.html',
        hive_data=hive_data,
        status_config=STATUS_CONFIG,
        status_families=STATUS_FAMILIES,
        metrics={'total': total, 'alerts': alerts_count, 'agitated': agitated_count, 'calm': calm_count, 'silent': silent_count}
    )
