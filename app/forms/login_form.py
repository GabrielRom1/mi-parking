from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Email, Length, Regexp


class LoginForm(FlaskForm):
    email = StringField(
        "Correo electrónico",
        validators=[
            DataRequired(),
            Email(
                message="Introduce un correo electrónico válido.",
            ),
            Length(max=320),
        ],
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
