import os
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from .models import db, bcrypt, User
from .scheduler import init_scheduler


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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(beehives_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(api_bp)
    csrf.exempt(api_bp)

    with app.app_context():
        db.create_all()
        init_scheduler(app)

    return app
