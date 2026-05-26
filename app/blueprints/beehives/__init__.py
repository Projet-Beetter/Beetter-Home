from flask import Blueprint

beehives_bp = Blueprint('beehives', __name__, url_prefix='/beehives')

from . import routes  # noqa: E402, F401
