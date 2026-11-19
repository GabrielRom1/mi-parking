from flask import current_app, render_template
from flask_mailman import EmailMultiAlternatives
from itsdangerous import URLSafeTimedSerializer


def checkout_action_url(reservation, action):
    """Build a signed link whose action is only valid within its reservation window."""
    if action not in ('checkout', 'extend'):
        raise ValueError(f'Unsupported checkout action: {action}')

    serializer = URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        salt='reservation-checkout',
    )
    token = serializer.dumps({
        'reservation_id': reservation.id,
        'user_id': reservation.user_id,
        'end_time': reservation.end_time.isoformat(),
        'action': action,
    })
    base_url = current_app.config['PUBLIC_BASE_URL'].rstrip('/')
    return (
        f'{base_url}/reservations/checkout/{token}'
        f'?action={action}'
    )


def send_email(to, subject, template, attachments=(), **context):
    """Send templates/emails/<template>.txt and .html to `to`.

    `attachments` are (filename, content, mimetype) tuples. Returns False
    instead of raising when sending fails, so a mail outage never undoes
    the action that triggered the email.
    """
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_template(f'emails/{template}.txt', **context),
        to=[to],
    )
    message.attach_alternative(
        render_template(f'emails/{template}.html', **context), 'text/html'
    )
    for filename, content, mimetype in attachments:
        message.attach(filename, content, mimetype)
    try:
        message.send()
    except Exception:
        current_app.logger.exception('Error enviando correo a %s', to)
        return False
    return True


def send_cancellation_email(user, reservation):
    """Email the user that their reservation was cancelled."""
    return send_email(
        user.email,
        'Tu reservación en MiParking fue cancelada',
        'reservation_cancelled',
        user=user,
        reservation=reservation,
    )


def send_checkout_timeout_email(user, reservation):
    """Tell the user their reservation ended automatically after checkout grace."""
    return send_email(
        user.email,
        'Tu reservación terminó automáticamente',
        'reservation_checkout_timeout',
        user=user,
        reservation=reservation,
    )


def send_scheduled_action_admin_notice(admin, target, action, new_date, blockers=()):
    """Notify one administrator that a scheduled lot/spot action was postponed."""
    return send_email(
        admin.email,
        'Acción programada pospuesta en MiParking',
        'scheduled_action_postponed',
        admin=admin,
        target=target,
        action=action,
        new_date=new_date,
        blockers=blockers,
    )


def send_checkout_reminder_email(
    user, reservation, checkout_url, extension_url=None
):
    """Ask the user to confirm checkout, optionally offering one time-slot extension."""
    return send_email(
        user.email,
        'Confirma tu salida de MiParking',
        'checkout_reminder',
        user=user,
        reservation=reservation,
        checkout_url=checkout_url,
        extension_url=extension_url,
    )
