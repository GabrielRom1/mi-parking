from flask_wtf import FlaskForm
from wtforms import DateTimeField, IntegerField
from wtforms.validators import DataRequired
from wtforms.widgets import HiddenInput


class ReservationForm(FlaskForm):
    """The spot and time picked on the Reserve page (SRS REQ.3.1). The page fills these in; the user never types them."""

    spot_id = IntegerField(widget=HiddenInput(), validators=[DataRequired()])
    start_time = DateTimeField(format='%Y-%m-%dT%H:%M', widget=HiddenInput(), validators=[DataRequired()])
    end_time = DateTimeField(format='%Y-%m-%dT%H:%M', widget=HiddenInput(), validators=[DataRequired()])


class CheckoutActionForm(FlaskForm):
    """CSRF protection for signed-link checkout and extension confirmations."""
