from datetime import date, timedelta
import unicodedata
from uuid import uuid4

from app.database import db
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
	def create_parent_lot(cls, name, location, is_paid, floors):
		"""Create and persist a new parent lot through the model layer."""
		lot = cls.create_lot(name, location, is_paid, floors)
		try:
			db.session.add(lot)
			db.session.commit()
		except SQLAlchemyError:
			db.session.rollback()
			return None
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

	@classmethod
	def get_lot_by_id(cls, lot_id):
		"""Fetch a lot by ID through the model layer."""
		return cls.query.get(lot_id)

	@classmethod
	def get_parent_lots(cls):
		"""Return parent lots for the administration list."""
		return cls.query.filter_by(parent_id=None).order_by(cls.id).all()

	@classmethod
	def get_parent_lot_by_id(cls, lot_id):
		"""Return a parent lot, including lots that currently have no floors."""
		return cls.query.filter_by(id=lot_id, parent_id=None).first()

	@classmethod
	def get_parent_lot_summaries(cls, lots=None):
		"""Build the admin list data while keeping relationship queries in the model."""
		lots = cls.get_parent_lots() if lots is None else lots
		summaries = []
		for lot in lots:
			floors = cls.get_floors(lot)
			spots = list(lot.spots) + [
				spot for floor in floors for spot in floor.spots
			]
			roles = sorted(
				{floor.role for floor in floors if floor.role},
				key=lambda role: role.id,
			)
			name_key = unicodedata.normalize("NFD", lot.name.casefold())
			summaries.append(
				{
					"id": lot.id,
					"name": lot.name,
					"sort_key": "".join(
						char
						for char in name_key
						if not unicodedata.combining(char)
					),
					"location": lot.location,
					"is_paid": bool(lot.is_paid),
					"floors": len(floors),
					"spots": len(spots),
					"accessible": sum(spot.is_accessible for spot in spots),
					"roles": [role.name.title() for role in roles],
					"is_active": bool(lot.is_active),
					"date_to_be_deleted": (
						lot.date_to_be_deleted.isoformat()
						if lot.date_to_be_deleted
						else None
					),
				}
			)
		return summaries

	@classmethod
	def get_parent_lot_details(cls, lot_id):
		"""Return editable values for an existing parent lot."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return None
		floors = []
		for floor in cls.get_floors(lot):
			floors.append(
				{
					"id": floor.id,
					"capacity": len(floor.spots),
					"accessible_capacity": sum(
						spot.is_accessible for spot in floor.spots
					),
					"role_id": floor.role_id,
				}
			)
		return {
			"id": lot.id,
			"name": lot.name,
			"location": lot.location,
			"is_paid": bool(lot.is_paid),
			"floors": floors,
		}

	@classmethod
	def update_parent_lot(cls, lot_id, data):
		"""Validate and persist an edit without removing reserved spots or floors."""
		from app.models.Reservations import Reservation
		from app.models.Roles import Role

		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return "not_found"

		existing_floors = {floor.id: floor for floor in cls.get_floors(lot)}
		submitted_ids = [
			floor["id"] for floor in data["floors"] if floor["id"] is not None
		]
		if (
			len(submitted_ids) != len(set(submitted_ids))
			or not set(submitted_ids).issubset(existing_floors)
		):
			return "invalid_floor"

		allowed_role_ids = {
			role.id for role in Role.get_roles_for_lots()
		}
		for floor in data["floors"]:
			if floor["role_id"] is not None and floor["role_id"] not in allowed_role_ids:
				return "invalid_role"

		reserved_spot_ids = Reservation.get_reserved_spot_ids(
			set(existing_floors)
		)
		submitted_id_set = set(submitted_ids)
		for floor_id, floor in existing_floors.items():
			spots = floor.spots
			floor_spot_ids = {spot.id for spot in spots}
			if (
				floor_id not in submitted_id_set
				and reserved_spot_ids.intersection(floor_spot_ids)
			):
				return "reserved_floor"

		floor_by_id = {floor["id"]: floor for floor in data["floors"]}
		for floor_id, desired in floor_by_id.items():
			if floor_id is None:
				continue
			floor = existing_floors[floor_id]
			spots = floor.spots
			reserved = [
				spot for spot in spots if spot.id in reserved_spot_ids
			]
			reserved_accessible = sum(
				spot.is_accessible for spot in reserved
			)
			reserved_regular = len(reserved) - reserved_accessible
			if (
				desired["capacity"] < len(reserved)
				or desired["accessible_capacity"] < reserved_accessible
				or desired["capacity"] - desired["accessible_capacity"]
				< reserved_regular
			):
				return "reserved_capacity"

		own_ids = {lot.id, *existing_floors}
		floor_names = [
			f"{data['name']} · Piso {number}"
			for number in range(1, len(data["floors"]) + 1)
		]
		conflicting_names = [data["name"], *floor_names]
		conflicts = cls.query.filter(
			db.func.lower(cls.name).in_(
				{name.lower() for name in conflicting_names}
			)
		).all()
		if any(record.id not in own_ids for record in conflicts):
			return "duplicate_name"

		try:
			# Free the unique floor names before assigning the lot's new names.
			for floor in existing_floors.values():
				floor.name = f"__lot-edit-{uuid4().hex}"
			db.session.flush()

			lot.name = data["name"]
			lot.location = data["location"]
			lot.is_paid = data["is_paid"]
			lot.accessible = any(
				floor["accessible_capacity"] > 0
				for floor in data["floors"]
			)

			for number, floor_data in enumerate(data["floors"], start=1):
				floor_id = floor_data["id"]
				if floor_id is None:
					floor = cls._build_floor(
						lot,
						number,
						floor_data["capacity"],
						floor_data["accessible_capacity"],
						floor_data["role_id"],
					)
					lot.floors.append(floor)
					floor.is_active = lot.is_active
					floor.date_to_be_deleted = lot.date_to_be_deleted
					for spot in floor.spots:
						spot.date_to_be_deleted = lot.date_to_be_deleted
				else:
					floor = existing_floors[floor_id]
					floor.name = f"{lot.name} · Piso {number}"
					floor.location = lot.location
					floor.is_paid = lot.is_paid
					floor.accessible = floor_data["accessible_capacity"] > 0
					floor.role_id = floor_data["role_id"]
					cls._resize_floor(
						floor,
						floor_data["capacity"],
						floor_data["accessible_capacity"],
						reserved_spot_ids,
					)

			for floor_id, floor in existing_floors.items():
				if floor_id not in submitted_id_set:
					for spot in floor.spots:
						db.session.delete(spot)
					db.session.delete(floor)
			db.session.commit()
		except IntegrityError:
			db.session.rollback()
			return "duplicate_name"
		return None

	@classmethod
	def _resize_floor(
		cls, floor, capacity, accessible_capacity, reserved_spot_ids
	):
		"""Resize only unreserved spots; reserved spots retain their type."""
		spots = floor.spots
		available_accessible = [
			spot
			for spot in spots
			if spot.id not in reserved_spot_ids and spot.is_accessible
		]
		available_regular = [
			spot
			for spot in spots
			if spot.id not in reserved_spot_ids and not spot.is_accessible
		]
		reserved = [spot for spot in spots if spot.id in reserved_spot_ids]
		reserved_accessible = sum(spot.is_accessible for spot in reserved)
		reserved_regular = len(reserved) - reserved_accessible
		desired_accessible = accessible_capacity - reserved_accessible
		desired_regular = capacity - accessible_capacity - reserved_regular

		for spot in available_accessible[desired_accessible:]:
			db.session.delete(spot)
		for spot in available_regular[desired_regular:]:
			db.session.delete(spot)
		for _ in range(max(0, desired_accessible - len(available_accessible))):
			db.session.add(Spots(is_accessible=True, lot=floor))
		for _ in range(max(0, desired_regular - len(available_regular))):
			db.session.add(Spots(is_accessible=False, lot=floor))

	@classmethod
	def schedule_parent_deletion(cls, lot_id):
		"""Set the scheduled deletion date two calendar days from today."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return None
		deletion_date = date.today() + timedelta(days=2)
		lot.date_to_be_deleted = deletion_date
		for floor in cls.get_floors(lot):
			floor.date_to_be_deleted = deletion_date
			for spot in floor.spots:
				spot.date_to_be_deleted = deletion_date
		db.session.commit()
		return deletion_date

	@classmethod
	def deactivate_parent_lot(cls, lot_id):
		"""Disable a parent lot and its floors while retaining their data."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return False
		lot.is_active = False
		lot.date_to_be_deleted = None
		for spot in lot.spots:
			spot.date_to_be_deleted = None
		for floor in cls.get_floors(lot):
			floor.is_active = False
			floor.date_to_be_deleted = None
			for spot in floor.spots:
				spot.date_to_be_deleted = None
		db.session.commit()
		return True

	@classmethod
	def delete_parent_lot(cls, lot_id):
		"""Delete a parent lot and every dependent report, reservation, spot, and floor."""
		from app.models.Incident_Reports import IncidentReport
		from app.models.Reservations import Reservation

		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return None
		floors = cls.get_floors(lot)
		lot_ids = {lot.id, *(floor.id for floor in floors)}
		spots = Spots.query.filter(Spots.lot_id.in_(lot_ids)).all()
		spot_ids = {spot.id for spot in spots}
		reservations = Reservation.query.filter(
			Reservation.spot_id.in_(spot_ids)
		).all()
		reservation_ids = {reservation.id for reservation in reservations}
		reports = IncidentReport.query.filter(
			IncidentReport.reservation_id.in_(reservation_ids)
		).all()

		for report in reports:
			db.session.delete(report)
		for reservation in reservations:
			db.session.delete(reservation)
		for spot in spots:
			db.session.delete(spot)
		for floor in floors:
			db.session.delete(floor)
		db.session.delete(lot)
		db.session.commit()
		return len(reservations)

	@classmethod
	def get_floors(cls, lot):
		"""Return a parent's floors in their persisted display order."""
		return sorted(lot.floors, key=lambda floor: floor.id)

	@classmethod
	def is_parent_lot(cls, lot):
		"""Parent lots remain editable even when they have no floors."""
		return lot is not None and lot.parent_id is None
