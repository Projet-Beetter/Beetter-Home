from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

user_favorites = db.Table('user_favorites',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('hive_id', db.Integer, db.ForeignKey('beehives.id'), primary_key=True)
)

user_alert_reads = db.Table('user_alert_reads',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('alert_id', db.Integer, db.ForeignKey('alerts.id'), primary_key=True)
)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(16), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='viewer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    beehives = db.relationship('Beehive', backref='owner', lazy=True, cascade='all, delete-orphan')
    favorite_hives = db.relationship('Beehive', secondary=user_favorites, lazy='subquery', cascade='all, delete', single_parent=True)
    remote_configs = db.relationship('RemoteServerConfig', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_editor(self):
        return self.role in ('editor', 'admin')

    @property
    def can_view_data(self):
        return True

    @property
    def can_edit_data(self):
        return self.role in ('editor', 'admin')


class Beehive(db.Model):
    __tablename__ = 'beehives'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    street = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    device_eui = db.Column(db.String(64))
    lora_frequency = db.Column(db.Float, default=868.0)
    spreading_factor = db.Column(db.Integer, default=7)
    bandwidth = db.Column(db.Integer, default=125)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='no_data')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    hive_id = db.Column(db.Integer, db.ForeignKey('beehives.id'), nullable=False)
    old_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    source = db.Column(db.String(50), nullable=False, default='manual')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    hive = db.relationship('Beehive', backref='alerts')
    read_by = db.relationship('User', secondary=user_alert_reads, lazy='subquery')

class RemoteServerConfig(db.Model):
    __tablename__ = 'remote_server_configs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    push_interval = db.Column(db.Integer, default=10, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    last_push_at = db.Column(db.DateTime)
    last_push_status = db.Column(db.String(20))
    last_push_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class UserHiveIndicator(db.Model):
    __tablename__ = 'user_hive_indicators'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    hive_id = db.Column(db.Integer, db.ForeignKey('beehives.id'), primary_key=True)
    indicators = db.Column(db.String(255), nullable=False, default='temperature_int,humidity_int')

    user = db.relationship('User', backref=db.backref('hive_indicators', lazy='dynamic'))
    hive = db.relationship('Beehive', backref=db.backref('user_indicators', lazy='dynamic'))
