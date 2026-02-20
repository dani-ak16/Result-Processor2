from flask_login import current_user
from functools import wraps
from flask import abort


def tenant_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:
            abort(401)

        if not current_user.school_id:
            abort(403)

        return f(*args, **kwargs)

    return wrapper
