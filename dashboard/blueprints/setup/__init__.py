from flask import Blueprint
setup_bp = Blueprint('setup', __name__, url_prefix='/setup')
from . import routes
