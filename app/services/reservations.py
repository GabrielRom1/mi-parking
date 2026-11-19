"""Reservation rules for SRS REQ.3.1: who can use which lot, the time slots
shown on the availability chart, spot availability, and creating a reservation."""

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


def slot_starts(day):
    """The start of every slot on `day`."""
    return day_boundaries(day)[:-1]


def slot_state(start, current):
    """'past' (already started), 'beyond' (outside the reservation window) or 'open'."""
    if start <= current:
        return 'past'
    if start >= _window_end(current):
        return 'beyond'
    return 'open'


def window_days(current=None):
    """The chart's columns: today, then every day that opens before the window ends."""
    current = current or now()
    window_end = _window_end(current)
    days = [current.date()]
    day = current.date() + timedelta(days=1)
    while _opening(day) < window_end:
        days.append(day)
        day += timedelta(days=1)
    return days


def window_end(current=None):
    return _window_end(current or now())


def default_range(current=None):
    """The first open slot, for an hour (or until closing). None if nothing is open."""
    current = current or now()
    for day in window_days(current):
        for start in slot_starts(day):
            if slot_state(start, current) == 'open':
                return start, min(start + timedelta(hours=1), _closing(day))
    return None, None


def parse_range(values, current=None):
    """`start`/`end` ISO datetimes from a request, or the default range if missing or invalid.

    This only reads the values; reserve() still validates them before saving.
    """
    try:
        start = datetime.fromisoformat(values['start'])
        end = datetime.fromisoformat(values['end'])
    except (KeyError, TypeError, ValueError):
        return default_range(current)
    return start, end


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


def _open_spots(areas, day):
    return [
        spot for area in areas if is_lot_active(area)
        for spot in sorted(area.spots, key=lambda spot: spot.id)
        if is_spot_open(spot, day)
    ]


def chart_columns(user, lot=None, current=None):
    """One column per day for the availability chart, with how many spots are free in each slot.

    Counts the spots of `lot`, or of every lot the user can use. A cell's
    `level` (0-4) sets its shade: 0 means no free spot, 4 means most are free.
    """
    current = current or now()
    lots = [lot] if lot is not None else eligible_lots(user)
    areas = [area for each in lots for area in usable_areas(user, each)]
    days = window_days(current)
    all_spots = _open_spots(areas, days[0])
    ranges = active_reservations_by_spot(
        [spot.id for spot in all_spots], _opening(days[0]), _closing(days[-1])
    )

    columns = []
    for day in days:
        spots = [spot for spot in all_spots if is_spot_open(spot, day)]
        cells = []
        for start in slot_starts(day):
            end = start + _slot()
            free = sum(1 for spot in spots if not _is_taken(ranges[spot.id], start, end))
            if not free:
                level = 0
            else:
                level = min(4, 1 + free * 4 // len(spots))
            cells.append({
                'start': start,
                'end': end,
                'state': slot_state(start, current),
                'free': free,
                'total': len(spots),
                'level': level,
            })
        columns.append({'day': day, 'cells': cells})
    return columns


def lot_summary(user, lot, start, end):
    """A lot card for the chosen time: its spots, and how many are free for the whole time."""
    spots = _open_spots(usable_areas(user, lot), start.date()) if is_lot_active(lot) else []
    ranges = active_reservations_by_spot([spot.id for spot in spots], start, end)
    free = [spot for spot in spots if not ranges[spot.id]]
    return {
        'id': lot.id,
        'name': lot.name,
        'location': lot.location,
        'is_paid': bool(lot.is_paid),
        'is_active': is_lot_active(lot),
        'spots': len(spots),
        'free': len(free),
        'accessible_free': sum(1 for spot in free if spot.is_accessible),
    }


def lot_summaries(user, start, end):
    """Cards for every lot the user can use, active ones first, most free spots on top."""
    lots = [lot_summary(user, lot, start, end) for lot in eligible_lots(user)]
    lots.sort(key=lambda lot: (not lot['is_active'], -lot['free'], lot['name']))
    return lots


def spot_grid(user, lot, start, end, current=None):
    """The floors of `lot` the user can use, each with its spots for the chosen time.

    A spot is 'available' if it's free for the whole time, 'reserved' if
    someone has part of it, or 'full' if that day has no free slot left.
    Only available spots the user is allowed to take are selectable.
    """
    current = current or now()
    day = start.date()
    areas = [area for area in usable_areas(user, lot) if is_lot_active(area)]
    spots = _open_spots(areas, day)
    ranges = active_reservations_by_spot([spot.id for spot in spots], _opening(day), _closing(day))

    floors = []
    for area in areas:
        tiles = []
        for spot in (spot for spot in spots if spot.lot_id == area.id):
            if not _is_taken(ranges[spot.id], start, end):
                state = 'available'
            elif any(slot['state'] == 'free' for slot in day_timeline(day, ranges[spot.id], current)):
                state = 'reserved'
            else:
                state = 'full'
            tiles.append({
                'id': spot.id,
                'label': spot_label(spot),
                'state': state,
                'is_accessible': bool(spot.is_accessible),
                'selectable': state == 'available' and spot.is_reservable_by(user),
            })
        floors.append({
            'number': floor_number(area),
            'free': sum(1 for tile in tiles if tile['state'] == 'available'),
            'spots': tiles,
        })
    return floors


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

def floor_number(area):
    """Floors are child lots, numbered 1..n in the order they were created. A lot without floors is floor 1."""
    if area.parent is None:
        return 1
    floors = sorted(area.parent.floors, key=lambda floor: floor.id)
    return floors.index(area) + 1


def spot_label(spot):
    """Spots have no label column, so they're named <floor>-<number>, like 2-21 (SDS Option B)."""
    ordered = sorted(spot.lot.spots, key=lambda other: other.id)
    return f'{floor_number(spot.lot)}-{ordered.index(spot) + 1:02d}'
