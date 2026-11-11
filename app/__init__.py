import os

from flask import Flask

from config import Config
from app.database import db, init_db
# from app.extensions import bcrypt

from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()



def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    bcrypt.init_app(app)
    init_db(app, bcrypt)

    from app.routes.auth import auth_bp
    from app.routes.public import public_bp

    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(public_bp, url_prefix="/")

    return app


__all__ = ["create_app", "db"]
