"""
app/blueprints/utils/influxdb.py

Changes vs previous version:
  - MEASUREMENTS extended with mfcc_int_0..12 and mfcc_ext_0..12
  - write_sensor_data() accepts optional mfcc_int / mfcc_ext lists
  - All other functions unchanged (they query by measurement name, so they
    automatically pick up the new measurements without any edits)
"""

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import current_app
from datetime import datetime, timezone

RANGE_OPTIONS = ['1h', '6h', '24h', '7d', '30d']

_WINDOW_MAP = {
    '1h': '1m',
    '6h': '5m',
    '24h': '15m',
    '7d': '1h',
    '30d': '6h',
}

# ── Measurements ──────────────────────────────────────────────────────────────
# One InfluxDB measurement per physical quantity; each has a single field "value".
# MFCC coefficients 1-5 are stored separately so chart queries can filter them
# independently.  They are omitted from write_sensor_data() when not provided,
# so older packets (without MFCC) continue to work correctly.
MEASUREMENTS = (
    # Environmental + audio amplitude/frequency
    'temperature_int', 'humidity_int',
    'temperature_ext', 'humidity_ext',
    'sound_freq_int',  'sound_amp_int',
    'sound_freq_ext',  'sound_amp_ext',
    'light_ext',
    # MFCC coefficients 0-12 — written once ESP32 firmware sends them
    *[f'mfcc_int_{i}' for i in range(13)],
    *[f'mfcc_ext_{i}' for i in range(13)],
)

# Subset used by the ML feature vector (17-d per sensor, matches beehive/config.py)
# temperature, humidity, sound_freq (≈ dom_freq), sound_amp (≈ log_rms proxy),
# mfcc_0..12.  Defined here so collect_training_data.py can import it.
ML_FEATURES_INT = (
    'temperature_int', 'humidity_int',
    'sound_freq_int', 'sound_amp_int',
    *[f'mfcc_int_{i}' for i in range(13)],
)
ML_FEATURES_EXT = (
    'temperature_ext', 'humidity_ext',
    'sound_freq_ext', 'sound_amp_ext',
    *[f'mfcc_ext_{i}' for i in range(13)],
)


def _measurement_filter():
    return ' or '.join(f'r._measurement == "{m}"' for m in MEASUREMENTS)


def _client():
    return InfluxDBClient(
        url=current_app.config['INFLUXDB_URL'],
        token=current_app.config['INFLUXDB_TOKEN'],
        org=current_app.config['INFLUXDB_ORG'],
    )


def write_sensor_data(beehive_id,
                      temperature_int=None, humidity_int=None,
                      temperature_ext=None, humidity_ext=None,
                      sound_freq_int=None,  sound_amp_int=None,
                      sound_freq_ext=None,  sound_amp_ext=None,
                      light_ext=None,
                      mfcc_int=None,   # list[13] or None
                      mfcc_ext=None,   # list[13] or None
                      timestamp=None):
    """
    Write one sensor reading to InfluxDB.

    mfcc_int / mfcc_ext are optional lists of 13 floats [c0, c1, ..., c12].
    When absent (None or wrong length), the MFCC measurements are simply not
    written — the existing measurements are unaffected.
    """
    ts = timestamp or datetime.now(timezone.utc)

    # ── Scalar measurements (always present when available) ───────────────
    scalar_values = {
        'temperature_int': temperature_int,
        'humidity_int':    humidity_int,
        'temperature_ext': temperature_ext,
        'humidity_ext':    humidity_ext,
        'sound_freq_int':  sound_freq_int,
        'sound_amp_int':   sound_amp_int,
        'sound_freq_ext':  sound_freq_ext,
        'sound_amp_ext':   sound_amp_ext,
        'light_ext':       light_ext,
    }
    points = [
        Point(measurement)
        .tag("beehive_id", str(beehive_id))
        .field("value", float(value))
        .time(ts, WritePrecision.S)
        for measurement, value in scalar_values.items()
        if value is not None
    ]

    # ── MFCC measurements (written only when ESP32 provides them) ─────────
    for coeff_list, prefix in ((mfcc_int, 'mfcc_int'), (mfcc_ext, 'mfcc_ext')):
        if coeff_list is not None and len(coeff_list) == 13:
            for i, val in enumerate(coeff_list, start=0):
                points.append(
                    Point(f'{prefix}_{i}')
                    .tag("beehive_id", str(beehive_id))
                    .field("value", float(val))
                    .time(ts, WritePrecision.S)
                )

    if not points:
        return

    with _client() as c:
        c.write_api(write_options=SYNCHRONOUS).write(
            bucket=current_app.config['INFLUXDB_BUCKET'],
            org=current_app.config['INFLUXDB_ORG'],
            record=points,
        )


# ── All query functions below are UNCHANGED from the original ─────────────────
# They work on MEASUREMENTS generically, so they automatically include MFCC
# measurements in chart data and exports without any edits.

def query_chart_data(beehive_id, range_str='24h'):
    if range_str not in RANGE_OPTIONS:
        range_str = '24h'
    window = _WINDOW_MAP[range_str]
    bucket = current_app.config['INFLUXDB_BUCKET']
    org    = current_app.config['INFLUXDB_ORG']

    query = f'''
from(bucket: "{bucket}")
  |> range(start: -{range_str})
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => {_measurement_filter()})
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
  |> yield(name: "mean")
'''
    result = {m: {'labels': [], 'data': []} for m in MEASUREMENTS}
    with _client() as c:
        for table in c.query_api().query(query, org=org):
            if not table.records:
                continue
            measurement = table.records[0].get_measurement()
            if measurement not in result:
                continue
            for r in table.records:
                result[measurement]['labels'].append(
                    r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ')
                )
                val = r.get_value()
                result[measurement]['data'].append(round(val, 2) if val is not None else None)
    return result


def query_latest_values(beehive_id):
    bucket = current_app.config['INFLUXDB_BUCKET']
    org    = current_app.config['INFLUXDB_ORG']
    query = f'''
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => {_measurement_filter()})
  |> last()
'''
    result = {}
    with _client() as c:
        for table in c.query_api().query(query, org=org):
            for r in table.records:
                val = r.get_value()
                result[r.get_measurement()] = {
                    'value': round(val, 2) if val is not None else None,
                    'time':  r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ'),
                }
    return result


def delete_beehive_data(beehive_id):
    """Purge all InfluxDB measurements for a beehive."""
    bucket = current_app.config['INFLUXDB_BUCKET']
    org    = current_app.config['INFLUXDB_ORG']
    with _client() as c:
        c.delete_api().delete(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            stop=datetime.now(timezone.utc),
            predicate=f'beehive_id="{beehive_id}"',
            bucket=bucket,
            org=org,
        )


def query_export_data(beehive_id, measurements, start_str, stop_str=None):
    valid = [m for m in measurements if m in MEASUREMENTS]
    if not valid:
        return []
    bucket       = current_app.config['INFLUXDB_BUCKET']
    org          = current_app.config['INFLUXDB_ORG']
    meas_filter  = ' or '.join(f'r._measurement == "{m}"' for m in valid)
    range_clause = f'start: {start_str}'
    if stop_str:
        range_clause += f', stop: {stop_str}'
    query = f'''
from(bucket: "{bucket}")
  |> range({range_clause})
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => {meas_filter})
  |> pivot(rowKey: ["_time"], columnKey: ["_measurement"], valueColumn: "_value")
'''
    data = []
    with _client() as c:
        for table in c.query_api().query(query, org=org):
            for r in table.records:
                row = {'timestamp': r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ')}
                for field in valid:
                    v = r.values.get(field)
                    if v is not None:
                        row[field] = round(v, 2)
                data.append(row)
    return sorted(data, key=lambda x: x['timestamp'])


def query_recent_data(beehive_id, since):
    bucket   = current_app.config['INFLUXDB_BUCKET']
    org      = current_app.config['INFLUXDB_ORG']
    since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
    query = f'''
from(bucket: "{bucket}")
  |> range(start: {since_str})
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => {_measurement_filter()})
  |> pivot(rowKey: ["_time"], columnKey: ["_measurement"], valueColumn: "_value")
'''
    data = []
    with _client() as c:
        for table in c.query_api().query(query, org=org):
            for r in table.records:
                row = {'timestamp': r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ')}
                for field in MEASUREMENTS:
                    v = r.values.get(field)
                    if v is not None:
                        row[field] = round(v, 2)
                data.append(row)
    return data
