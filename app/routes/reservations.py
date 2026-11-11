from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

from app.database import db
from app.decorators import role_required
from app.forms.reservation_form import ReservationForm
from app.models import Lots, Reservation, Spots, User
from app.services.calendar import build_ics, ics_filename
from app.services.notifications import send_email
from app.services.reservations import (
    ReservationError,
    active_reservations_by_spot,
    can_use_area,
    day_timeline,
    eligible_lots,
    end_choices,
    is_lot_active,
    is_spot_open,
    now,
    reservable_days,
    reserve,
    spot_number,
    spot_state,
    start_choices,
    usable_areas,
)

reservations_bp = Blueprint('reservations', __name__)

_DAYS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
_MONTHS = (
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
)


@reservations_bp.app_template_filter('fecha')
def _format_date(value):
    """martes, 27 de octubre"""
    return f'{_DAYS[value.weekday()]}, {value.day} de {_MONTHS[value.month - 1]}'


@reservations_bp.app_template_filter('fecha_corta')
def _format_short_date(value):
    """mar 27"""
    return f'{_DAYS[value.weekday()][:3]} {value.day}'


@reservations_bp.app_template_filter('hora')
def _format_time(value):
    """9:30 AM"""
    return value.strftime('%I:%M %p').lstrip('0')


def _current_user():
    return db.session.get(User, session['user_id'])


def _open_spots(areas, day):
    return [spot for area in areas for spot in area.spots if is_spot_open(spot, day)]


def _lot_summary(user, lot, current):
    spots = _open_spots(usable_areas(user, lot), current.date())
    ranges = active_reservations_by_spot(
        [spot.id for spot in spots], current, current + timedelta(minutes=1)
    )
    free = [spot for spot in spots if not ranges[spot.id]]
    return {
        'id': lot.id,
        'name': lot.name,
        'location': lot.location,
        'is_paid': bool(lot.is_paid),
        'is_active': bool(lot.is_active),
        'spots': len(spots),
        'free': len(free),
        'accessible_free': sum(1 for spot in free if spot.is_accessible),
    }


def _spot_summary(user, spot, ranges, current):
    return {
        'id': spot.id,
        'number': spot_number(spot),
        'is_accessible': bool(spot.is_accessible),
        'reservable': spot.is_reservable_by(user),
        'state': spot_state(ranges, current),
        'timeline': day_timeline(current.date(), ranges, current),
    }


def _area_summaries(user, lot, current):
    areas = usable_areas(user, lot)
    day_start = current.replace(hour=0, minute=0)
    ranges = active_reservations_by_spot(
        [spot.id for spot in _open_spots(areas, current.date())],
        day_start,
        day_start + timedelta(days=1),
    )
    return [
        {
            'name': area.name,
            'spots': [
                _spot_summary(user, spot, ranges[spot.id], current)
                for spot in sorted(area.spots, key=lambda spot: spot.id)
                if spot.id in ranges
            ],
        }
        for area in areas
    ]


def _chosen_day(days):
    try:
        day = date.fromisoformat(request.args.get('day', ''))
    except ValueError:
        day = None
    return day if day in days else (days[0] if days else None)


def _get_reservable_spot(user, spot_id):
    spot = db.session.get(Spots, spot_id)
    if spot is None or spot.lot is None:
        abort(404)
    if not can_use_area(user, spot.lot):
        abort(403)
    return spot


def _render_spot_form(user, spot, form, error=None, status=200):
    current = now()
    days = reservable_days(current)
    day = _chosen_day(days)
    timeline = []
    if day is not None:
        ranges = active_reservations_by_spot(
            [spot.id],
            current.replace(hour=0, minute=0),
            current.replace(hour=0, minute=0) + timedelta(days=len(days) + 1),
        )[spot.id]
        timeline = day_timeline(day, ranges, current)
        form.set_choices(start_choices(day, current), end_choices(day, current))
    return render_template(
        'reservations/new.html',
        user=user,
        form=form,
        error=error,
        spot=spot,
        number=spot_number(spot),
        lot=spot.lot.parent or spot.lot,
        area=spot.lot,
        lot_active=is_lot_active(spot.lot),
        days=days,
        day=day,
        timeline=timeline,
    ), status


def _get_own_reservation(reservation_id):
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        abort(404)
    if reservation.user_id != session['user_id']:
        abort(403)
    return reservation


@reservations_bp.route('/', methods=['GET'])
@role_required()
def index():
    user = _current_user()
    current = now()
    lots = [_lot_summary(user, lot, current) for lot in eligible_lots(user)]
    # Active lots first, the ones with the most free spots on top (Screen #4).
    lots.sort(key=lambda lot: (not lot['is_active'], -lot['free'], lot['name']))
    return render_template('reservations/index.html', user=user, lots=lots, current=current)


@reservations_bp.route('/lots/<int:lot_id>', methods=['GET'])
@role_required()
def lot(lot_id):
    user = _current_user()
    lot = db.session.get(Lots, lot_id)
    if lot is None or lot.parent_id is not None:
        abort(404)
    if not usable_areas(user, lot):
        abort(403)
    current = now()
    return render_template(
        'reservations/lot.html',
        user=user,
        lot=lot,
        lot_active=bool(lot.is_active),
        areas=_area_summaries(user, lot, current),
        current=current,
    )


@reservations_bp.route('/spots/<int:spot_id>', methods=['GET'])
@role_required()
def new(spot_id):
    user = _current_user()
    spot = _get_reservable_spot(user, spot_id)
    return _render_spot_form(user, spot, ReservationForm())


@reservations_bp.route('/spots/<int:spot_id>', methods=['POST'])
@role_required()
def create(spot_id):
    user = _current_user()
    spot = _get_reservable_spot(user, spot_id)
    form = ReservationForm()
    current = now()
    day = _chosen_day(reservable_days(current))
    if day is not None:
        form.set_choices(start_choices(day, current), end_choices(day, current))

    if not form.validate_on_submit():
        return _render_spot_form(user, spot, form, status=422)

    try:
        reservation = reserve(user, spot.id, form.start, form.end)
    except ReservationError as error:
        return _render_spot_form(user, spot, form, error=str(error), status=422)

    sent = send_email(
        user.email,
        'Tu reservación en MiParking está confirmada',
        'reservation_confirmed',
        attachments=[(ics_filename(reservation), build_ics(reservation), 'text/calendar')],
        user=user,
        reservation=reservation,
        lot=reservation.spot.lot.parent or reservation.spot.lot,
        area=reservation.spot.lot,
        number=spot_number(reservation.spot),
    )
    if sent:
        flash('¡Reservación confirmada! Te enviamos los detalles por correo.', 'success')
    else:
        flash('¡Reservación confirmada! No pudimos enviarte el correo, pero tu reservación está guardada.', 'warning')
    return redirect(url_for('reservations.show', reservation_id=reservation.id))


@reservations_bp.route('/<int:reservation_id>', methods=['GET'])
@role_required()
def show(reservation_id):
    reservation = _get_own_reservation(reservation_id)
    spot = reservation.spot
    return render_template(
        'reservations/show.html',
        user=_current_user(),
        reservation=reservation,
        lot=spot.lot.parent or spot.lot,
        area=spot.lot,
        number=spot_number(spot),
    )


@reservations_bp.route('/<int:reservation_id>/calendar.ics', methods=['GET'])
@role_required()
def calendar(reservation_id):
    reservation = _get_own_reservation(reservation_id)
    return Response(
        build_ics(reservation),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename={ics_filename(reservation)}'},
    )
