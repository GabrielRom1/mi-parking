"""Lot usage reports for SRS REQ.2.4: total reservations, lots ranked by use,
peak occupancy and how often reservations start, for today or the last 7 days."""

from datetime import datetime, time, timedelta

from flask import current_app

from app.models import IncidentReport, Lots, Reservation, Role
from app.services.reservations import day_boundaries, is_lot_active, is_spot_open, now


PERIOD_DAYS = {'today': 1, 'week': 7}
PENDING_INCIDENTS = ('Open', 'In Progress')


class ReportError(Exception):
    """The report filters are invalid. The message explains why."""


# ========== Filters ==========

def parse_filters(args):
    """Read period, lot and role from the query string. Returns (period, lot or None, role name or None)."""
    period = args.get('period') or 'today'
    if period not in PERIOD_DAYS:
        raise ReportError('El periodo debe ser "today" o "week".')

    lot = None
    lot_id = args.get('lot')
    if lot_id:
        if not lot_id.isdigit():
            raise ReportError('El lote no es válido.')
        lot = Lots.get_parent_lot_by_id(int(lot_id))
        if lot is None:
            raise ReportError('El lote no existe.')

    role = args.get('role') or None
    if role and role not in {item.name for item in Role.get_roles_for_lots()}:
        raise ReportError('El rol no es válido.')

    return period, lot, role


# ========== Helpers ==========

def _days(period, current):
    today = current.date()
    return [today - timedelta(days=offset) for offset in reversed(range(PERIOD_DAYS[period]))]


def _slot_minutes():
    return current_app.config['RESERVATION_SLOT_MINUTES']


def _overlap_minutes(reservation, windows):
    """Minutes of the reservation that fall inside the operating hours of the period."""
    total = timedelta()
    for start, end in windows:
        overlap = min(reservation.end_time, end) - max(reservation.start_time, start)
        if overlap > timedelta():
            total += overlap
    return total.total_seconds() / 60


def _ratio(part, whole):
    return round(part / whole, 4) if whole else 0.0


def _minute(moment):
    return moment.strftime('%Y-%m-%dT%H:%M')


# ========== Report ==========

def build_report(period='today', lot=None, role=None, current=None):
    """The usage report as a JSON-ready dict. Times are Puerto Rico time and
    occupancy values are fractions from 0 to 1."""
    current = current or now()
    days = _days(period, current)
    boundaries = [day_boundaries(day) for day in days]
    windows = [(bounds[0], bounds[-1]) for bounds in boundaries]
    window_minutes = sum((end - start).total_seconds() / 60 for start, end in windows)
    period_start = datetime.combine(days[0], time.min)
    period_end = datetime.combine(days[-1] + timedelta(days=1), time.min)

    lots = [lot] if lot else Lots.get_parent_lots()

    # Spots that still existed when the period began, grouped by parent lot.
    # Spots on inactive lots or floors count toward their own lot but not toward the totals.
    spots_by_lot = {}
    active_spots = []
    for parent in lots:
        spots_by_lot[parent.id] = []
        for area in (parent, *parent.floors):
            open_spots = [spot for spot in area.spots if is_spot_open(spot, days[0])]
            spots_by_lot[parent.id].extend(open_spots)
            if is_lot_active(area):
                active_spots.extend(open_spots)

    lot_of_spot = {spot.id: lot_id for lot_id, spots in spots_by_lot.items() for spot in spots}
    active_ids = {spot.id for spot in active_spots}
    accessible_ids = {spot.id for spot in active_spots if spot.is_accessible}

    reservations = Reservation.for_usage_report(list(lot_of_spot), period_start, period_end, role)
    started = [item for item in reservations if period_start <= item.start_time < period_end]

    minutes_by_lot = dict.fromkeys(spots_by_lot, 0.0)
    reserved_by_lot = {lot_id: set() for lot_id in spots_by_lot}
    active_minutes = accessible_minutes = 0.0
    for reservation in reservations:
        minutes = _overlap_minutes(reservation, windows)
        if not minutes:
            continue
        lot_id = lot_of_spot[reservation.spot_id]
        minutes_by_lot[lot_id] += minutes
        reserved_by_lot[lot_id].add(reservation.spot_id)
        if reservation.spot_id in active_ids:
            active_minutes += minutes
        if reservation.spot_id in accessible_ids:
            accessible_minutes += minutes

    accessible_reserved = set().union(*reserved_by_lot.values()) & accessible_ids
    incidents = IncidentReport.count_by_status([item.id for item in started])
    pending = sum(incidents.get(status, 0) for status in PENDING_INCIDENTS)

    return {
        'generated_at': _minute(current),
        'range': {'start': days[0].isoformat(), 'end': days[-1].isoformat()},
        'summary': {
            'total_reservations': len(started),
            'active_lots': sum(1 for parent in lots if parent.is_active),
            'average_occupancy': _ratio(active_minutes, len(active_spots) * window_minutes),
            'active_spots': len(active_spots),
            'peak': _peak(reservations, boundaries, active_ids),
            'accessible_occupancy': (
                _ratio(accessible_minutes, len(accessible_ids) * window_minutes) if accessible_ids else None
            ),
            'accessible_reserved': len(accessible_reserved),
            'accessible_spots': len(accessible_ids),
            'incidents': {
                'total': sum(incidents.values()),
                'pending': pending,
                'resolved': incidents.get('Resolved', 0),
            },
        },
        'ranking': _ranking(lots, spots_by_lot, reserved_by_lot, minutes_by_lot, window_minutes),
        'frequency': _frequency(started, days[0]),
    }


def _ranking(lots, spots_by_lot, reserved_by_lot, minutes_by_lot, window_minutes):
    """Lots from most to least used by average occupancy. Inactive lots go last."""
    rows = []
    for parent in lots:
        capacity = len(spots_by_lot[parent.id])
        rows.append({
            'id': parent.id,
            'name': parent.name,
            'location': parent.location,
            'is_active': bool(parent.is_active),
            'reserved': len(reserved_by_lot[parent.id]),
            'capacity': capacity,
            'occupancy': _ratio(minutes_by_lot[parent.id], capacity * window_minutes),
        })
    rows.sort(key=lambda row: (not row['is_active'], -row['occupancy'], -row['reserved'], row['name'].lower()))
    return rows


def _peak(reservations, boundaries, active_ids):
    """The slot with the most active spots reserved at once. The earliest wins a tie."""
    best = None
    for bounds in boundaries:
        for start, end in zip(bounds, bounds[1:]):
            spots = {
                item.spot_id for item in reservations
                if item.spot_id in active_ids and item.start_time < end and item.end_time > start
            }
            if spots and (best is None or len(spots) > best[2]):
                best = (start, end, len(spots))
    if best is None:
        return None
    start, end, count = best
    return {'start': _minute(start), 'end': _minute(end), 'occupancy': _ratio(count, len(active_ids))}


def _frequency(started, first_day):
    """Reservations that start in each slot of the day, added up over every day of the period."""
    minutes = _slot_minutes()
    starts = day_boundaries(first_day)[:-1]
    opening = starts[0]
    counts = [0] * len(starts)
    for reservation in started:
        offset = reservation.start_time - datetime.combine(reservation.start_time.date(), opening.time())
        index = int(offset.total_seconds() // 60 // minutes)
        if 0 <= index < len(counts):
            counts[index] += 1
    return {
        'slot_minutes': minutes,
        'slots': [{'start': start.strftime('%H:%M'), 'count': count} for start, count in zip(starts, counts)],
    }
