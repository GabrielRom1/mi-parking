"""'View as user' for admins.

An admin can browse MiParking with the user navbar while keeping their own
permissions. The mode is a flag in the session, so it ends at logout. Opening a
user page turns it on and opening an admin page turns it off, so the navbar
always matches the page.
"""
from flask import session

from app.models import User

_SESSION_KEY = 'view_as_user'


def start_viewing_as_user():
    session[_SESSION_KEY] = True


def stop_viewing_as_user():
    session.pop(_SESSION_KEY, None)


def is_viewing_as_user(user):
    return user is not None and user.is_admin and session.get(_SESSION_KEY, False)


def enter_user_view_for_admins():
    """before_request hook for blueprints made of user pages."""
    user_id = session.get('user_id')
    user = User.get_user_by_id(user_id) if user_id is not None else None
    if user is not None and user.is_admin:
        start_viewing_as_user()


def init_app(app):
    @app.context_processor
    def inject_view_mode():
        def viewing_as_user(user):
            return is_viewing_as_user(user)

        return {'viewing_as_user': viewing_as_user}
