from flask_wtf import FlaskForm
from wtforms import DateTimeField, HiddenField, SelectField
from wtforms.validators import Optional
from wtforms.widgets import HiddenInput


class QuickFindForm(FlaskForm):
    """Quick Find (SRS REQ.5.1): an optional lot and a duration, or the time picked on the chart."""

    lot = SelectField("Lote", validators=[Optional()], validate_choice=True)
    duration = SelectField("Duración", coerce=int, validators=[Optional()])
    # Set instead of the duration by "Búsqueda rápida en este horario".
    start_time = DateTimeField(format='%Y-%m-%dT%H:%M', widget=HiddenInput(), validators=[Optional()])
    end_time = DateTimeField(format='%Y-%m-%dT%H:%M', widget=HiddenInput(), validators=[Optional()])
    # Comma-separated IDs of the spots already suggested, for "Buscar otro".
    skip = HiddenField()

    def skipped_ids(self):
        return [int(part) for part in (self.skip.data or '').split(',') if part.strip().isdigit()]
