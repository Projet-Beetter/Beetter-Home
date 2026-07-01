"""
app/blueprints/utils/influxdb_predictions.py

InfluxDB read/write helpers for ML hive-state predictions.

Writes to a separate 'predictions' bucket (INFLUXDB_PREDICTIONS_BUCKET) so ML
output never mixes with raw sensor measurements in the primary bucket.

All functions fail gracefully: a missing bucket, network error, or missing
config key logs a warning and returns None / empty dict so this module never
breaks the sensor ingest path.

Do NOT call write_prediction() from api/routes.py yet — that wiring happens
once a trained model exists. This module is the storage layer only.
"""

import logging
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import current_app

logger = logging.getLogger(__name__)

# Must match IA/beehive/config.py HIVE_STATES order exactly.
HIVE_STATES = [
    'normal',            # 0
    'pre_swarming',      # 1
    'swarming',          # 2
    'queen_competition', # 3
    'queenless',         # 4
    'attack',            # 5
]

_RANGE_OPTIONS = ['1h', '6h', '24h', '7d', '30d']
_WINDOW_MAP = {
    '1h':  '1m',
    '6h':  '5m',
    '24h': '15m',
    '7d':  '2h',
    '30d': '12h',
}


def _client() -> InfluxDBClient:
    return InfluxDBClient(
        url=current_app.config['INFLUXDB_URL'],
        token=current_app.config['INFLUXDB_TOKEN'],
        org=current_app.config['INFLUXDB_ORG'],
        timeout=5_000,
    )


def write_prediction(beehive_id,
                     probabilities,
                     predicted_state,
                     confidence=None,
                     timestamp=None):
    """
    Write ML state probabilities and a summary prediction to InfluxDB.

    Args:
        beehive_id:     Hive identifier string.
        probabilities:  List of 6 floats in HIVE_STATES order (must sum ≈ 1).
        predicted_state: String name of the predicted state (argmax of probabilities).
        confidence:     Optional float override; defaults to max(probabilities).
        timestamp:      Optional datetime (UTC); defaults to now.
    """
    if len(probabilities) != len(HIVE_STATES):
        logger.warning(
            "write_prediction: expected %d probabilities, got %d — skipping",
            len(HIVE_STATES), len(probabilities),
        )
        return

    ts = timestamp or datetime.now(timezone.utc)
    conf = confidence if confidence is not None else float(max(probabilities))
    bucket = current_app.config.get('INFLUXDB_PREDICTIONS_BUCKET', 'predictions')
    org = current_app.config['INFLUXDB_ORG']

    points = []

    # One point per state → measurement 'hive_state_probability'
    for state, prob in zip(HIVE_STATES, probabilities):
        points.append(
            Point('hive_state_probability')
            .tag('beehive_id', str(beehive_id))
            .tag('state', state)
            .field('probability', float(prob))
            .time(ts, WritePrecision.S)
        )

    # One summary point → measurement 'hive_state_prediction'
    points.append(
        Point('hive_state_prediction')
        .tag('beehive_id', str(beehive_id))
        .field('state', str(predicted_state))
        .field('confidence', conf)
        .time(ts, WritePrecision.S)
    )

    try:
        with _client() as c:
            c.write_api(write_options=SYNCHRONOUS).write(
                bucket=bucket,
                org=org,
                record=points,
            )
    except Exception as e:
        logger.warning("write_prediction failed for hive %s: %s", beehive_id, e)


def query_prediction_history(beehive_id, range_str='24h'):
    """
    Return per-state probability timeseries for charting.

    Returns:
        dict of {state: {'labels': [ISO timestamps], 'data': [floats]}}
        for all 6 HIVE_STATES.  Returns empty dict on error.
    """
    if range_str not in _RANGE_OPTIONS:
        range_str = '24h'
    window = _WINDOW_MAP[range_str]
    bucket = current_app.config.get('INFLUXDB_PREDICTIONS_BUCKET', 'predictions')
    org    = current_app.config['INFLUXDB_ORG']

    state_filter = ' or '.join(f'r["state"] == "{s}"' for s in HIVE_STATES)
    query = f'''
from(bucket: "{bucket}")
  |> range(start: -{range_str})
  |> filter(fn: (r) => r._measurement == "hive_state_probability")
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => {state_filter})
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
  |> yield(name: "mean")
'''
    result = {state: {'labels': [], 'data': []} for state in HIVE_STATES}
    try:
        with _client() as c:
            for table in c.query_api().query(query, org=org):
                if not table.records:
                    continue
                state = table.records[0].values.get('state')
                if state not in result:
                    continue
                for r in table.records:
                    result[state]['labels'].append(
                        r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ')
                    )
                    val = r.get_value()
                    result[state]['data'].append(
                        round(val, 4) if val is not None else None
                    )
    except Exception as e:
        logger.warning(
            "query_prediction_history failed for hive %s: %s", beehive_id, e
        )
    return result


def query_latest_prediction(beehive_id):
    """
    Return the most recent per-state probabilities.

    Returns:
        dict {state: probability} for all 6 states, or None if no data.
    """
    bucket = current_app.config.get('INFLUXDB_PREDICTIONS_BUCKET', 'predictions')
    org    = current_app.config['INFLUXDB_ORG']

    query = f'''
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "hive_state_probability")
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> last()
'''
    result = {}
    try:
        with _client() as c:
            for table in c.query_api().query(query, org=org):
                for r in table.records:
                    state = r.values.get('state')
                    if state in HIVE_STATES:
                        result[state] = r.get_value()
    except Exception as e:
        logger.warning(
            "query_latest_prediction failed for hive %s: %s", beehive_id, e
        )

    return result if result else None
