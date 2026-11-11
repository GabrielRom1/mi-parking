from functools import wraps

from flask import abort, redirect, session, url_for

from app.database import db
from app.models import User


def role_required(role_name=None):
    def decorator(view):
        @wraps(view)
        def decorated_view(*args, **kwargs):
            user_id = session.get('user_id')
            user = db.session.get(User, user_id) if user_id is not None else None

            if user is None:
                return redirect(url_for('auth_bp.login'))
            if role_name is not None and (
                user.role is None or user.role.name != role_name
            ):
                abort(403)

            return view(*args, **kwargs)

        return decorated_view

    return decorator
