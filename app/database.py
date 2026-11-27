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

# (name, location, is_paid, is_active, floors). Each floor is
# (role_name, capacity, accessible_capacity) and becomes a child lot named
# "<lot name> · Piso N", the same way admins create floors.
DEMO_LOTS = (
    ("Estudios Generales", "Detrás del edificio de Estudios Generales", False, True, (
        ("estudiante", 12, 2),
    )),
    ("Torre Norte", "Calle Amapola, Residencias Torre Norte", True, True, (
        ("estudiante", 10, 1),
        ("empleado", 10, 1),
    )),
    ("Facultad de Ciencias", "Ave. Universidad, frente a Ciencias Naturales", False, True, (
        ("empleado", 8, 1),
    )),
    ("Plaza Universitaria", "Av. Ponce de León, frente a Plaza Universitaria", True, True, (
        (None, 8, 2),
    )),
    ("Teatro UPR", "Ave. Universidad, junto al Teatro UPR", False, False, (
        (None, 6, 1),
    )),
)


def _create_demo_lots(models, roles):
    for name, location, is_paid, is_active, floors in DEMO_LOTS:
        lot = models.Lots(
            name=name,
            location=location,
            is_paid=is_paid,
            is_active=is_active,
            accessible=any(accessible for _, _, accessible in floors),
        )
        for number, (role_name, capacity, accessible_capacity) in enumerate(floors, start=1):
            floor = models.Lots(
                name=f"{name} · Piso {number}",
                location=location,
                is_paid=is_paid,
                is_active=is_active,
                accessible=accessible_capacity > 0,
                role=roles.get(role_name) if role_name is not None else None,
            )
            # The first `accessible_capacity` spots are the accessible ones.
            floor.spots = [
                models.Spots(is_accessible=spot < accessible_capacity)
                for spot in range(capacity)
            ]
            lot.floors.append(floor)
        db.session.add(lot)
    db.session.commit()


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

        if models.Lots.query.first() is None:
            _create_demo_lots(models, roles)
