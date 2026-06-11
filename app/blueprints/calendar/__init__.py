from flask import Blueprint

calendar_bp = Blueprint('calendar', __name__, url_prefix='/calendar')

from . import routes  # noqa: E402, F401
