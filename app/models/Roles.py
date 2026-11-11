from app.database import db

class Role(db.Model):
	__tablename__ = 'roles'

	# CREATE TABLE roles (
	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	name varchar(20) NOT NULL UNIQUE,
	name = db.Column(db.String(20), unique=True, nullable=False)

	# 	description varchar(500) NULL
	description = db.Column(db.String(500), nullable=True)

	users = db.relationship('User', back_populates='role', lazy=True)
	lots = db.relationship('Lots', back_populates='role', lazy=True)


	@classmethod
	def add_default_roles(cls):
		default_roles = {
			'admin': 'Tiene acceso a la administración del sistema y puede reservar en todos los lotes.',
			'estudiante': 'Usuario con rol de estudiante.',
			'empleado': 'Usuario con rol de empleado.',
		}
		existing_roles = {
			role.name: role
			for role in cls.query.filter(cls.name.in_(default_roles)).all()
		}

		for name, description in default_roles.items():
			role = existing_roles.get(name)
			if role is None:
				db.session.add(cls(name=name, description=description))
			elif role.description != description:
				role.description = description

		db.session.commit()
