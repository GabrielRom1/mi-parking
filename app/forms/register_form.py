from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, SelectField, StringField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    Regexp,
    ValidationError,
)

from app.models import User


class RegisterForm(FlaskForm):
    first_name = StringField(
        "Nombre",
        validators=[DataRequired(), Length(max=100)],
    )
    
    last_name = StringField(
        "Apellido",
        validators=[DataRequired(), Length(max=100)],
    )
    
    email = StringField(
        "Correo electrónico",
        validators=[DataRequired(), Email(), Length(max=320)],
    )
    
    password = PasswordField(
        "Contraseña",
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
        "Confirma la contraseña",
        validators=[
            DataRequired(),
            EqualTo("password", message="Las contraseñas no coinciden."),
        ],
    )
    
    user_role = SelectField(
        "Rol de usuario",
        choices=[
            ("estudiante", "Estudiante"),
            ("empleado", "Empleado"),
        ],
        validators=[InputRequired()],
    )
    
    requires_accessible_spot = RadioField(
        "¿Necesitas un espacio accesible?",
        choices=[("yes", "Sí"), ("no", "No")],
        validators=[InputRequired()],
    )

    def validate_email(self, field):
        existing_user = User.get_user_by_email(field.data)
        if existing_user is not None:
            raise ValidationError("Error al crear usuario.")
