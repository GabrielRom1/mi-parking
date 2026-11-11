"""Reservation rules for SRS REQ.3.1: who can use which lot, the time slots
offered in the dropdowns, spot availability, and creating a reservation."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from app.database import db
from app.models import Lots, Reservation, Spots


# Reservation times are saved without a time zone and always mean Puerto Rico time.
PUERTO_RICO = ZoneInfo('America/Puerto_Rico')


class ReservationError(Exception):
    """A reservation was rejected. The message is shown to the user."""


# ========== Setup ========== 

def now():
    """Current Puerto Rico time, without the time zone, the same way reservation times are saved."""
    return datetime.now(PUERTO_RICO).replace(tzinfo=None, second=0, microsecond=0)


def _slot():
    return timedelta(minutes=current_app.config['RESERVATION_SLOT_MINUTES'])


def _window_end(current):
    return current + timedelta(hours=current_app.config['RESERVATION_WINDOW_HOURS'])


def _opening(day):
    return datetime.combine(day, time(current_app.config['RESERVATION_OPENING_HOUR']))


def _closing(day):
    return datetime.combine(day, time(current_app.config['RESERVATION_CLOSING_HOUR']))


# ========== Eligibility ==========

def can_use_area(user, area):
    """Admins can reserve anywhere. Others need a role, and the lot or floor must be open to it."""
    if user.role is None:
        return False
    if user.role.name == 'admin':
        return True
    return area.role_id is None or area.role_id == user.role_id


def is_lot_active(area):
    """A floor is only active if its parent lot is active too."""
    return bool(area.is_active) and (area.parent is None or bool(area.parent.is_active))


def usable_areas(user, lot):
    """The lot itself and its floors that have spots and are open to the user."""
    return [
        area for area in (lot, *lot.floors)
        if area.spots and can_use_area(user, area)
    ]


def eligible_lots(user):
    """Top-level lots with at least one area the user may reserve in, including inactive ones."""
    lots = Lots.query.filter(Lots.parent_id.is_(None)).order_by(Lots.name).all()
    return [lot for lot in lots if usable_areas(user, lot)]


def is_spot_open(spot, day):
    return spot.date_to_be_deleted is None or spot.date_to_be_deleted > day


# ========== Time slots ==========

def day_boundaries(day):
    """Every slot boundary from opening to closing on `day`, both included."""
    boundaries = []
    moment, closing = _opening(day), _closing(day)
    while moment <= closing:
        boundaries.append(moment)
        moment += _slot()
    return boundaries


def start_choices(day, current=None):
    current = current or now()
    window_end = _window_end(current)
    return [
        moment for moment in day_boundaries(day)[:-1]
        if current < moment < window_end
    ]


def end_choices(day, current=None):
    current = current or now()
    return [moment for moment in day_boundaries(day)[1:] if moment > current]


def reservable_days(current=None):
    """Days within the reservation window that still have a start time left."""
    current = current or now()
    days = []
    day = current.date()
    while day <= _window_end(current).date():
        if start_choices(day, current):
            days.append(day)
        day += timedelta(days=1)
    return days


# ========== Availability ==========

def active_reservations_by_spot(spot_ids, start, end):
    """{spot_id: [(start_time, end_time), ...]} for active reservations between start and end."""
    ranges = {spot_id: [] for spot_id in spot_ids}
    if not spot_ids:
        return ranges
    reservations = (
        Reservation.active_overlapping(start, end)
        .filter(Reservation.spot_id.in_(spot_ids))
        .order_by(Reservation.start_time)
        .all()
    )
    for reservation in reservations:
        ranges[reservation.spot_id].append((reservation.start_time, reservation.end_time))
    return ranges


def _is_taken(ranges, start, end):
    return any(start < taken_end and taken_start < end for taken_start, taken_end in ranges)


def day_timeline(day, ranges, current=None):
    """One entry per slot of the day: 'past', 'reserved', 'beyond' (outside the window) or 'free'."""
    current = current or now()
    window_end = _window_end(current)
    timeline = []
    for start in day_boundaries(day)[:-1]:
        end = start + _slot()
        if start <= current:
            state = 'past'
        elif _is_taken(ranges, start, end):
            state = 'reserved'
        elif start >= window_end:
            state = 'beyond'
        else:
            state = 'free'
        timeline.append({'start': start, 'end': end, 'state': state})
    return timeline


def spot_state(ranges, current=None):
    """'reserved' if taken right now, 'full' if no free slot is left today, else 'available'."""
    current = current or now()
    if _is_taken(ranges, current, current + timedelta(minutes=1)):
        return 'reserved'
    if not any(slot['state'] == 'free' for slot in day_timeline(current.date(), ranges, current)):
        return 'full'
    return 'available'


# ========== Creating a reservation ==========

def _validate_times(start, end, current):
    if end <= start:
        raise ReservationError('La hora de salida debe ser después de la hora de entrada.')
    if start <= current:
        raise ReservationError('La hora de entrada debe ser en el futuro.')
    if start >= _window_end(current):
        hours = current_app.config['RESERVATION_WINDOW_HOURS']
        raise ReservationError(f'Solo puedes reservar dentro de las próximas {hours} horas.')
    if start.date() != end.date() or start < _opening(start.date()) or end > _closing(start.date()):
        opening = current_app.config['RESERVATION_OPENING_HOUR']
        closing = current_app.config['RESERVATION_CLOSING_HOUR']
        raise ReservationError(
            f'Las reservaciones deben estar entre las {opening}:00 y las {closing}:00 del mismo día.'
        )
    slot_minutes = current_app.config['RESERVATION_SLOT_MINUTES']
    if start.minute % slot_minutes or end.minute % slot_minutes:
        raise ReservationError(f'Escoge horas en intervalos de {slot_minutes} minutos.')


def _validate_spot(user, spot, start):
    if spot is None or spot.lot is None:
        raise ReservationError('Ese espacio no existe.')
    if not can_use_area(user, spot.lot):
        raise ReservationError('Tu rol no tiene acceso a este lote.')
    if not is_lot_active(spot.lot):
        raise ReservationError('Este lote está inactivo y no acepta reservaciones.')
    if not is_spot_open(spot, start.date()):
        raise ReservationError('Este espacio no está disponible para esa fecha.')
    if not spot.is_reservable_by(user):
        raise ReservationError('Este espacio está reservado para personas que necesitan un espacio accesible.')


def reserve(user, spot_id, start, end):
    """Create an active reservation, or raise ReservationError with the reason.

    Covers SRS REQ.3.1 step 4: the user has no other reservation at that time,
    the start is in the future, the end is after the start, and nobody else
    has reserved the spot for that time.
    """
    current = now()
    _validate_times(start, end, current)
    spot = db.session.get(Spots, spot_id)
    _validate_spot(user, spot, start)

    # Take the database write lock before checking for overlaps, so two people
    # reserving the same spot at once can't both pass the check.
    db.session.execute(
        db.update(Spots).where(Spots.id == spot.id).values(id=Spots.id)
    )
    try:
        overlapping = Reservation.active_overlapping(start, end)
        if overlapping.filter(Reservation.user_id == user.id).first() is not None:
            raise ReservationError('Ya tienes una reservación en ese horario.')
        if overlapping.filter(Reservation.spot_id == spot.id).first() is not None:
            raise ReservationError('Este espacio ya está reservado en ese horario. Escoge otro horario u otro espacio.')

        reservation = Reservation.create(user, spot, start, end)
        db.session.add(reservation)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return reservation


# ========== Display helpers ==========

def spot_number(spot):
    """Spots have no label, so number them 1..n within their lot or floor."""
    ordered = sorted(spot.lot.spots, key=lambda other: other.id)
    return ordered.index(spot) + 1
