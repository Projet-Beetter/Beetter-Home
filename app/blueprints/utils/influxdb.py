from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import current_app
from datetime import datetime, timezone

RANGE_OPTIONS = {'1h', '6h', '24h', '7d', '30d'}

_WINDOW_MAP = {
    '1h': '1m',
    '6h': '5m',
    '24h': '15m',
    '7d': '1h',
    '30d': '6h',
}

# Canonical list of measurements stored for a beehive.
# One InfluxDB measurement per physical quantity; each has a single field "value".
MEASUREMENTS = (
    'temperature_int', 'humidity_int',      # interior temp/humidity sensor
    'temperature_ext', 'humidity_ext',      # exterior temp/humidity sensor
    'sound_freq_int', 'sound_amp_int',      # interior microphone: peak freq (Hz) + amplitude
    'sound_freq_ext', 'sound_amp_ext',      # exterior microphone: peak freq (Hz) + amplitude
    'light_ext',                            # exterior photoresistor: light level
)


def _measurement_filter():
    """Flux predicate matching any of our measurements."""
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
                      sound_freq_int=None, sound_amp_int=None,
                      sound_freq_ext=None, sound_amp_ext=None,
                      light_ext=None,
                      timestamp=None):
    ts = timestamp or datetime.now(timezone.utc)
    values = {
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
        for measurement, value in values.items()
        if value is not None
    ]
    if not points:
        return
    with _client() as c:
        c.write_api(write_options=SYNCHRONOUS).write(
            bucket=current_app.config['INFLUXDB_BUCKET'],
            org=current_app.config['INFLUXDB_ORG'],
            record=points,
        )


def query_chart_data(beehive_id, range_str='24h'):
    if range_str not in RANGE_OPTIONS:
        range_str = '24h'
    window = _WINDOW_MAP[range_str]
    bucket = current_app.config['INFLUXDB_BUCKET']
    org = current_app.config['INFLUXDB_ORG']

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
    org = current_app.config['INFLUXDB_ORG']
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
                    'time': r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ'),
                }
    return result


def query_recent_data(beehive_id, since):
    """Return flat list of {timestamp, <measurement>: value, ...} since `since`."""
    bucket = current_app.config['INFLUXDB_BUCKET']
    org = current_app.config['INFLUXDB_ORG']
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
