from flask_wtf import FlaskForm
from wtforms import BooleanField, FieldList, Form, FormField, IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, ValidationError

from app.models import Lots

# Guard rails so a typo can't create millions of spot rows in one request.
MAX_FLOOR_CAPACITY = 2000
MAX_FLOORS = 20


class FloorForm(Form):
    class Meta:
        # WTForms' built-in messages (e.g. a non-numeric value).
        locales = ["es"]

    capacity = IntegerField(
        "Capacidad del piso",
        validators=[
            InputRequired(message="Introduce la capacidad del piso."),
            NumberRange(
                min=0,
                max=MAX_FLOOR_CAPACITY,
                message=f"Introduce un número del 0 al {MAX_FLOOR_CAPACITY}.",
            ),
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
        validate_choice=True,
        validators=[InputRequired(message="Selecciona un rol.")],
    )

    def validate_accessible_capacity(self, field):
        capacity = self.capacity.data
        if (
            field.data is not None
            and capacity is not None
            and not self.capacity.errors
            and field.data > capacity
        ):
            raise ValidationError(f"No puede exceder la capacidad del piso ({capacity}).")


class LotForm(FlaskForm):
    name = StringField(
        "Nombre del lote",
        filters=[lambda value: value.strip() if isinstance(value, str) else value],
        validators=[
            DataRequired(message="Introduce el nombre del lote."),
            Length(max=100, message="Usa 100 caracteres o menos."),
        ],
    )

    location = StringField(
        "Ubicación",
        filters=[lambda value: value.strip() if isinstance(value, str) else value],
        validators=[
            DataRequired(message="Introduce la ubicación."),
            Length(max=255, message="Usa 255 caracteres o menos."),
        ],
    )

    # A checkbox always submits a value (checked or not), so "required" holds.
    is_paid = BooleanField("Lote pago")

    floors = FieldList(FormField(FloorForm), min_entries=0, max_entries=MAX_FLOORS)

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
        """Flatten errors to {input name: first message}, including floor fields."""
        errors = {}
        for field in self:
            if isinstance(field, FieldList):
                for entry in field.entries:
                    for subfield in entry.form:
                        if subfield.errors:
                            errors[subfield.name] = subfield.errors[0]
            elif field.errors:
                errors[field.name] = field.errors[0]
        return errors
