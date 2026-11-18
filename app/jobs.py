from datetime import datetime, timedelta

from app.database import db
from app.models.Reservations import Reservation
from app.services.notifications import (
    checkout_action_url,
    send_cancellation_email,
    send_checkout_reminder_email,
)
from app.services.reservations import extension_available, now


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


def cancel_reservations_without_check_out(app):
    with app.app_context():
        grace_minutes = app.config['RESERVATION_CHECKOUT_GRACE_MINUTES']
        deadline = now() - timedelta(minutes=grace_minutes)
        reservations = Reservation.checked_in_without_checkout_before(
            deadline
        ).all()

        for reservation in reservations:
            reservation.status = 'Cancelled'
            reservation.cancelation_reason = (
                'Sin check-out dentro del periodo de gracia'
            )

        if reservations:
            db.session.commit()
            for reservation in reservations:
                send_cancellation_email(reservation.user, reservation)

            app.logger.info(
                'Se cancelaron %s reservaciones sin check-out',
                len(reservations),
            )


def send_checkout_reminders(app):
    with app.app_context():
        deadline = now() + timedelta(
            minutes=app.config['RESERVATION_CHECKOUT_REMINDER_MINUTES']
        )
        reservations = Reservation.checked_in_without_checkout_reminder_before(
            deadline
        ).all()

        for reservation in reservations:
            extension_url = None
            if extension_available(reservation):
                extension_url = checkout_action_url(reservation, 'extend')
            checkout_url = checkout_action_url(reservation, 'checkout')
            email_sent = send_checkout_reminder_email(
                reservation.user,
                reservation,
                checkout_url=checkout_url,
                extension_url=extension_url,
            )
            if not email_sent:
                app.logger.warning(
                    'No se pudo enviar el recordatorio de salida para la reservación %s',
                    reservation.id,
                )
                continue

            reservation.checkout_reminder_sent_at = now()
            db.session.commit()
            app.logger.info(
                'Se envió el recordatorio de salida para la reservación %s',
                reservation.id,
            )


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
    scheduler.add_job(
        id='send-checkout-reminders',
        func=send_checkout_reminders,
        trigger='interval',
        minutes=1,
        args=[app],
        misfire_grace_time=30,
        replace_existing=True,
    )
    scheduler.add_job(
        id='cancel-reservations-without-check-out',
        func=cancel_reservations_without_check_out,
        trigger='interval',
        minutes=1,
        args=[app],
        misfire_grace_time=30,
        replace_existing=True,
    )