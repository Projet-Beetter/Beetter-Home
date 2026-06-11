import os
from datetime import datetime
from flask import Flask, session, redirect, request, url_for
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from .models import db, bcrypt, User
from .scheduler import init_scheduler
from .i18n import get_text


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'postgresql://beetter:beetter@db:5432/beetter'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_NAME'] = 'beetter_app'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    app.config['INFLUXDB_URL'] = os.environ.get('INFLUXDB_URL', 'http://influxdb:8086')
    app.config['INFLUXDB_TOKEN'] = os.environ.get('INFLUXDB_TOKEN', '')
    app.config['INFLUXDB_ORG'] = os.environ.get('INFLUXDB_ORG', 'beetter')
    app.config['INFLUXDB_BUCKET'] = os.environ.get('INFLUXDB_BUCKET', 'sensors')

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
    csrf.exempt(api_bp)

    from .models import Alert, user_alert_reads

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    @app.route('/set-lang/<lang>')
    def set_lang(lang):
        if lang in ('en', 'fr'):
            session['lang'] = lang
        return redirect(request.referrer or '/')

    @app.context_processor
    def inject_globals():
        lang = session.get('lang', 'en')
        alerts_count = 0
        if current_user.is_authenticated:
            today = datetime.utcnow().date()
            read_ids = db.session.query(user_alert_reads.c.alert_id).filter(
                user_alert_reads.c.user_id == current_user.id
            ).subquery()
            alerts_count = Alert.query.filter(
                Alert.created_at >= today,
                ~Alert.id.in_(read_ids)
            ).count()
        return {
            'alerts_count': alerts_count,
            'current_lang': lang,
            '_t': lambda key: get_text(key, lang),
        }


    with app.app_context():
        db.create_all()
        init_scheduler(app)

    return app
