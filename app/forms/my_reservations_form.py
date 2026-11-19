from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import Length, Optional


class CancelReservationForm(FlaskForm):
    """SRS REQ.3.2. Reason: text field, optional."""

    reason = TextAreaField('Razón (opcional)', validators=[Optional(), Length(max=500)])


class CheckOutForm(FlaskForm):
    """SRS REQ.3.3. No fields, it only carries the CSRF token."""

    # TODO REQ.3.3: "Duration Extension" dropdown for the new end time (optional field).
