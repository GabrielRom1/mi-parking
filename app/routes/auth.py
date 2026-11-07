
from flask import Blueprint, flash, redirect, render_template, session, url_for

from app.database import db
from app import bcrypt
from app.forms.login_form import LoginForm
from app.forms.register_form import RegisterForm
from app.models import Role, User

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    credentials_error = False

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.get_user_by_email(email)
        password_matches = user is not None and bcrypt.check_password_hash(
            user.password_hash, form.password.data
        )
        if not password_matches:
            credentials_error = True
        else:
            session.clear()
            session.permanent = True
            session['user_id'] = user.id
            return redirect(url_for('public.hello_world'))

    return render_template(
        'login.html',
        form=form,
        credentials_error=credentials_error,
    )


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        role = Role.query.filter_by(name=form.user_role.data).one()

        user = User.create_user(
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            password_hash=bcrypt.generate_password_hash(
                form.password.data
            ).decode("utf-8"),
            requires_accessible_spot=(
                form.requires_accessible_spot.data == 'yes'
            ),
            role=role,
        )

        db.session.add(user)
        db.session.commit()

        flash('¡Cuenta creado exitosamente!', 'success')
        return redirect(url_for('auth_bp.login'))

    return render_template('register.html', form=form)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth_bp.login'))
