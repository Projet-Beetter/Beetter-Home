import logging
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime, timezone

_now = lambda: datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

db = SQLAlchemy()
bcrypt = Bcrypt()

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
    created_at = db.Column(db.DateTime, default=_now)

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

    @property
    def prefs(self):
        try:
            if self.preferences is None:
                p = UserPreferences(user_id=self.id)
                db.session.add(p)
                db.session.commit()
            return self.preferences
        except Exception:
            logger.exception("Failed to load/create UserPreferences for user %s", self.id)
            return UserPreferences()


class Beehive(db.Model):
    __tablename__ = 'beehives'

    id = db.Column(db.String(4), primary_key=True)
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
    created_at = db.Column(db.DateTime, default=_now)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    no_data_threshold_minutes = db.Column(db.Integer, default=10, nullable=False)
    # How many minutes without data before the hive is marked no_data.
    # Set to 0 to disable automatic no_data detection for this hive.

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    hive_id = db.Column(db.String(4), db.ForeignKey('beehives.id'), nullable=False)
    old_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    source = db.Column(db.String(50), nullable=False, default='manual')
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_now, nullable=False)

    hive = db.relationship('Beehive', backref=db.backref('alerts', cascade='all, delete-orphan'))
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
    created_at = db.Column(db.DateTime, default=_now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class HiveEvent(db.Model):
    __tablename__ = "hive_events"

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(120), nullable=False)
    event_type = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date   = db.Column(db.DateTime, nullable=True)
    all_day    = db.Column(db.Boolean, default=True)
    notes      = db.Column(db.Text, nullable=True)
    hive_id    = db.Column(db.String(4), db.ForeignKey("beehives.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    hive    = db.relationship("Beehive", backref=db.backref("events", cascade="all, delete-orphan", lazy=True))
    creator = db.relationship("User", backref=db.backref("events", lazy=True))


class UserHiveIndicator(db.Model):
    __tablename__ = 'user_hive_indicators'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    hive_id = db.Column(db.String(4), db.ForeignKey('beehives.id'), primary_key=True)
    indicators = db.Column(db.String(255), nullable=False, default='temperature_int,humidity_int')

    user = db.relationship('User', backref=db.backref('hive_indicators', lazy='dynamic'))
    hive = db.relationship('Beehive', backref=db.backref('user_indicators', cascade='all, delete-orphan', lazy='dynamic'))


class UserPreferences(db.Model):
    __tablename__ = 'user_preferences'

    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)

    # General
    language    = db.Column(db.String(10), default='en')
    time_format = db.Column(db.String(5),  default='24h')    # '24h' or '12h'
    week_start  = db.Column(db.String(10), default='monday') # 'monday' or 'sunday'
    temp_unit   = db.Column(db.String(2),  default='C')      # 'C' or 'F'

    # Notifications
    email_alerts      = db.Column(db.Boolean, default=True)
    alert_temperature = db.Column(db.Boolean, default=True)
    alert_humidity    = db.Column(db.Boolean, default=True)
    alert_sound       = db.Column(db.Boolean, default=True)
    alert_offline     = db.Column(db.Boolean, default=True)

    # Accessibility
    high_contrast = db.Column(db.Boolean, default=False)
    large_text    = db.Column(db.Boolean, default=False)
    reduce_motion = db.Column(db.Boolean, default=False)

    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    user = db.relationship('User', backref=db.backref('preferences', uselist=False, lazy=True))


class SystemConfig(db.Model):
    """Key-value store for app-wide settings."""
    __tablename__ = 'system_config'
    key   = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

    @staticmethod
    def get(key, default=None):
        row = db.session.get(SystemConfig, key)
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = db.session.get(SystemConfig, key)
        if row:
            row.value = str(value)
        else:
            db.session.add(SystemConfig(key=key, value=str(value)))
        db.session.commit()


class DailySummary(db.Model):
    __tablename__ = 'daily_summaries'

    id           = db.Column(db.Integer, primary_key=True)
    hive_id      = db.Column(db.String(4), db.ForeignKey('beehives.id'), nullable=False)
    date         = db.Column(db.Date, nullable=False)

    avg_temp_int = db.Column(db.Float, nullable=True)
    avg_temp_ext = db.Column(db.Float, nullable=True)
    avg_hum_int  = db.Column(db.Float, nullable=True)
    avg_freq_int = db.Column(db.Float, nullable=True)
    avg_amp_int  = db.Column(db.Float, nullable=True)
    avg_light    = db.Column(db.Float, nullable=True)

    alert_count   = db.Column(db.Integer, default=0)
    status_at_end = db.Column(db.String(20), nullable=True)
    data_points   = db.Column(db.Integer, default=0)

    generated_at = db.Column(db.DateTime, default=_now)

    hive = db.relationship('Beehive',
                           backref=db.backref('daily_summaries', lazy=True,
                                              cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('hive_id', 'date', name='uq_summary_hive_date'),
    )
