from app.database import db
from app.models.Spots import Spots

class Lots(db.Model):
	__tablename__ = 'lots'

	# 	id int AUTO_INCREMENT PRIMARY KEY
	id = db.Column(db.Integer, primary_key=True)
 
	# 	name varchar(120) NOT NULL UNIQUE,
	# Lot names are limited to 100 characters by the form (SRS REQ.2.1). The extra
	# room is for floors, which are child lots named "<lot name> · Piso N".
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
		"""Build a lot with one child lot per floor, each with its spots.

		`floors` is ordered bottom to top. Each item has `capacity`,
		`accessible_capacity` and `role_id`. The caller adds and commits.
		"""
		lot = cls(
			name=name,
			location=location,
			is_paid=is_paid,
			accessible=any(floor['accessible_capacity'] > 0 for floor in floors),
		)
		for number, floor in enumerate(floors, start=1):
			lot.floors.append(cls._build_floor(lot, number, **floor))
		return lot

	@classmethod
	def _build_floor(cls, lot, number, capacity, accessible_capacity, role_id):
		floor = cls(
			name=f"{lot.name} · Piso {number}",
			location=lot.location,
			is_paid=lot.is_paid,
			accessible=accessible_capacity > 0,
			role_id=role_id,
		)
		# The first `accessible_capacity` spots are the accessible ones.
		floor.spots = [
			Spots(is_accessible=spot < accessible_capacity)
			for spot in range(capacity)
		]
		return floor
