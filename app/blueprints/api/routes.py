"""
app/blueprints/api/routes.py

Changes vs previous version:
  - ingest() now extracts mfcc_int / mfcc_ext from the POST body
    and passes them to write_sensor_data()
  - Everything else unchanged
"""

import logging
from flask import request, jsonify
from flask_login import login_required
from datetime import datetime, timezone
from ...models import db, Beehive, Alert
from ..utils.influxdb import write_sensor_data, query_chart_data, RANGE_OPTIONS
from ..utils.thresholds import check_any_crit, check_any_warn, all_ok, THRESHOLDS
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

    hive = Beehive.query.get(beehive_id)
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
            mfcc_int=_mfcc_or_none('mfcc_int'),   # list[5] or None
            mfcc_ext=_mfcc_or_none('mfcc_ext'),   # list[5] or None
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


@api_bp.route('/beehives/<int:hive_id>/chart-data')
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
    return jsonify(data)
