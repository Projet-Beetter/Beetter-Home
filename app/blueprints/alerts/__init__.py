from flask import Blueprint
alerts_bp = Blueprint('alerts', __name__, url_prefix='/alerts')
from . import routes
