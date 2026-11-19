from datetime import datetime
import unicodedata
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request, session

from app.decorators import role_required
from app.forms.lot_form import LotForm
from app.models import Lots, Role, User
from app.models.Lots import SchedulingRequired
from app.services.notifications import send_cancellation_email
from app.validations.lots import validate_edit_payload

lots_bp = Blueprint('lots', __name__)
_PUERTO_RICO = ZoneInfo('America/Puerto_Rico')


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
    if isinstance(error, dict) and 'floor_deletions' in error:
        return jsonify(
            message="Confirma cómo deseas eliminar cada piso seleccionado.",
            floor_deletions=error['floor_deletions'],
        ), 409
    if isinstance(error, dict):
        for reservation in error['canceled_reservations']:
            send_cancellation_email(reservation.user, reservation)
        return jsonify(
            message=(
                "El lote y sus pisos se actualizaron correctamente."
                if not error['scheduled_floor_ids']
                else "Los cambios se guardaron y se programó la eliminación del piso."
            ),
            scheduled_floor_ids=error['scheduled_floor_ids'],
            lot=Lots.get_parent_lot_details(lot_id),
        )
    if error == "not_found":
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    if error == "invalid_floor":
        return jsonify(message="Uno o más pisos no pertenecen a este lote."), 422
    if error == "invalid_role":
        return jsonify(message="Uno o más roles no son válidos para los lotes."), 422
    if error == "invalid_floor_deletion_date":
        return jsonify(message="La fecha de eliminación del piso no es válida."), 400
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
    payload = request.get_json(silent=True) or {}
    try:
        result = Lots.request_deletion(
            lot_id,
            override=bool(payload.get('override', False)),
            scheduled_date=payload.get('scheduled_date'),
            confirmed=bool(payload.get('confirmed', False)),
            minimum_token=payload.get('minimum_token'),
        )
    except SchedulingRequired as error:
        preview = Lots.deletion_preview(lot_id)
        if preview is None:
            return jsonify(message="El lote ya no existe."), 404
        return jsonify(
            message=str(error),
            **preview,
        ), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    if result is None:
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    if isinstance(result, dict) and result.get('status') == 'scheduled':
        return jsonify(
            message=(
                "El lote quedó programado para eliminación "
                f"el {result['date_to_be_deleted'].isoformat()}."
            ),
            scheduled=True,
            date_to_be_deleted=result['date_to_be_deleted'].isoformat(),
        )
    return jsonify(
        message=(
            "El lote fue eliminado físicamente junto con sus pisos y espacios."
        ),
        scheduled=False,
    )


@lots_bp.route("/<int:lot_id>/delete/preview", methods=["POST"])
@role_required("admin")
def preview_deletion(lot_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(message="Los datos de verificación no son válidos."), 400
    clicked_at_ms = payload.get('clicked_at_ms')
    clicked_at = None
    if clicked_at_ms is not None:
        if isinstance(clicked_at_ms, bool) or not isinstance(clicked_at_ms, int):
            return jsonify(message="El momento del clic no es válido."), 400
        seconds, milliseconds = divmod(clicked_at_ms, 1000)
        try:
            clicked_at = datetime.fromtimestamp(
                seconds, tz=_PUERTO_RICO
            ).replace(tzinfo=None, microsecond=milliseconds * 1000)
        except (OverflowError, OSError, ValueError):
            return jsonify(message="El momento del clic no es válido."), 400
        if abs((Lots._now() - clicked_at).total_seconds()) > 60:
            return jsonify(
                message="La verificación expiró. Vuelve a pulsar eliminar."
            ), 400
    preview = Lots.deletion_preview(lot_id, clicked_at=clicked_at)
    if preview is None:
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(**preview)


@lots_bp.route("/<int:lot_id>/schedule-deletion", methods=["POST"])
@role_required("admin")
def schedule_deletion(lot_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = Lots.request_deletion(
            lot_id,
            override=False,
            scheduled_date=payload.get('scheduled_date'),
            minimum_token=payload.get('minimum_token'),
        )
    except SchedulingRequired as error:
        preview = Lots.deletion_preview(lot_id)
        if preview is None:
            return jsonify(message="El lote ya no existe."), 404
        return jsonify(
            message=str(error),
            **preview,
        ), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    if result is None:
        return jsonify(message="No existe un lote o piso con ese identificador."), 404
    if isinstance(result, dict) and result.get('status') == 'scheduled':
        deletion_date = result['date_to_be_deleted']
        return jsonify(
            message=(
                "El lote quedó programado para eliminación el "
                f"{deletion_date.isoformat()}."
            ),
            date_to_be_deleted=deletion_date.isoformat(),
        )
    return jsonify(message="El lote se eliminó de inmediato."), 200


@lots_bp.route("/<int:lot_id>/deactivate", methods=["POST"])
@role_required("admin")
def deactivate(lot_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = Lots.request_deactivation(
            lot_id,
            override=bool(payload.get('override', False)),
            scheduled_date=payload.get('scheduled_date'),
        )
    except SchedulingRequired as error:
        return jsonify(
            message=str(error),
            minimum_datetime=error.minimum_date.isoformat(timespec='minutes'),
        ), 409
    except ValueError as error:
        return jsonify(message=str(error)), 400
    if result is None:
        return jsonify(message="No existe un lote o piso con ese identificador."), 404
    if isinstance(result, dict) and result.get('status') == 'scheduled':
        scheduled_date = result['date_to_be_deactivated']
        return jsonify(
            message=(
                "La desactivación quedó programada para "
                f"{scheduled_date.isoformat(timespec='minutes')}."
            ),
            scheduled=True,
            date_to_be_deactivated=scheduled_date.isoformat(timespec='minutes'),
        )
    return jsonify(message="El lote o piso fue desactivado; sus datos se conservaron.")


@lots_bp.route("/<int:lot_id>/activate", methods=["POST"])
@role_required("admin")
def activate(lot_id):
    if not Lots.activate_parent_lot(lot_id):
        return jsonify(message="No existe un lote padre con ese identificador."), 404
    return jsonify(message="El lote fue activado y ya puede aceptar reservaciones.")


@lots_bp.route("/<int:lot_id>/cancel-schedule", methods=["POST"])
@role_required("admin")
def cancel_scheduled_action(lot_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(message="Los datos de la solicitud no son válidos."), 400
    try:
        canceled = Lots.cancel_scheduled_action(
            lot_id, payload.get('action')
        )
    except ValueError as error:
        return jsonify(message=str(error)), 400
    if canceled is None:
        return jsonify(message="No existe un lote con ese identificador."), 404
    if not canceled:
        return jsonify(message="Ese tipo de acción no está programado."), 409
    return jsonify(message="La acción programada fue cancelada.")
