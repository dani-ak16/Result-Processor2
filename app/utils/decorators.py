from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            flash("Please log in first", "warning")
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)

    return wrapper


def roles_required(*roles):

    def decorator(f):

        @wraps(f)
        def wrapper(*args, **kwargs):

            if session.get("role") not in roles:
                flash("You do not have permission", "danger")
                return redirect(url_for("auth.login"))

            return f(*args, **kwargs)

        return wrapper

    return decorator
