from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, current_app, flash, jsonify, render_template, request, session
from itsdangerous import BadData, URLSafeTimedSerializer

from app.database import db
from app.decorators import role_required
from app.forms.reservation_form import CheckoutActionForm, ReservationForm
from app.models import Lots, Reservation, Spots, User
from app.services.calendar import build_ics, ics_filename
from app.services.notifications import checkout_action_url, send_email
from app.services.reservations import (
    ReservationError,
    can_use_area,
    check_out_reservation,
    chart_columns,
    default_range,
    extend_reservation,
    extension_available,
    eligible_lots,
    floor_number,
    is_lot_active,
    lot_summaries,
    now,
    parse_range,
    reserve,
    spot_grid,
    spot_label,
    usable_areas,
    window_end,
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
        lots=lot_summaries(user, start, end) if start else [],
        all_lots=eligible_lots(user),
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
        columns=chart_columns(user, lot),
        chart_lot=lot,
    )


@reservations_bp.route('/lots', methods=['GET'])
@role_required()
def lots():
    user = _current_user()
    start, end = parse_range(request.args)
    return render_template(
        'reservations/include/lots.html',
        lots=lot_summaries(user, start, end) if start else [],
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
        floors=spot_grid(user, lot, start, end),
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


def _reservation_from_checkout_token(token):
    serializer = URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        salt='reservation-checkout',
    )
    try:
        payload = serializer.loads(
            token,
        )
    except BadData:
        abort(404)

    if (
        not isinstance(payload, dict)
        or type(payload.get('reservation_id')) is not int
        or type(payload.get('user_id')) is not int
        or not isinstance(payload.get('end_time'), str)
        or payload.get('action') not in ('checkout', 'extend')
    ):
        abort(404)
    try:
        expected_end = datetime.fromisoformat(payload['end_time'])
    except ValueError:
        abort(404)

    reservation = db.session.get(Reservation, payload['reservation_id'])
    if (
        reservation is None
        or reservation.user_id != payload['user_id']
        or reservation.end_time != expected_end
    ):
        abort(404)
    return reservation, expected_end, payload['action']


@reservations_bp.route('/checkout/<token>', methods=['GET', 'POST'])
def checkout_action(token):
    reservation, expected_end, token_action = _reservation_from_checkout_token(token)
    action = request.args.get('action', 'checkout')
    if action != token_action:
        abort(400)
    current = now()
    if token_action == 'extend' and current >= expected_end:
        abort(404)
    checkout_deadline = expected_end + timedelta(
        minutes=current_app.config['RESERVATION_CHECKOUT_GRACE_MINUTES']
    )
    if token_action == 'checkout' and current >= checkout_deadline:
        abort(404)
    if token_action == 'extend' and reservation.checkout_reminder_sent_at is None:
        abort(404)
    form = CheckoutActionForm()

    if request.method == 'POST':
        if not form.validate_on_submit():
            abort(400)
        if request.form.get('action') != token_action:
            abort(400)
        action = token_action
        if action == 'checkout':
            try:
                check_out_reservation(reservation)
            except ReservationError as error:
                flash(str(error), 'error')
            else:
                flash('Tu salida quedó confirmada. ¡Gracias!', 'success')
            return render_template(
                'reservations/checkout.html',
                reservation=reservation,
                action='checkout',
                form=form,
                can_extend=extension_available(
                    reservation, expected_end=expected_end
                ),
                extension_url=(
                    checkout_action_url(reservation, 'extend')
                    if extension_available(
                        reservation, expected_end=expected_end
                    )
                    else None
                ),
                checked_out=reservation.check_out_time is not None,
            )
        if action == 'extend':
            try:
                extend_reservation(reservation, expected_end)
            except ReservationError as error:
                db.session.rollback()
                flash(str(error), 'error')
            else:
                flash(
                    'Tu reservación se extendió por un bloque adicional.',
                    'success',
                )
            return render_template(
                'reservations/checkout.html',
                reservation=reservation,
                action='extend',
                form=form,
                can_extend=extension_available(
                    reservation, expected_end=expected_end
                ),
                extension_url=None,
                checked_out=reservation.check_out_time is not None,
            )
        abort(400)

    return render_template(
        'reservations/checkout.html',
        reservation=reservation,
        action=action,
        form=form,
        can_extend=extension_available(
            reservation, expected_end=expected_end
        ),
        extension_url=(
            checkout_action_url(reservation, 'extend')
            if token_action == 'checkout'
            and extension_available(reservation, expected_end=expected_end)
            else None
        ),
        checked_out=reservation.check_out_time is not None,
    )
