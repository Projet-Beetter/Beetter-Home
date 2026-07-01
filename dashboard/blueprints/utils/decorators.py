from functools import wraps
from flask import abort
from flask_login import current_user

def editor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.can_edit_data:
            abort(403)
        return f(*args, **kwargs)
    return decorated
