"""
app/blueprints/api/routes.py

Handles the sensor ingest endpoint (/api/data) and the chart-data endpoint.
ingest() validates and stores all sensor fields including 13 MFCC coefficients
per microphone (mfcc_int / mfcc_ext), then runs threshold-based status updates
that auto-escalate or auto-recover the hive status and log an Alert.
"""

import logging
from flask import request, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime, timezone
from ...models import db, Beehive, Alert, user_alert_reads
from ..utils.influxdb import write_sensor_data, query_chart_data, query_latest_values, RANGE_OPTIONS
from ..utils.thresholds import check_any_crit, check_any_warn, all_ok, THRESHOLDS, get_threshold_status
from ..utils.status import STATUS_CONFIG, CALM_STATUSES
from ...i18n import get_text
from . import api_bp

logger = logging.getLogger(__name__)


@api_bp.route('/data', methods=['POST'])
def ingest():
    """Called by the LoRa receiver script to push sensor readings."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    beehive_id = data.get('beehive_id')
    if beehive_id is None:
        return jsonify({'error': 'beehive_id required'}), 400
    beehive_id = str(beehive_id).upper()

    hive = db.session.get(Beehive, beehive_id)
    if not hive or not hive.enabled:
        return jsonify({'error': 'Beehive not found or disabled'}), 404

    ts = None
    if data.get('timestamp'):
        try:
            ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        except ValueError:
            pass

    # ── MFCC: validate list[13] if present, silently drop otherwise ───────
    def _mfcc_or_none(key):
        val = data.get(key)
        if val is not None and isinstance(val, list) and len(val) == 13:
            try:
                return [float(v) for v in val]
            except (TypeError, ValueError):
                pass
        return None

    try:
        write_sensor_data(
            beehive_id=beehive_id,
            temperature_int=data.get('temperature_int'),
            humidity_int=data.get('humidity_int'),
            temperature_ext=data.get('temperature_ext'),
            humidity_ext=data.get('humidity_ext'),
            sound_freq_int=data.get('sound_freq_int'),
            sound_amp_int=data.get('sound_amp_int'),
            sound_freq_ext=data.get('sound_freq_ext'),
            sound_amp_ext=data.get('sound_amp_ext'),
            light_ext=data.get('light_ext'),
            mfcc_int=_mfcc_or_none('mfcc_int'),   # list[13] or None
            mfcc_ext=_mfcc_or_none('mfcc_ext'),   # list[13] or None
            timestamp=ts,
        )
    except Exception as e:
        return jsonify({'error': f'InfluxDB write failed: {e}'}), 500

    # ── Threshold check → auto status update ─────────────────────────────
    try:
        sensor_values = {
            "temperature_int": data.get('temperature_int'),
            "temperature_ext": data.get('temperature_ext'),
            "humidity_int":    data.get('humidity_int'),
            "humidity_ext":    data.get('humidity_ext'),
            "sound_freq_int":  data.get('sound_freq_int'),
            "sound_amp_int":   data.get('sound_amp_int'),
            "light_ext":       data.get('light_ext'),
        }
        clean = {k: v for k, v in sensor_values.items() if v is not None}

        crit_keys = check_any_crit(clean)
        warn_keys = check_any_warn(clean) if not crit_keys else []

        if crit_keys:
            target_status   = 'critical'
            triggered_keys  = crit_keys
        elif warn_keys and hive.status not in ('critical', 'swarming', 'queenless', 'predator'):
            target_status   = 'agitated'
            triggered_keys  = warn_keys
        else:
            target_status   = None
            triggered_keys  = []

        if target_status and hive.status != target_status:
            old_status = hive.status
            hive.status = target_status
            note_parts = []
            for key in triggered_keys:
                val = sensor_values[key]
                ok_min, ok_max, warn_min, warn_max = THRESHOLDS[key]
                note_parts.append(f"{key}={val} (ok: {ok_min}–{ok_max})")
            db.session.add(Alert(
                hive_id=hive.id,
                old_status=old_status,
                new_status=target_status,
                source='threshold',
                note="Auto threshold breach: " + ", ".join(note_parts),
            ))
            db.session.commit()

        elif all_ok(clean) and hive.status in ('critical', 'agitated',
                                                'stressed', 'virgin_queen'):
            last_alert = (Alert.query
                          .filter_by(hive_id=hive.id)
                          .order_by(Alert.created_at.desc())
                          .first())
            if last_alert and last_alert.source == 'threshold':
                old_status = hive.status
                hive.status = 'calm'
                db.session.add(Alert(
                    hive_id=hive.id,
                    old_status=old_status,
                    new_status='calm',
                    source='threshold',
                    note='Auto recovery: all sensor values returned to normal range.',
                ))
                db.session.commit()
    except Exception as e:
        logger.warning("Threshold check failed for hive %s: %s", beehive_id, e)

    return jsonify({'status': 'ok'}), 201


@api_bp.route('/beehives/<string:hive_id>/latest')
@login_required
def latest_values(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    try:
        data = query_latest_values(str(hive.id))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    for key, entry in data.items():
        entry['status'] = get_threshold_status(key, entry['value'])

    # Hive meta — used by live UI updates
    lang = session.get('lang', 'en')
    s = STATUS_CONFIG.get(hive.status, STATUS_CONFIG['no_data'])
    try:
        today = datetime.utcnow().date()
        read_ids = db.session.query(user_alert_reads.c.alert_id).filter(
            user_alert_reads.c.user_id == current_user.id
        ).subquery()
        user_hive_ids = db.session.query(Beehive.id).filter_by(user_id=current_user.id).subquery()
        alerts_count = Alert.query.filter(
            Alert.created_at >= today,
            Alert.hive_id.in_(user_hive_ids.select()),
            ~Alert.id.in_(read_ids),
            ~Alert.new_status.in_(CALM_STATUSES),
        ).count()
    except Exception:
        alerts_count = 0
    data['_hive'] = {
        'status': hive.status,
        'badge': s['badge'],
        'label': get_text('status_' + hive.status, lang),
        'alerts_count': alerts_count,
    }

    resp = jsonify(data)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api_bp.route('/alerts-count')
@login_required
def alerts_count_endpoint():
    try:
        today = datetime.utcnow().date()
        read_ids = db.session.query(user_alert_reads.c.alert_id).filter(
            user_alert_reads.c.user_id == current_user.id
        ).subquery()
        user_hive_ids = db.session.query(Beehive.id).filter_by(user_id=current_user.id).subquery()
        count = Alert.query.filter(
            Alert.created_at >= today,
            Alert.hive_id.in_(user_hive_ids.select()),
            ~Alert.id.in_(read_ids),
            ~Alert.new_status.in_(CALM_STATUSES),
        ).count()
    except Exception:
        count = 0
    resp = jsonify({'count': count})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api_bp.route('/dashboard')
@login_required
def dashboard_data():
    from ..dashboard.routes import (
        CARD_METRICS, bar_percent, card_overall_status,
    )
    beehives = Beehive.query.order_by(Beehive.created_at).all()
    result = {}
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass

        def _v(key, _l=latest):
            obj = _l.get(key)
            return obj['value'] if obj is not None else None

        metrics = []
        for m in CARD_METRICS:
            val = _v(m['key'])
            status = get_threshold_status(m['key'], val)
            metrics.append({
                'key':     m['key'],
                'value':   val,
                'unit':    m['unit'],
                'status':  status,
                'percent': bar_percent(m['key'], val),
            })

        has_data = bool(latest)
        online   = hive.enabled and has_data
        result[str(hive.id)] = {
            'overall': card_overall_status(metrics, hive.status) if online else 'no_data',
            'online':  online,
            'status':  hive.status,
            'metrics': metrics,
        }

    alerts_count   = sum(1 for h in beehives if result[str(h.id)]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'critical')
    agitated_count = sum(1 for h in beehives if result[str(h.id)]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'agitated')
    calm_count     = sum(1 for h in beehives if result[str(h.id)]['online'] and STATUS_CONFIG.get(h.status, {}).get('family') == 'calm')
    silent_count   = sum(1 for h in beehives if not result[str(h.id)]['online'] or STATUS_CONFIG.get(h.status, {}).get('family') is None)

    resp = jsonify({
        'hives': result,
        'summary': {
            'total':    len(beehives),
            'alerts':   alerts_count,
            'agitated': agitated_count,
            'calm':     calm_count,
            'silent':   silent_count,
        }
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api_bp.route('/beehives/<string:hive_id>/chart-data')
@login_required
def chart_data(hive_id):
    """Returns Chart.js-ready data for the given beehive."""
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    range_str = request.args.get('range', '24h')
    if range_str not in RANGE_OPTIONS:
        range_str = '24h'
    try:
        data = query_chart_data(str(hive.id), range_str)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    resp = jsonify(data)
    resp.headers['Cache-Control'] = 'no-store'
    return resp
