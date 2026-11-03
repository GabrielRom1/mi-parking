from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    email = StringField(
        "Correo electrónico",
        validators=[DataRequired(), Email(), Length(max=320)],
    )
    password = PasswordField(
        "Contraseña",
        validators=[DataRequired(), Length(max=128)],
    )
