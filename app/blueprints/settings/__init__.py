from flask import Blueprint

settings_bp = Blueprint('settings', __name__, url_prefix='/servers')

from . import routes  # noqa: E402, F401
