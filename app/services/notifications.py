from flask import current_app, render_template
from flask_mailman import EmailMultiAlternatives


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
