from datetime import UTC, datetime

from icalendar import Calendar, Event

from app.services.reservations import PUERTO_RICO, spot_number


def _to_utc(moment):
    """Reservation times are Puerto Rico time; calendars need them in UTC."""
    return moment.replace(tzinfo=PUERTO_RICO).astimezone(UTC)


def ics_filename(reservation):
    return f'miparking-reservacion-{reservation.id}.ics'


def build_ics(reservation):
    """An .ics file with one event for the reservation, as bytes."""
    spot = reservation.spot
    lot = spot.lot.parent or spot.lot

    calendar = Calendar()
    calendar.add('prodid', '-//MiParking//Reservaciones//ES')
    calendar.add('version', '2.0')
    calendar.add('method', 'PUBLISH')

    event = Event()
    event.add('uid', f'reservation-{reservation.id}@miparking')
    event.add('dtstamp', datetime.now(UTC))
    event.add('dtstart', _to_utc(reservation.start_time))
    event.add('dtend', _to_utc(reservation.end_time))
    event.add('summary', f'Estacionamiento: {lot.name}, espacio {spot_number(spot)}')
    event.add('location', lot.location)
    event.add('description', f'Reservación #{reservation.id} en MiParking.')
    calendar.add_component(event)

    return calendar.to_ical()
