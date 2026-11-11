from flask import current_app, render_template
from flask_mail import Message
from app import mail

def send_email(to, subject, template, **context):
    msg = Message(subject, recipientes=[to])
    msg.body = render_templaye(f'emails/{template}.txt', **context)
    msg.html = render_templaye(f'emails/{template}.html', **context)
    try:
        mail.send(msg)
    except Exception:
        current_app.logger.exception('Error enviando correo a %s', to)
