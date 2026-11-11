from flask_wtf import FlaskForm
from wtforms import BooleanField, FieldList, Form, FormField, IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, ValidationError

from app.models import Lots


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class FloorForm(Form):
    class Meta:
        # WTForms' built-in messages (e.g. a non-numeric value).
        locales = ["es"]

    capacity = IntegerField(
        "Capacidad del piso",
        validators=[
            InputRequired(message="Introduce la capacidad del piso."),
            NumberRange(min=0, message="Introduce 0 o más."),
        ],
    )

    accessible_capacity = IntegerField(
        "Capacidad accesible",
        validators=[
            InputRequired(message="Introduce la capacidad accesible."),
            NumberRange(min=0, message="Introduce 0 o más."),
        ],
    )

    role_id = SelectField(
        "Tipo de rol",
        coerce=int,
        validators=[InputRequired(message="Selecciona un rol.")],
    )

    def validate_accessible_capacity(self, field):
        if self.capacity.errors or field.data is None:
            return  # An invalid value is already reported; there's nothing to compare.

        capacity = self.capacity.data
        if field.data > capacity:
            raise ValidationError(f"No puede exceder la capacidad del piso ({capacity}).")


class LotForm(FlaskForm):
    name = StringField(
        "Nombre del lote",
        filters=[_strip],
        validators=[
            DataRequired(message="Introduce el nombre del lote."),
            Length(max=100, message="Usa 100 caracteres o menos."),
        ],
    )

    location = StringField(
        "Ubicación",
        filters=[_strip],
        validators=[
            DataRequired(message="Introduce la ubicación."),
            Length(max=255, message="Usa 255 caracteres o menos."),
        ],
    )

    # A checkbox always submits a value (checked or not), so "required" holds.
    is_paid = BooleanField("Lote pago")

    floors = FieldList(FormField(FloorForm))

    def __init__(self, *args, role_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        for floor in self.floors:
            floor.form.role_id.choices = list(role_choices)

    def validate_name(self, field):
        if field.data and Lots.get_lot_by_name(field.data) is not None:
            raise ValidationError(
                f"Ya existe un lote llamado “{field.data}”. Los nombres de los lotes deben ser únicos."
            )

    def field_errors(self):
        """Return {input name: first error message}, including the floor fields."""
        lot_fields = [field for field in self if field is not self.floors]
        floor_fields = [field for entry in self.floors for field in entry.form]
        return {field.name: field.errors[0] for field in lot_fields + floor_fields if field.errors}
