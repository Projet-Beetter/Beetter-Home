import requests
from datetime import datetime, timezone, timedelta
from flask import current_app
from ...models import db, RemoteServerConfig, Beehive
from .influxdb import query_recent_data


def push_to_remote(config_id):
    config = db.session.get(RemoteServerConfig, config_id)
    if not config or not config.enabled:
        return

    since = config.last_push_at
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
    elif since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    beehives = Beehive.query.filter_by(enabled=True).all()
    payload = {
        'source': 'beetter',
        'pushed_at': datetime.now(timezone.utc).isoformat(),
        'beehives': [],
    }
    for hive in beehives:
        data = query_recent_data(str(hive.id), since)
        payload['beehives'].append({
            'id': hive.id,
            'name': hive.name,
            'location': ', '.join(filter(None, [hive.street, hive.city, hive.postal_code])),
            'data': data,
        })

    try:
        resp = requests.post(
            f"{config.url.rstrip('/')}/api/push",
            json=payload,
            headers={'Authorization': f'Bearer {config.api_key}'},
            timeout=(5, 30),  # (connect_timeout, read_timeout)
        )
        if resp.ok:
            # Only advance the cursor on success so offline data is retried later.
            config.last_push_at = datetime.now(timezone.utc)
            config.last_push_status = 'success'
            config.last_push_message = f'HTTP {resp.status_code}'
        else:
            config.last_push_status = 'error'
            config.last_push_message = f'HTTP {resp.status_code}: {resp.text[:200]}'
    except requests.ConnectionError:
        # Server unreachable (no internet, wrong URL, etc.).
        # Do NOT update last_push_at — data will be included in the next push.
        config.last_push_status = 'offline'
        config.last_push_message = 'Server unreachable — data will be included in next push'
    except requests.Timeout:
        config.last_push_status = 'timeout'
        config.last_push_message = 'Request timed out — data will be included in next push'
    except requests.RequestException as e:
        config.last_push_status = 'error'
        config.last_push_message = str(e)[:500]

    db.session.commit()
