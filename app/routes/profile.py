from flask import Blueprint, flash, redirect, render_template, session, url_for

from app import bcrypt
from app.decorators import role_required
from app.forms.profile_form import PasswordForm, ProfileForm
from app.models import User

profile_bp = Blueprint('profile', __name__)

# Both cards live on the same page, so each form gets a prefix to keep their
# fields (both have current_password) apart.
_INFO_PREFIX = 'info'
_PASSWORD_PREFIX = 'password'


def _current_user():
    return User.get_user_by_id(session['user_id'])


def _render(user, info_form=None, password_form=None, status=200):
    if info_form is None:
        info_form = ProfileForm(user, prefix=_INFO_PREFIX, formdata=None, obj=user)
        if 'requires_accessible_spot' in info_form:
            info_form.requires_accessible_spot.data = (
                'yes' if user.requires_accessible_spot else 'no'
            )
    if password_form is None:
        password_form = PasswordForm(user, prefix=_PASSWORD_PREFIX, formdata=None)
    return render_template(
        'profile/index.html',
        user=user,
        info_form=info_form,
        password_form=password_form,
        active_nav='profile',
    ), status


@profile_bp.route('/', methods=['GET'])
@role_required()
def index():
    return _render(_current_user())


@profile_bp.route('/', methods=['POST'])
@role_required()
def update_info():
    user = _current_user()
    form = ProfileForm(user, prefix=_INFO_PREFIX)
    if not form.validate_on_submit():
        return _render(user, info_form=form, status=422)

    if 'requires_accessible_spot' in form:
        requires_accessible_spot = form.requires_accessible_spot.data == 'yes'
    else:
        requires_accessible_spot = user.requires_accessible_spot

    user.update_profile(
        email=form.email.data,
        first_name=form.first_name.data,
        last_name=form.last_name.data,
        requires_accessible_spot=requires_accessible_spot,
    )
    flash('Tu información se actualizó.', 'success')
    return redirect(url_for('profile.index'))


@profile_bp.route('/password', methods=['POST'])
@role_required()
def update_password():
    user = _current_user()
    form = PasswordForm(user, prefix=_PASSWORD_PREFIX)
    if not form.validate_on_submit():
        return _render(user, password_form=form, status=422)

    user.update_password(
        bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
    )
    flash('Tu contraseña se actualizó.', 'success')
    return redirect(url_for('profile.index'))
