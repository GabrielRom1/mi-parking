from app.database import db

class Lots(db.Model):
	__tablename__ = 'lots'

	# 	id int AUTO_INCREMENT PRIMARY KEY
	id = db.Column(db.Integer, primary_key=True)
 
	# 	name varchar(50) NOT NULL UNIQUE,
	# SRS REQ.2.1 allows lot names up to 100 characters; floors are stored as
	# child lots named "<lot name> · Piso N", so the column leaves room for that suffix.
	name = db.Column(db.String(120), unique=True, nullable=False)

	# 	location varchar(255) NOT NULL,
	location = db.Column(db.String(255), nullable=False)

	# 	is_paid TINYINT DEFAULT 0,
	is_paid = db.Column(db.Boolean, default=False)

	date_to_be_deleted = db.Column(db.Date, nullable=True)

	# 	is_active TINYINT DEFAULT 1,
	is_active = db.Column(db.Boolean, default=True)

	# 	parent_id int NULL,
	# 	FOREIGN KEY (parent_id) REFERENCES lots(id)
	parent_id = db.Column(db.Integer, db.ForeignKey('lots.id'), nullable=True)

	parent = db.relationship('Lots', remote_side=[id], back_populates='floors')

	floors = db.relationship('Lots', back_populates='parent')

	# 	accessible TINYINT DEFAULT 0,
	accessible = db.Column(db.Boolean, default=False)

	# 	role_id int NULL,
 	# 	FOREIGN KEY (role_id) REFERENCES roles(id),
	role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
	role = db.relationship('Role', back_populates='lots', lazy=True)

	@classmethod
	def get_lot_by_name(cls, name):
		normalized_name = name.strip().lower()
		return cls.query.filter(
			db.func.lower(cls.name) == normalized_name
		).first()

	@classmethod
	def create_lot(cls, name, location, is_paid, floors):
		"""Build a lot, one child lot per floor and that floor's spots.

		`floors` is a list of dicts with `capacity`, `accessible_capacity` and
		`role`, ordered bottom (Floor 1) to top. The caller adds and commits.
		"""
		from app.models.Spots import Spots

		name = name.strip()
		location = location.strip()
		lot = cls(
			name=name,
			location=location,
			is_paid=is_paid,
			is_active=True,
			accessible=any(floor['accessible_capacity'] > 0 for floor in floors),
		)
		for number, floor_data in enumerate(floors, start=1):
			floor = cls(
				name=f"{name} · Piso {number}",
				location=location,
				is_paid=is_paid,
				is_active=True,
				accessible=floor_data['accessible_capacity'] > 0,
				role=floor_data['role'],
			)
			floor.spots = [
				Spots(is_accessible=index < floor_data['accessible_capacity'])
				for index in range(floor_data['capacity'])
			]
			lot.floors.append(floor)
		return lot
