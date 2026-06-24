import logging
import os
import fcntl
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone='UTC')

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


def _generate_for_date(app, target_date):
    """
    Generates a DailySummary for each enabled hive for the given date.
    Skips hives that already have a summary for that date.
    Returns the number of summaries created.
    """
    with app.app_context():
        from .models import db, Beehive, DailySummary, Alert
        from .blueprints.utils.influxdb import query_export_data
        from datetime import datetime as dt

        start_str = target_date.strftime('%Y-%m-%dT00:00:00Z')
        stop_str  = target_date.strftime('%Y-%m-%dT23:59:59Z')
        day_start = dt.combine(target_date, dt.min.time())
        day_end   = dt.combine(target_date, dt.max.time())

        SENSORS = ['temperature_int', 'temperature_ext', 'humidity_int',
                   'sound_freq_int', 'sound_amp_int', 'light_ext']

        created = 0
        for hive in Beehive.query.filter_by(enabled=True).all():
            try:
                with db.session.no_autoflush:
                    exists = DailySummary.query.filter_by(
                        hive_id=hive.id, date=target_date
                    ).first()
                    if exists:
                        continue

                try:
                    rows = query_export_data(str(hive.id), SENSORS, start_str, stop_str)
                except Exception as exc:
                    logger.error('query_export_data failed for hive %s on %s: %s',
                                 hive.id, target_date, exc)
                    rows = []

                if not rows:
                    logger.debug('No InfluxDB rows for hive %s on %s — storing empty summary',
                                 hive.id, target_date)
                    db.session.add(DailySummary(
                        hive_id=hive.id,
                        date=target_date,
                        data_points=0,
                        status_at_end=hive.status,
                    ))
                    db.session.commit()
                    created += 1
                    continue

                def avg(key):
                    vals = [r[key] for r in rows if key in r and r[key] is not None]
                    return round(sum(vals) / len(vals), 2) if vals else None

                alert_count = Alert.query.filter(
                    Alert.hive_id == hive.id,
                    Alert.created_at >= day_start,
                    Alert.created_at <= day_end,
                ).count()

                db.session.add(DailySummary(
                    hive_id=hive.id,
                    date=target_date,
                    avg_temp_int=avg('temperature_int'),
                    avg_temp_ext=avg('temperature_ext'),
                    avg_hum_int=avg('humidity_int'),
                    avg_freq_int=avg('sound_freq_int'),
                    avg_amp_int=avg('sound_amp_int'),
                    avg_light=avg('light_ext'),
                    alert_count=alert_count,
                    status_at_end=hive.status,
                    data_points=len(rows),
                ))
                db.session.commit()
                created += 1
            except Exception:
                db.session.rollback()
                # Silently skip — another worker already inserted this record
                continue

        return created


def _generate_daily_summaries(app):
    """Scheduled job: generates summaries for yesterday."""
    from datetime import date, timedelta
    yesterday = date.today() - timedelta(days=1)
    logger.info('Generating daily summaries for %s', yesterday)
    try:
        n = _generate_for_date(app, yesterday)
        logger.info('Daily summaries done: %d hive(s) processed for %s', n, yesterday)
    except Exception as exc:
        logger.error('Daily summary job failed for %s: %s', yesterday, exc)


def _backfill_missing_summaries(app):
    """On startup, fill any gaps in the last 7 days so missed cron runs are recovered."""
    from datetime import date, timedelta
    today = date.today()
    for offset in range(1, 8):
        target = today - timedelta(days=offset)
        try:
            n = _generate_for_date(app, target)
            if n:
                logger.info('Backfill: created %d summary(s) for %s', n, target)
        except Exception as exc:
            logger.error('Backfill failed for %s: %s', target, exc)


def init_scheduler(app):
    lock_file = '/tmp/beetter_scheduler.lock'
    try:
        lock = open(lock_file, 'w')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # Another worker already holds the lock — skip scheduler init
        return

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

    with app.app_context():
        try:
            from .models import SystemConfig
            hour = int(SystemConfig.get('summary_hour', '1'))
        except Exception:
            hour = 1

    scheduler.add_job(
        func=_generate_daily_summaries,
        args=[app],
        trigger='cron',
        hour=hour,
        minute=0,
        id='generate_daily_summaries',
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()

    # Fill any days the cron missed while the server was down
    _backfill_missing_summaries(app)
