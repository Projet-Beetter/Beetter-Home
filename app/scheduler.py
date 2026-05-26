from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


def _make_push_job(app, config_id):
    def job():
        with app.app_context():
            from .blueprints.utils.push import push_to_remote
            push_to_remote(config_id)
    return job


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


def init_scheduler(app):
    scheduler.add_job(
        func=_check_and_push,
        args=[app],
        trigger='interval',
        minutes=1,
        id='check_and_push',
        replace_existing=True,
    )
    scheduler.start()
