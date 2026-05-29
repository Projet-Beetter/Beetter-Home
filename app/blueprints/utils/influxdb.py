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


def _client():
    return InfluxDBClient(
        url=current_app.config['INFLUXDB_URL'],
        token=current_app.config['INFLUXDB_TOKEN'],
        org=current_app.config['INFLUXDB_ORG'],
    )


def write_sensor_data(beehive_id, temperature_int=None, humidity_int=None, temperature_ext=None, humidity_ext=None, timestamp=None):
    ts = timestamp or datetime.now(timezone.utc)
    points = []
    
    if temperature_int is not None:
        points.append(
            Point("temperature_int")
            .tag("beehive_id", str(beehive_id))
            .field("value", float(temperature_int))
            .time(ts, WritePrecision.S)
        )
    if humidity_int is not None:
        points.append(
            Point("humidity_int")
            .tag("beehive_id", str(beehive_id))
            .field("value", float(humidity_int))
            .time(ts, WritePrecision.S)
        )
    if temperature_ext is not None:
        points.append(
            Point("temperature_ext")
            .tag("beehive_id", str(beehive_id))
            .field("value", float(temperature_ext))
            .time(ts, WritePrecision.S)
        )
    if humidity_ext is not None:
        points.append(
            Point("humidity_ext")
            .tag("beehive_id", str(beehive_id))
            .field("value", float(humidity_ext))
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
  |> filter(fn: (r) => r._measurement == "temperature_int" or r._measurement == "humidity_int" or r._measurement == "temperature_ext" or r._measurement == "humidity_ext")
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
  |> yield(name: "mean")
'''
    result = {
        'temperature_int': {'labels': [], 'data': []},
        'humidity_int': {'labels': [], 'data': []},
        'temperature_ext': {'labels': [], 'data': []},
        'humidity_ext': {'labels': [], 'data': []},
    }
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
  |> filter(fn: (r) => r._measurement == "temperature_int" or r._measurement == "humidity_int" or r._measurement == "temperature_ext" or r._measurement == "humidity_ext")
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
    """Return flat list of {timestamp, temperature?, humidity?} since `since`."""
    bucket = current_app.config['INFLUXDB_BUCKET']
    org = current_app.config['INFLUXDB_ORG']
    since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
    query = f'''
from(bucket: "{bucket}")
  |> range(start: {since_str})
  |> filter(fn: (r) => r["beehive_id"] == "{beehive_id}")
  |> filter(fn: (r) => r._measurement == "temperature_int" or r._measurement == "humidity_int" or r._measurement == "temperature_ext" or r._measurement == "humidity_ext")
  |> pivot(rowKey: ["_time"], columnKey: ["_measurement"], valueColumn: "_value")
'''
    data = []
    with _client() as c:
        for table in c.query_api().query(query, org=org):
            for r in table.records:
                row = {'timestamp': r.get_time().strftime('%Y-%m-%dT%H:%M:%SZ')}
                for field in ('temperature_int', 'humidity_int', 'temperature_ext', 'humidity_ext'):
                    v = r.values.get(field)
                    if v is not None:
                        row[field] = round(v, 2)
                data.append(row)
    return data
