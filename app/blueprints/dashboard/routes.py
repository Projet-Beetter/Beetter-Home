from flask import render_template
from flask_login import login_required
from ...models import Beehive
from ..utils.influxdb import query_latest_values
from ..utils.status import STATUS_CONFIG, STATUS_FAMILIES
from ..beehives.routes import get_threshold_status
from . import dashboard_bp

CARD_METRICS = [
    {"key": "temperature_int", "label": "Temp. int",  "unit": "°C",  "icon": "bi-thermometer-half",  "color": "#E24B4A"},
    {"key": "temperature_ext", "label": "Temp. ext",  "unit": "°C",  "icon": "bi-thermometer-half",  "color": "#F4836B"},
    {"key": "humidity_int",    "label": "Hum. int",   "unit": "%",   "icon": "bi-droplet-half",      "color": "#378ADD"},
    {"key": "sound_freq_int",  "label": "Fréquence",  "unit": " Hz", "icon": "bi-music-note-beamed", "color": "#639922"},
]

CARD_RANGES = {
    "temperature_int": (28, 42),
    "temperature_ext": (0,  40),
    "humidity_int":    (40, 85),
    "sound_freq_int":  (150, 400),
}

def bar_percent(key, value):
    if value is None or key not in CARD_RANGES:
        return 0
    lo, hi = CARD_RANGES[key]
    return max(0, min(100, int((value - lo) / (hi - lo) * 100)))

STATUS_PRIORITY = {"crit": 3, "warn": 2, "ok": 1, "no_data": 0}

STATUS_SEVERITY = {
    "swarming":     "crit",
    "queenless":    "crit",
    "predator":     "crit",
    "critical":     "crit",
    "stressed":     "warn",
    "agitated":     "warn",
    "virgin_queen": "warn",
    "ventilating":  "warn",
    "silent":       "warn",
    "foraging":     "ok",
    "calm":         "ok",
    "no_data":      "no_data",
}

def card_overall_status(metric_list, hive_status="no_data"):
    worst = STATUS_SEVERITY.get(hive_status, "no_data")
    for m in metric_list:
        if STATUS_PRIORITY.get(m["status"], 0) > STATUS_PRIORITY.get(worst, 0):
            worst = m["status"]
    return worst

@dashboard_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()

    hive_metrics = {}
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass

        def _v(key, _latest=latest):
            obj = _latest.get(key)
            return obj['value'] if obj is not None else None

        metrics = []
        for m in CARD_METRICS:
            val = _v(m["key"])
            status = get_threshold_status(m["key"], val)
            metrics.append({
                **m,
                "value":   val,
                "status":  status,
                "percent": bar_percent(m["key"], val),
            })

        has_data = bool(latest)
        online   = hive.enabled and has_data
        hive_metrics[hive.id] = {
            "metrics": metrics,
            "overall": card_overall_status(metrics, hive.status) if online else "no_data",
            "online":  online,
            "family":  STATUS_CONFIG.get(hive.status, STATUS_CONFIG.get('no_data', {})).get('family') if online else None,
        }

    total          = len(beehives)
    alerts_count   = sum(1 for h in beehives if hive_metrics[h.id]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'critical')
    agitated_count = sum(1 for h in beehives if hive_metrics[h.id]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'agitated')
    calm_count     = sum(1 for h in beehives if hive_metrics[h.id]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'calm')
    silent_count   = sum(1 for h in beehives if not hive_metrics[h.id]['online'] or STATUS_CONFIG.get(h.status, {}).get('family') is None)

    return render_template('dashboard/index.html',
        beehives=beehives,
        hive_metrics=hive_metrics,
        status_config=STATUS_CONFIG,
        status_families=STATUS_FAMILIES,
        metrics={'total': total, 'alerts': alerts_count, 'agitated': agitated_count, 'calm': calm_count, 'silent': silent_count}
    )
