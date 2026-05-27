from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='viewer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    beehives = db.relationship('Beehive', backref='owner', lazy=True, cascade='all, delete-orphan')
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
    location = db.Column(db.String(200))
    device_eui = db.Column(db.String(64))
    lora_frequency = db.Column(db.Float, default=868.0)
    spreading_factor = db.Column(db.Integer, default=7)
    bandwidth = db.Column(db.Integer, default=125)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


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
