import unicodedata

from flask import Blueprint, jsonify, render_template, request, session

from app.decorators import role_required
from app.forms.lot_form import LotForm
from app.models import Lots, Role, User
from app.validations.lots import validate_edit_payload

lots_bp = Blueprint('lots', __name__)


def _sort_key(name):
    """Case- and accent-insensitive. lots.js compares these same keys when inserting a row."""
    decomposed = unicodedata.normalize('NFD', name.casefold())
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def _role_label(role):
    return role.name.title()


def _role_choices():
    """Return selectable roles, excluding administrators."""
    return [("", "Sin rol")] + [
        (role.id, _role_label(role)) for role in Role.get_roles_for_lots()
    ]


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _validation_message(errors):
    if "csrf_token" in errors:
        return "Tu sesión expiró. Recarga la página e inténtalo de nuevo."
    if errors.get("name", "").startswith("Ya existe"):
        return errors["name"]
    if len(errors) == 1:
        return "Corrige el campo marcado e inténtalo de nuevo."
    return f"Corrige los {len(errors)} campos marcados e inténtalo de nuevo."


def _created_message(summary):
    if not summary["floors"]:
        return f"{summary['name']} se creó como un lote vacío."
    return (
        f"{summary['name']} se creó con "
        f"{_plural(summary['floors'], 'piso')} y "
        f"{_plural(summary['spots'], 'espacio')}."
    )


@lots_bp.route("/", methods=["GET"])
@role_required("admin")
def index():
    user = User.get_user_by_id(session["user_id"])
    return render_template(
        "lots/index.html",
        user=user,
        form=LotForm(),
        role_options=_role_choices(),
    )


@lots_bp.route("/rows", methods=["GET"])
@role_required("admin")
def rows():
    lots = Lots.get_parent_lot_summaries()
    lots.sort(key=lambda lot: _sort_key(lot["name"]))
    return render_template("lots/include/rows.html", lots=lots)


@lots_bp.route("/", methods=["POST"])
@role_required("admin")
def create():
    form = LotForm(role_choices=_role_choices())
    if not form.validate():
        errors = form.field_errors()
        return jsonify(errors=errors, message=_validation_message(errors)), 422

    lot = Lots.create_parent_lot(
        name=form.name.data,
        location=form.location.data,
        is_paid=form.is_paid.data,
        floors=form.floors.data,
    )
    if lot is None:
        return jsonify(
            message="No se pudo guardar el lote. Inténtalo de nuevo en un momento."
        ), 500

    summary = Lots.get_parent_lot_summaries([lot])[0]
    return jsonify(
        message=_created_message(summary),
        row_html=render_template("lots/include/row.html", lot=summary),
    ), 201


@lots_bp.route("/<int:lot_id>", methods=["GET"])
@role_required("admin")
def edit(lot_id):
    lot = Lots.get_parent_lot_details(lot_id)
    if lot is None:
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(lot=lot)


@lots_bp.route("/<int:lot_id>", methods=["PUT", "PATCH"])
@role_required("admin")
def update(lot_id):
    if not request.is_json:
        return jsonify(message="Envía los cambios como JSON."), 415

    payload, errors = validate_edit_payload(request.get_json())
    if errors:
        return jsonify(errors=errors, message="Corrige los datos del lote."), 422

    error = Lots.update_parent_lot(lot_id, payload)
    if error == "not_found":
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    if error == "invalid_floor":
        return jsonify(message="Uno o más pisos no pertenecen a este lote."), 422
    if error == "invalid_role":
        return jsonify(message="Uno o más roles no son válidos para los lotes."), 422
    if error == "reserved_floor":
        return jsonify(message="No se puede eliminar un piso con reservaciones."), 409
    if error == "reserved_capacity":
        return jsonify(
            message=(
                "No se puede reducir la capacidad ni cambiar el tipo de espacios "
                "que tienen reservaciones."
            )
        ), 409
    if error == "duplicate_name":
        return jsonify(
            message="El nombre del lote o de uno de sus pisos ya existe."
        ), 409

    return jsonify(
        message="El lote y sus pisos se actualizaron correctamente.",
        lot=Lots.get_parent_lot_details(lot_id),
    )


@lots_bp.route("/<int:lot_id>/delete", methods=["POST"])
@role_required("admin")
def delete(lot_id):
    deleted_reservations = Lots.delete_parent_lot(lot_id)
    if deleted_reservations is None:
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(
        message=(
            "El lote fue eliminado físicamente junto con sus pisos, espacios, "
            "reservaciones e informes relacionados "
            f"({deleted_reservations} reservaciones)."
        )
    )


@lots_bp.route("/<int:lot_id>/schedule-deletion", methods=["POST"])
@role_required("admin")
def schedule_deletion(lot_id):
    deletion_date = Lots.schedule_parent_deletion(lot_id)
    if deletion_date is None:
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(
        message=(
            "El lote quedó programado para eliminación el "
            f"{deletion_date.isoformat()}."
        ),
        date_to_be_deleted=deletion_date.isoformat(),
    )


@lots_bp.route("/<int:lot_id>/deactivate", methods=["POST"])
@role_required("admin")
def deactivate(lot_id):
    if not Lots.deactivate_parent_lot(lot_id):
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(message="El lote fue desactivado; sus datos se conservaron.")
