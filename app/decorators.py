from functools import wraps

from flask import abort, redirect, session, url_for

from app.models import User
from app.view_as import stop_viewing_as_user


def role_required(role_name=None):
    """Send logged-out users to the login page and block other roles with a 403.
    Admin-only pages also end 'View as user', so they always get the admin navbar."""
    def decorator(view):
        @wraps(view)
        def decorated_view(*args, **kwargs):
            user_id = session.get('user_id')
            user = User.get_user_by_id(user_id) if user_id is not None else None

            if user is None:
                return redirect(url_for('auth_bp.login'))
            if role_name is not None and (
                user.role is None or user.role.name != role_name
            ):
                abort(403)
            if role_name == 'admin':
                stop_viewing_as_user()

            return view(*args, **kwargs)

        return decorated_view

    return decorator
