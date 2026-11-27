from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, StringField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    Regexp,
    ValidationError,
)

from app import bcrypt
from app.models import User


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _check_current_password(user, password):
    if not bcrypt.check_password_hash(user.password_hash, password):
        raise ValidationError("La contraseña actual no es correcta.")


class ProfileForm(FlaskForm):
    """Personal info card. Changing the email also asks for the current password."""

    first_name = StringField(
        "Nombre",
        filters=[_strip],
        validators=[DataRequired(), Length(max=100)],
    )

    last_name = StringField(
        "Apellido",
        filters=[_strip],
        validators=[DataRequired(), Length(max=100)],
    )

    email = StringField(
        "Correo electrónico",
        filters=[_strip],
        validators=[
            DataRequired(),
            Email(message="Introduce un correo electrónico válido."),
            Length(max=320),
        ],
    )

    requires_accessible_spot = RadioField(
        "¿Necesitas un espacio accesible?",
        choices=[("yes", "Sí"), ("no", "No")],
        validators=[InputRequired()],
    )

    current_password = PasswordField("Contraseña actual")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Accessibility only affects which spots show up when reserving, so admins don't get it.
        if user.is_admin:
            del self.requires_accessible_spot

    def email_changed(self):
        return (self.email.data or "").strip().lower() != self.user.email

    def validate_email(self, field):
        existing_user = User.get_user_by_email(field.data)
        if existing_user is not None and existing_user.id != self.user.id:
            raise ValidationError("Ese correo electrónico ya está en uso.")

    def validate_current_password(self, field):
        if not field.data:
            if self.email_changed():
                raise ValidationError(
                    "Ingresa tu contraseña actual para cambiar el correo electrónico."
                )
            return
        _check_current_password(self.user, field.data)


class PasswordForm(FlaskForm):
    current_password = PasswordField(
        "Contraseña actual",
        validators=[DataRequired()],
    )

    new_password = PasswordField(
        "Contraseña nueva",
        validators=[
            DataRequired(),
            Length(min=8, max=128),
            Regexp(
                r"(?=.*[A-Z])(?=.*[0-9])(?=.*[?!#$&]).{8,}",
                message=(
                    "La contraseña debe tener al menos 8 caracteres, una mayúscula, un número "
                    "y uno de estos símbolos: ?, !, #, $ o &."
                ),
            ),
        ],
    )

    confirm_password = PasswordField(
        "Confirma la contraseña nueva",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="Las contraseñas no coinciden."),
        ],
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def validate_current_password(self, field):
        _check_current_password(self.user, field.data)
