from datetime import datetime, timedelta

from app.database import db
from app.models.Reservations import Reservation
from app.services.notifications import send_cancellation_email


def cancel_reservations_without_check_in(app):
    with app.app_context():
        grace_minutes = app.config['RESERVATION_CHECK_IN_GRACE_MINUTES']
        deadline = datetime.now() - timedelta(minutes=grace_minutes)

        reservations = Reservation.active_without_check_in_before(deadline).all()

        for reservation in reservations:
            reservation.status = 'Cancelled'
            reservation.cancelation_reason = (
                'Sin check-in dentro del periodo de gracia'
            )

        if reservations:
            db.session.commit()

            for reservation in reservations:
                send_cancellation_email(reservation.user, reservation)

            app.logger.info('Se cancelaron %s reservaciones', len(reservations))


def register_jobs(scheduler, app):
    scheduler.add_job(
        id='cancel-reservations-without-check-in',
        func=cancel_reservations_without_check_in,
        trigger='interval',
        minutes=1,
        args=[app],
        misfire_grace_time=30,
        replace_existing=True,
    )