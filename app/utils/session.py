from flask import session
from models.user import User


def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return User.query.get(user_id)


def current_role():
    return session.get("role")
