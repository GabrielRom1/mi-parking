from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


DEMO_USER_PASSWORD = "Example4030!"
DEMO_USERS = (
    ("estudiante@example.demo", "Estudiante", "Demo", "estudiante", False),
    ("empleado@example.demo", "Empleado", "Demo", "empleado", False),
    ("admin@example.demo", "Administrador", "Demo", "admin", False),
    (
        "estudiante.accesible@example.demo",
        "Estudiante",
        "Accesible",
        "estudiante",
        True,
    ),
    ("sin.rol.demo@example.demo", "Persona", "Sin rol", None, False),
)

def init_db(app, password_hasher):
    db.init_app(app)

    from app import models

    with app.app_context():
        db.create_all()
        models.Role.add_default_roles()

        roles = {role.name: role for role in models.Role.query.all()}
        users_to_create = [
            user_data
            for user_data in DEMO_USERS
            if models.User.get_user_by_email(user_data[0]) is None
        ]
        if users_to_create:
            for (
                email,
                first_name,
                last_name,
                role_name,
                needs_accessible_spot,
            ) in users_to_create:
                password_hash = password_hasher.generate_password_hash(
                    DEMO_USER_PASSWORD
                ).decode("utf-8")
                user = models.User.create_user(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password_hash=password_hash,
                    requires_accessible_spot=needs_accessible_spot,
                    role=roles.get(role_name) if role_name is not None else None,
                )
                db.session.add(user)
            db.session.commit()
