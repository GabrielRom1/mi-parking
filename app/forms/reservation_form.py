from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import SelectField
from wtforms.validators import DataRequired


class ReservationForm(FlaskForm):
    """Start and end dropdowns (SRS REQ.3.1). Values are ISO datetimes; the view sets the choices for the chosen day."""

    start_time = SelectField(
        "Hora de entrada",
        validators=[DataRequired(message="Escoge una hora de entrada.")],
    )
    end_time = SelectField(
        "Hora de salida",
        validators=[DataRequired(message="Escoge una hora de salida.")],
    )

    def set_choices(self, starts, ends):
        self.start_time.choices = [(_value(moment), _label(moment)) for moment in starts]
        self.end_time.choices = [(_value(moment), _label(moment)) for moment in ends]

    @property
    def start(self):
        return datetime.fromisoformat(self.start_time.data)

    @property
    def end(self):
        return datetime.fromisoformat(self.end_time.data)


def _value(moment):
    return moment.isoformat(timespec='minutes')


def _label(moment):
    return moment.strftime('%I:%M %p').lstrip('0')
