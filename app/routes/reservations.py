from flask import Blueprint, Response, abort, jsonify, render_template, request, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import generate_csrf

from app.database import db
from app.decorators import role_required
from app.forms.quick_find_form import QuickFindForm
from app.forms.reservation_form import ReservationForm
from app.models import Lots, Reservation, Spots, User
from app.services.calendar import build_ics, ics_filename
from app.services.notifications import send_email
from app.services.reservations import (
    ReservationError,
    can_use_area,
    chart_columns,
    default_range,
    eligible_lots,
    floor_number,
    is_lot_active,
    now,
    parse_range,
    reserve,
    spot_grid,
    spot_label,
    usable_areas,
    window_end,
)
from app.services.search import (
    DEFAULT_DURATION,
    DURATION_CHOICES,
    SORT_CHOICES,
    accessible_filter_on,
    quick_find,
    quick_find_range,
    release_holds,
    search_lots,
    starts_now,
)

reservations_bp = Blueprint('reservations', __name__)

_DAYS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
_MONTHS = (
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
)
_ROLE_NAMES = {'estudiante': 'Estudiantes', 'empleado': 'Empleados', 'admin': 'Administradores'}


@reservations_bp.app_template_filter('fecha')
def _format_date(value):
    """martes, 27 de octubre"""
    return f'{_DAYS[value.weekday()]}, {value.day} de {_MONTHS[value.month - 1]}'


@reservations_bp.app_template_filter('fecha_corta')
def _format_short_date(value):
    """mar 27 oct"""
    return f'{_DAYS[value.weekday()][:3]} {value.day} {_MONTHS[value.month - 1][:3]}'


@reservations_bp.app_template_filter('hora')
def _format_time(value):
    """9:30 AM"""
    return value.strftime('%I:%M %p').lstrip('0')


def _current_user():
    return db.session.get(User, session['user_id'])


def _get_lot(user, lot_id):
    """A top-level lot the user can use: 404 if it doesn't exist, 403 if their role can't use it."""
    lot = db.session.get(Lots, lot_id)
    if lot is None or lot.parent_id is not None:
        abort(404)
    if not usable_areas(user, lot):
        abort(403)
    return lot


def _chart_lot(user):
    """The lot picked in the chart's selector, or None for all eligible lots."""
    lot_id = request.args.get('lot', type=int)
    if lot_id is None:
        return None
    lot = db.session.get(Lots, lot_id)
    return lot if lot in eligible_lots(user) else None


def _accessible_only(user):
    """The "Solo espacios accesibles" checkbox, ignored for users who aren't offered it."""
    return accessible_filter_on(user, request.args.get('accessible'))


def _quick_find_form(user):
    form = QuickFindForm()
    form.lot.choices = [('', 'Cualquier lote')] + [
        (str(lot.id), lot.name) for lot in eligible_lots(user) if is_lot_active(lot)
    ]
    form.duration.choices = DURATION_CHOICES
    if form.duration.data is None:
        form.duration.data = DEFAULT_DURATION
    return form


@reservations_bp.route('/', methods=['GET'])
@role_required()
def index():
    user = _current_user()
    current = now()
    start, end = default_range(current)
    return render_template(
        'reservations/index.html',
        user=user,
        role_name=_ROLE_NAMES.get(user.role.name) if user.role else None,
        columns=chart_columns(user, current=current),
        lots=search_lots(user, start, end) if start else [],
        all_lots=eligible_lots(user),
        sort_choices=SORT_CHOICES,
        csrf=generate_csrf(),  # for the Quick Find requests the page sends without a form
        accessible_filter=bool(user.requires_accessible_spot),
        chart_lot=None,
        window_end=window_end(current),
        start=start,
        end=end,
    )


@reservations_bp.route('/chart', methods=['GET'])
@role_required()
def chart():
    user = _current_user()
    lot = _chart_lot(user)
    return render_template(
        'reservations/include/chart.html',
        columns=chart_columns(user, lot, accessible_only=_accessible_only(user)),
        chart_lot=lot,
    )


@reservations_bp.route('/lots', methods=['GET'])
@role_required()
def lots():
    user = _current_user()
    start, end = parse_range(request.args)
    query = request.args.get('q', '')
    lots = search_lots(
        user, start, end,
        query=query,
        order=request.args.get('sort', 'available'),
        accessible_only=_accessible_only(user),
    ) if start else []
    return render_template(
        'reservations/include/lots.html',
        lots=lots,
        searching=bool(query.strip()) or _accessible_only(user),
        chart_lot=_chart_lot(user),
        start=start,
        end=end,
    )


@reservations_bp.route('/lots/<int:lot_id>/spots', methods=['GET'])
@role_required()
def choose_spot(lot_id):
    user = _current_user()
    lot = _get_lot(user, lot_id)
    start, end = parse_range(request.args)
    return render_template(
        'reservations/include/choose_spot.html',
        lot=lot,
        floors=spot_grid(user, lot, start, end, accessible_only=_accessible_only(user)),
        lot_active=is_lot_active(lot),
        selected=request.args.get('spot', type=int),
        start=start,
        end=end,
    )


@reservations_bp.route('/spots/<int:spot_id>/confirm', methods=['GET'])
@role_required()
def confirm(spot_id):
    user = _current_user()
    spot = db.session.get(Spots, spot_id)
    if spot is None or spot.lot is None:
        abort(404)
    if not can_use_area(user, spot.lot):
        abort(403)
    start, end = parse_range(request.args)
    form = ReservationForm(data={'spot_id': spot.id, 'start_time': start, 'end_time': end})
    return render_template(
        'reservations/include/confirm.html',
        form=form,
        spot=spot,
        label=spot_label(spot),
        floor=floor_number(spot.lot),
        lot=spot.lot.parent or spot.lot,
        start=start,
        end=end,
    )


@reservations_bp.route('/', methods=['POST'])
@role_required()
def create():
    user = _current_user()
    form = ReservationForm()
    if not form.validate():
        if 'csrf_token' in form.errors:
            message = 'Tu sesión expiró. Recarga la página e inténtalo de nuevo.'
        else:
            message = 'Escoge un espacio y un horario en la gráfica e inténtalo de nuevo.'
        return jsonify(message=message), 422

    try:
        reservation = reserve(user, form.spot_id.data, form.start_time.data, form.end_time.data)
    except ReservationError as error:
        return jsonify(message=str(error)), 422

    spot = reservation.spot
    details = {
        'reservation': reservation,
        'lot': spot.lot.parent or spot.lot,
        'label': spot_label(spot),
        'floor': floor_number(spot.lot),
    }
    email_sent = send_email(
        user.email,
        'Tu reservación en MiParking está confirmada',
        'reservation_confirmed',
        attachments=[(ics_filename(reservation), build_ics(reservation), 'text/calendar')],
        user=user,
        **details,
    )
    return jsonify(
        html=render_template(
            'reservations/include/confirmed.html', user=user, email_sent=email_sent, **details
        ),
    ), 201


@reservations_bp.route('/<int:reservation_id>/calendar.ics', methods=['GET'])
@role_required()
def calendar(reservation_id):
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        abort(404)
    if reservation.user_id != session['user_id']:
        abort(403)
    return Response(
        build_ics(reservation),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename={ics_filename(reservation)}'},
    )


@reservations_bp.route('/quick-find', methods=['POST'])
@role_required()
def quick_find_result():
    """The Quick Find dialog with the best spot for the user, held for them (SRS REQ.5.1, Figma "4 · Quick Find").

    The page posts here when the dialog opens and whenever its fields change;
    "Buscar otro" posts again with the spots already shown in `skip`.
    """
    user = _current_user()
    form = _quick_find_form(user)
    if not form.validate_on_submit():
        message = (
            'Tu sesión expiró. Recarga la página e inténtalo de nuevo.'
            if 'csrf_token' in form.errors
            else 'Revisa los campos e inténtalo de nuevo.'
        )
        return render_template('reservations/include/quick_find.html', form=form, error=message), 422

    if form.start_time.data and form.end_time.data:
        start, end = form.start_time.data, form.end_time.data
    else:
        start, end = quick_find_range(form.duration.data or DEFAULT_DURATION)
    preferred = db.session.get(Lots, int(form.lot.data)) if form.lot.data else None

    suggestion = None
    error = None
    if start is not None:
        try:
            suggestion = quick_find(user, start, end, preferred, form.skipped_ids())
        except ReservationError as exc:
            error = str(exc)

    lot, spot = suggestion or (None, None)
    return render_template(
        'reservations/include/quick_find.html',
        form=form,
        chart_range=bool(form.start_time.data and form.end_time.data),
        starts_now=starts_now(start) if start else False,
        lot=lot,
        spot=spot,
        label=spot_label(spot) if spot else None,
        floor=floor_number(spot.lot) if spot else None,
        start=start,
        end=end,
        error=error,
        skip=','.join(str(spot_id) for spot_id in [*form.skipped_ids(), *([spot.id] if spot else [])]),
    )


@reservations_bp.route('/quick-find/release', methods=['POST'])
@role_required()
def quick_find_release():
    """Free the user's Quick Find hold when they close the suggestion without reserving."""
    if not FlaskForm().validate_on_submit():  # only the CSRF token
        abort(400)
    release_holds(_current_user())
    return '', 204
