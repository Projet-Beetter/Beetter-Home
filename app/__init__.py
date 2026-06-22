import os
import logging
from datetime import datetime, timezone
from flask import Flask, session, redirect, request, url_for
from flask_login import LoginManager, current_user

logger = logging.getLogger(__name__)
from flask_wtf.csrf import CSRFProtect
from .models import db, bcrypt, User
from .blueprints.utils.status import CALM_STATUSES
from .scheduler import init_scheduler
from .i18n import get_text


def _apply_schema_patches(engine):
    """Idempotent: add columns to existing tables that were created before new columns were declared."""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'beehives' in tables:
        existing = {c['name'] for c in inspector.get_columns('beehives')}
        if 'no_data_threshold_minutes' not in existing:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE beehives "
                    "ADD COLUMN no_data_threshold_minutes INTEGER NOT NULL DEFAULT 10"
                ))
                conn.commit()
            logger.info("Schema patch applied: beehives.no_data_threshold_minutes added")


def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
    if secret_key == 'change-me-in-production':
        logger.warning("SECRET_KEY is using the insecure default. Set the SECRET_KEY environment variable in production.")
    app.config['SECRET_KEY'] = secret_key
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'postgresql://beetter:beetter@db:5432/beetter'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_NAME'] = 'beetter_app'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not app.debug

    app.config['INFLUXDB_URL'] = os.environ.get('INFLUXDB_URL', 'http://influxdb:8086')
    app.config['INFLUXDB_TOKEN'] = os.environ.get('INFLUXDB_TOKEN', '')
    app.config['INFLUXDB_ORG'] = os.environ.get('INFLUXDB_ORG', 'beetter')
    app.config['INFLUXDB_BUCKET'] = os.environ.get('INFLUXDB_BUCKET', 'sensors')
    app.config['INFLUXDB_PREDICTIONS_BUCKET'] = os.environ.get('INFLUXDB_PREDICTIONS_BUCKET', 'predictions')

    db.init_app(app)
    bcrypt.init_app(app)
    csrf = CSRFProtect(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .blueprints.auth import auth_bp
    from .blueprints.dashboard import dashboard_bp
    from .blueprints.beehives import beehives_bp
    from .blueprints.settings import settings_bp
    from .blueprints.account import account_bp
    from .blueprints.api import api_bp
    from .blueprints.alerts import alerts_bp
    from .blueprints.export import export_bp
    from .blueprints.admin import admin_bp
    from .blueprints.calendar import calendar_bp
    from .blueprints.setup import setup_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(beehives_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(setup_bp)
    csrf.exempt(api_bp)

    SETUP_EXEMPT = {'setup.index', 'setup.create', 'setup.create_hive', 'setup.done', 'static', 'api.ingest'}

    @app.before_request
    def check_setup():
        if request.endpoint in SETUP_EXEMPT:
            return
        if User.query.count() == 0:
            return redirect(url_for('setup.index'))

    from .models import Alert, Beehive as _Beehive, user_alert_reads

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    @app.route('/set-lang/<lang>')
    def set_lang(lang):
        if lang in ('en', 'fr'):
            session['lang'] = lang
            if current_user.is_authenticated:
                try:
                    prefs = current_user.prefs
                    prefs.language = lang
                    db.session.commit()
                except Exception:
                    pass
        referrer = request.referrer
        if referrer:
            from urllib.parse import urlparse
            parsed = urlparse(referrer)
            if parsed.netloc == request.host:
                return redirect(referrer)
        return redirect('/')

    @app.context_processor
    def inject_globals():
        lang = session.get('lang', 'en')
        alerts_count = 0
        if current_user.is_authenticated:
            today = datetime.now(timezone.utc).date()
            read_ids = db.session.query(user_alert_reads.c.alert_id).filter(
                user_alert_reads.c.user_id == current_user.id
            ).subquery()
            user_hive_ids = db.session.query(_Beehive.id).filter_by(user_id=current_user.id).subquery()
            alerts_count = Alert.query.filter(
                Alert.created_at >= today,
                Alert.hive_id.in_(user_hive_ids.select()),
                ~Alert.id.in_(read_ids),
                ~Alert.new_status.in_(CALM_STATUSES)
            ).count()
        return {
            'alerts_count': alerts_count,
            'current_lang': lang,
            '_t': lambda key: get_text(key, lang),
        }


    with app.app_context():
        db.create_all()
        _apply_schema_patches(db.engine)
        init_scheduler(app)

    return app
