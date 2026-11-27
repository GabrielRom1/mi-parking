from datetime import timedelta

from app.database import db
from app.models.Reservations import Reservation
from app.models.Lots import Lots
from app.models.Spots import Spots
from app.models.User import User
from app.services.notifications import (
    checkout_action_url,
    send_cancellation_email,
    send_checkout_timeout_email,
    send_checkout_reminder_email,
    send_scheduled_action_admin_notice,
)
from app.services.reservations import extension_available, now


def cancel_reservations_without_check_in(app):
    with app.app_context():
        grace_minutes = app.config['RESERVATION_CHECK_IN_GRACE_MINUTES']
        deadline = now() - timedelta(minutes=grace_minutes)

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
                send_checkout_timeout_email(reservation.user, reservation)

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


def process_scheduled_lots(app):
    with app.app_context():
        result = Lots.process_due_scheduled_actions()

        for reservation in result['canceled']:
            send_cancellation_email(reservation.user, reservation)

        if result['deleted']:
            app.logger.info(
                'Se eliminaron lotes/pisos programados: %s',
                result['deleted'],
            )
        if result['deactivated']:
            app.logger.info(
                'Se desactivaron lotes/pisos programados: %s',
                result['deactivated'],
            )
        if result['canceled']:
            app.logger.info(
                'Se cancelaron %s reservaciones por acciones programadas',
                len(result['canceled']),
            )


def process_scheduled_spots(app):
    with app.app_context():
        result = Spots.process_due_deletions()

        if result['deleted']:
            app.logger.info(
                'Se eliminaron espacios programados: %s',
                result['deleted'],
            )
        for spot, new_date, blockers in result['admin_notices']:
            for admin in User.get_admin_users():
                sent = send_scheduled_action_admin_notice(
                    admin,
                    spot,
                    'eliminación de espacio',
                    new_date,
                    blockers,
                )
                if not sent:
                    app.logger.warning(
                        'No se pudo notificar al administrador %s sobre el espacio %s',
                        admin.email,
                        spot.id,
                    )
            app.logger.info(
                'Se pospuso la eliminación del espacio %s al %s',
                spot.id,
                new_date.isoformat(),
            )


def register_jobs(scheduler, app):

    scheduler.add_job(
        id='process-scheduled-lots',
        func=process_scheduled_lots,
        trigger='interval',
        seconds=60,
        args=[app],
        misfire_grace_time=30,
        replace_existing=True,
    )
    scheduler.add_job(
        id='process-scheduled-spots',
        func=process_scheduled_spots,
        trigger='interval',
        seconds=300,
        args=[app],
        misfire_grace_time=30,
        replace_existing=True,
    )

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