from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

NO_DATA_DEFAULT_MINUTES = 10


def _check_and_push(app):
    """Runs every minute; pushes any config whose interval has elapsed."""
    with app.app_context():
        from .models import RemoteServerConfig
        from .blueprints.utils.push import push_to_remote
        from datetime import datetime, timezone, timedelta

        configs = RemoteServerConfig.query.filter_by(enabled=True).all()
        now = datetime.now(timezone.utc)
        for config in configs:
            if config.last_push_at is None:
                push_to_remote(config.id)
            else:
                last = config.last_push_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last) >= timedelta(minutes=config.push_interval):
                    push_to_remote(config.id)


def _check_no_data(app):
    """
    Runs every minute. For each enabled hive, checks when the last data point
    was received. If silence exceeds the hive's threshold, sets status to no_data
    and logs an Alert with source='threshold'.
    Recovery (no_data → calm) is handled by ingest(), not here.
    """
    with app.app_context():
        from .models import db, Beehive, Alert
        from .blueprints.utils.influxdb import query_latest_values
        from datetime import datetime, timezone

        beehives = Beehive.query.filter_by(enabled=True).all()
        now = datetime.now(timezone.utc)

        for hive in beehives:
            threshold_min = hive.no_data_threshold_minutes
            if threshold_min <= 0:
                continue

            if hive.status == 'no_data':
                continue

            last_alert = (Alert.query
                          .filter_by(hive_id=hive.id)
                          .order_by(Alert.created_at.desc())
                          .first())
            if last_alert and last_alert.source == 'manual':
                continue

            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                continue

            if not latest:
                continue

            most_recent = None
            for sensor_data in latest.values():
                if isinstance(sensor_data, dict) and sensor_data.get('time'):
                    try:
                        t = datetime.fromisoformat(
                            sensor_data['time'].replace('Z', '+00:00')
                        )
                        if most_recent is None or t > most_recent:
                            most_recent = t
                    except ValueError:
                        continue

            if most_recent is None:
                continue

            silence_minutes = (now - most_recent).total_seconds() / 60

            if silence_minutes >= threshold_min:
                old_status = hive.status
                hive.status = 'no_data'
                db.session.add(Alert(
                    hive_id=hive.id,
                    old_status=old_status,
                    new_status='no_data',
                    source='threshold',
                    note=(
                        f'No data received for {silence_minutes:.0f} minutes '
                        f'(threshold: {threshold_min} min). '
                        f'Last data: {most_recent.strftime("%Y-%m-%d %H:%M UTC")}.'
                    ),
                ))
                db.session.commit()


def init_scheduler(app):
    scheduler.add_job(
        func=_check_and_push,
        args=[app],
        trigger='interval',
        minutes=1,
        id='check_and_push',
        replace_existing=True,
    )
    scheduler.add_job(
        func=_check_no_data,
        args=[app],
        trigger='interval',
        minutes=1,
        id='check_no_data',
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
