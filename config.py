# config.py

# Flask configuration with SQLite database settings
import os
from datetime import timedelta

# Get the base directory of the application
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Secret key for session management and CSRF protection
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    BCRYPT_HANDLE_LONG_PASSWORDS = True
    DEBUG = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true')
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True

    # SQLite database URI - stores the database file in the instance folder
    # The three slashes indicate a relative path from the current directory
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.sqlite')

    # Email (Flask-Mailman). Without MAIL_SERVER, emails are printed to the console.
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'MiParking <no-reply@miparking.local>'
    MAIL_BACKEND = os.environ.get('MAIL_BACKEND') or ('smtp' if MAIL_SERVER else 'console')
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL') or 'http://127.0.0.1:4030'

    # Reservations (REQ.3.1). All times are Puerto Rico time
    RESERVATION_SLOT_MINUTES = 30
    RESERVATION_OPENING_HOUR = 7
    RESERVATION_CLOSING_HOUR = 22
    RESERVATION_WINDOW_HOURS = 48

    RESERVATION_CHECK_IN_GRACE_MINUTES = int(
        os.environ.get('RESERVATION_CHECK_IN_GRACE_MINUTES') or 15
    )
    RESERVATION_CHECKOUT_REMINDER_MINUTES = int(
        os.environ.get('RESERVATION_CHECKOUT_REMINDER_MINUTES') or 15
    )
    RESERVATION_CHECKOUT_GRACE_MINUTES = int(
        os.environ.get('RESERVATION_CHECKOUT_GRACE_MINUTES') or 15
    )