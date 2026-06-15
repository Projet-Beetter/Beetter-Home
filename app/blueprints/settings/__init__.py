from flask import Blueprint

settings_bp = Blueprint('settings', __name__, url_prefix='/')

from . import routes  # noqa: E402, F401
