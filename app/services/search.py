"""Spot search for SRS Feature 5: searching and sorting the lot list (REQ.5.2)
and Quick Find (REQ.5.1). Availability itself comes from services/reservations."""

import unicodedata
from datetime import timedelta

from flask import current_app

from app.database import db
from app.models import Reservation, SpotHold, Spots
from app.services.reservations import (
    ReservationError,
    _closing,
    _is_taken,
    _open_spots,
    active_reservations_by_spot,
    default_range,
    eligible_lots,
    floor_number,
    is_lot_active,
    lot_summaries,
    now,
    spot_label,
    usable_areas,
)

MAX_QUERY_LENGTH = 100

# (value, label) for the sort dropdown. The first one is the default.
SORT_CHOICES = [
    ('available', 'Más disponibles'),
    ('name', 'Nombre (A–Z)'),
    ('free', 'Gratis primero'),
]

# (minutes, label) for Quick Find's duration dropdown.
DURATION_CHOICES = [
    (30, '30 minutos'),
    (60, '1 hora'),
    (90, '1 hora 30 minutos'),
    (120, '2 horas'),
    (180, '3 horas'),
    (240, '4 horas'),
]
DEFAULT_DURATION = 60


# ========== Search and sort (REQ.5.2) ==========

def _normalize(text):
    """Lowercase and without accents, so "estudios" finds "Estudios" and "leon" finds "León"."""
    decomposed = unicodedata.normalize('NFD', (text or '').casefold())
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def clean_query(query):
    return (query or '').strip()[:MAX_QUERY_LENGTH]


def accessible_filter_on(user, value):
    """The accessible-only filter is only offered to users who need an accessible spot (SRS REQ.5.2)."""
    return bool(user.requires_accessible_spot) and value in ('1', 'true', 'on')


def _matches(lot, needle):
    return needle in _normalize(lot['name']) or needle in _normalize(lot['location'])


def _sort_key(order):
    if order == 'name':
        return lambda lot: (not lot['is_active'], _normalize(lot['name']))
    if order == 'free':
        return lambda lot: (not lot['is_active'], lot['is_paid'], -lot['free'], _normalize(lot['name']))
    return lambda lot: (not lot['is_active'], -lot['free'], _normalize(lot['name']))


def search_lots(user, start, end, query='', order='available', accessible_only=False):
    """Lot cards for the chosen time that match the search, in the chosen order.

    The text is matched in Python against lots the user can already see,
    never put into a database query.
    """
    lots = lot_summaries(user, start, end, accessible_only)
    if accessible_only:
        lots = [lot for lot in lots if lot['spots']]
    needle = _normalize(clean_query(query))
    if needle:
        lots = [lot for lot in lots if _matches(lot, needle)]
    lots.sort(key=_sort_key(order))
    return lots


# ========== Quick Find (REQ.5.1) ==========

def quick_find_range(minutes, current=None):
    """From the first open slot, for `minutes` (cut short at closing). (None, None) if nothing is open."""
    start, _ = default_range(current)
    if start is None:
        return None, None
    return start, min(start + timedelta(minutes=minutes), _closing(start.date()))


def quick_find_candidates(user, start, end, preferred_lot=None, skip=(), current=None):
    """Spots the user could reserve for the whole time, best match first.

    Ranking (SRS REQ.5.1): the preferred lot first, then accessible spots for
    users who need one, then lots with more free spots, then floor and number.
    """
    current = current or now()
    lots = [lot for lot in eligible_lots(user) if is_lot_active(lot)]
    spots_by_lot = {lot.id: _open_spots(usable_areas(user, lot), start.date()) for lot in lots}
    spot_ids = [spot.id for spots in spots_by_lot.values() for spot in spots]
    ranges = active_reservations_by_spot(spot_ids, start, end)
    held = SpotHold.held_by_others(spot_ids, start, end, user.id, current)
    skip = set(skip)

    candidates = []
    free_in_lot = {}
    for lot in lots:
        free = [
            spot for spot in spots_by_lot[lot.id]
            if not _is_taken(ranges[spot.id], start, end)
            and spot.id not in held
            and spot.is_reservable_by(user)
        ]
        free_in_lot[lot.id] = len(free)
        candidates.extend((lot, spot) for spot in free if spot.id not in skip)

    wants_accessible = bool(user.requires_accessible_spot)
    candidates.sort(key=lambda pair: (
        preferred_lot is None or pair[0].id != preferred_lot.id,
        not (wants_accessible and pair[1].is_accessible),
        -free_in_lot[pair[0].id],
        pair[0].name,
        floor_number(pair[1].lot),
        spot_label(pair[1]),
    ))
    return candidates


def _hold(user, spot, start, end, current):
    """Set the spot aside for the user, unless someone took or held it meanwhile. The caller commits."""
    # Same lock as reserve(), so two people using Quick Find at once get different spots.
    db.session.execute(db.update(Spots).where(Spots.id == spot.id).values(id=Spots.id))
    taken = Reservation.active_overlapping(start, end).filter(Reservation.spot_id == spot.id).first()
    if taken is not None or SpotHold.held_by_others([spot.id], start, end, user.id, current):
        return False
    SpotHold.release_for_user(user.id)
    db.session.add(SpotHold(
        spot_id=spot.id,
        user_id=user.id,
        start_time=start,
        end_time=end,
        expires_at=current + timedelta(minutes=current_app.config['QUICK_FIND_HOLD_MINUTES']),
    ))
    return True


def quick_find(user, start, end, preferred_lot=None, skip=(), current=None):
    """Hold and return the best (lot, spot) for the user, or None if no spot is left.

    Raises ReservationError if the user already has a reservation at that time,
    since reserve() would reject any suggestion.
    """
    current = current or now()
    if Reservation.active_overlapping(start, end).filter(Reservation.user_id == user.id).first() is not None:
        raise ReservationError('Ya tienes una reservación en ese horario.')
    try:
        SpotHold.delete_expired(current)
        for lot, spot in quick_find_candidates(user, start, end, preferred_lot, skip, current):
            if _hold(user, spot, start, end, current):
                db.session.commit()
                return lot, spot
        SpotHold.release_for_user(user.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return None


def release_holds(user):
    SpotHold.release_for_user(user.id)
    db.session.commit()
