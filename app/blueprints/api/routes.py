from flask import request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone
from ...models import Beehive
from ..utils.influxdb import write_sensor_data, query_chart_data, RANGE_OPTIONS
from . import api_bp


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

    try:
        write_sensor_data(
            beehive_id=beehive_id,
            temperature=data.get('temperature'),
            humidity=data.get('humidity'),
            timestamp=ts,
        )
    except Exception as e:
        return jsonify({'error': f'InfluxDB write failed: {e}'}), 500

    return jsonify({'status': 'ok'}), 201


@api_bp.route('/beehives/<int:hive_id>/chart-data')
@login_required
def chart_data(hive_id):
    """Returns Chart.js-ready data for the given beehive."""
    hive = Beehive.query.filter_by(id=hive_id, user_id=current_user.id).first_or_404()
    range_str = request.args.get('range', '24h')
    if range_str not in RANGE_OPTIONS:
        range_str = '24h'
    try:
        data = query_chart_data(str(hive.id), range_str)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify(data)
