"""Managing your own reservations: SRS REQ.3.2 (cancel) and REQ.3.3 (check out).

Spot availability comes from active reservations (Reservation.active_overlapping),
so "freeing the spot" means the reservation stops being 'Active' or its
end_time moves earlier.
"""

from app.database import db
from app.models import Reservation
from app.services.reservations import ReservationError, now


def get_own_reservation(user, reservation_id):
    """The user's reservation. Someone else's counts as not found."""
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None or reservation.user_id != user.id:
        raise ReservationError('No encontramos esa reservación.')
    return reservation


def my_reservations(user, current=None):
    """The user's active reservations: 'current' have started, 'upcoming' haven't."""
    current = current or now()
    active = (
        Reservation.query
        .filter(Reservation.user_id == user.id, Reservation.status == 'Active',
                Reservation.spot_id.isnot(None))
        .order_by(Reservation.start_time)
        .all()
    )
    return {
        'current': [r for r in active if r.start_time <= current],
        'upcoming': [r for r in active if r.start_time > current],
    }


def past_reservations(user):
    """user's completed and cancelled reservations"""
    return (
        Reservation.query
        .filter(Reservation.user_id == user.id, Reservation.status != 'Active',
                Reservation.spot_id.isnot(None))
        .order_by(Reservation.start_time.desc())
        .all()
    )

# REQ.3.2 Cancel

def cancel(user, reservation_id, reason=None):
    """Steps 1 and 3: cancel an upcoming reservation and save the optional reason."""
    reservation = get_own_reservation(user, reservation_id)
    if reservation.status != 'Active':
        raise ReservationError('Esta reservación ya no está activa.')
    if reservation.start_time <= now():
        raise ReservationError('Esta reservación ya comenzó. Usa “Check out”.')

    reservation.status = 'Cancelled'
    reservation.cancelation_reason = (reason or '').strip() or None
    db.session.commit()
    return reservation


# REQ.3.3 Check out

def check_out(user, reservation_id):
    """Step 1: end a reservation that has started."""
    reservation = get_own_reservation(user, reservation_id)
    if reservation.status != 'Active':
        raise ReservationError('Esta reservación ya no está activa.')
    current = now()
    if reservation.start_time > current:
        raise ReservationError('Esta reservación aún no comienza. Puedes cancelarla.')

    reservation.status = 'Completed'
    reservation.check_out_time = current
    # TODO REQ.3.3 postcondition 2: on an early check out, move end_time back
    # to the check out time so the rest of the slot is free for others.
    db.session.commit()
    return reservation


# TODO REQ.3.3 step 2 (Timeslot Check): find out whether the spot is reserved
#   in the next slot after this reservation. Reservation.active_overlapping()
#   and RESERVATION_SLOT_MINUTES from config are useful here.

# TODO REQ.3.3 step 3 (Expiration trigger): find active reservations whose
#   end_time has passed and email the user asking them to check out, with an
#   option to extend if the next slot is free. Needs a scheduler (SRS dependency).

# TODO REQ.3.3 field "Duration Extension": the new end times the user can pick.
