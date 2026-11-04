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
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True

    # SQLite database URI - stores the database file in the instance folder
    # The three slashes indicate a relative path from the current directory
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.sqlite')
