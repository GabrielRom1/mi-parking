from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import unicodedata
from uuid import uuid4

from app.database import db
from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.models.Spots import Spots


PUERTO_RICO = ZoneInfo('America/Puerto_Rico')


class SchedulingRequired(ValueError):
	"""A destructive or disruptive schedule needs an explicit date/override."""

	def __init__(
		self, minimum_date, lot_id, action, has_pending_reservations=False
	):
		self.minimum_date = minimum_date
		self.lot_id = lot_id
		self.action = action
		self.has_pending_reservations = has_pending_reservations
		super().__init__(
			f'No se puede {action} ahora; programe la operación para el '
			f'{minimum_date.isoformat()} o posterior, o use override.'
		)


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

	date_to_be_deleted = db.Column(db.DateTime, nullable=True)

	date_to_be_deactivated = db.Column(db.DateTime, nullable=True)

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
					"date_to_be_deactivated": (
						lot.date_to_be_deactivated.isoformat()
						if lot.date_to_be_deactivated
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
					"is_active": bool(floor.is_active),
					"date_to_be_deleted": (
						floor.date_to_be_deleted.isoformat()
						if floor.date_to_be_deleted
						else None
					),
					"date_to_be_deactivated": (
						floor.date_to_be_deactivated.isoformat()
						if floor.date_to_be_deactivated
						else None
					),
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
		removed_floor_ids = set(existing_floors) - submitted_id_set
		deletion_decisions = data.get('floor_deletion_decisions', {})
		floor_deletion_issues = []
		for floor_id, floor in existing_floors.items():
			if floor_id not in removed_floor_ids:
				continue
			spots = floor.spots
			blockers = cls._blocking_reservations(spots)
			schedule_info = cls._deletion_schedule_info(
				floor_id, blockers
			)
			decision = deletion_decisions.get(str(floor_id))
			if decision is None:
				floor_deletion_issues.append({
					'floor_id': floor_id,
					'has_pending_reservations': bool(blockers),
					**schedule_info,
				})
				continue
			if decision.get('confirmed') and blockers:
				floor_deletion_issues.append({
					'floor_id': floor_id,
					'has_pending_reservations': True,
					**schedule_info,
				})
				continue
			if decision.get('scheduled_date'):
				try:
					scheduled_date = cls._normalize_deletion_datetime(
						decision['scheduled_date']
					)
				except ValueError:
					return 'invalid_floor_deletion_date'
				token_payload = cls._read_deletion_minimum_token(
					decision.get('minimum_token'), floor_id
				)
				if (
					token_payload is None
					or scheduled_date != token_payload['scheduled_at']
					or not cls._is_no_reservable_deletion_datetime(
						scheduled_date,
						token_payload['clicked_at'],
					)
					or not schedule_info['can_schedule']
				):
					floor_deletion_issues.append({
						'floor_id': floor_id,
						'has_pending_reservations': bool(blockers),
						**schedule_info,
					})
		if floor_deletion_issues:
			return {'floor_deletions': floor_deletion_issues}

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
			f"{lot.name} · Piso {number}"
			for number in range(1, len(data["floors"]) + 1)
		]
		conflicting_names = [lot.name, *floor_names]
		conflicts = cls.query.filter(
			db.func.lower(cls.name).in_(
				{name.lower() for name in conflicting_names}
			)
		).all()
		if any(record.id not in own_ids for record in conflicts):
			return "duplicate_name"

		canceled_reservations = []
		scheduled_floor_ids = []
		try:
			# Free the unique floor names before assigning the lot's new names.
			for floor in existing_floors.values():
				floor.name = f"__lot-edit-{uuid4().hex}"
			db.session.flush()

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
					decision = deletion_decisions[str(floor_id)]
					if decision.get('scheduled_date'):
						scheduled_date = cls._normalize_deletion_datetime(
							decision['scheduled_date']
						)
						floor.date_to_be_deleted = scheduled_date
						floor.date_to_be_deactivated = None
						for spot in floor.spots:
							spot.date_to_be_deleted = scheduled_date
						scheduled_floor_ids.append(floor_id)
						continue

					from app.models.Reservations import Reservation
					spots = floor.spots
					spot_ids = {spot.id for spot in spots}
					reservations = Reservation.query.filter(
						Reservation.spot_id.in_(spot_ids)
					).all() if spot_ids else []
					for reservation in reservations:
						if (
							decision.get('override')
							and reservation.status == 'Active'
							and reservation.end_time >= cls._now()
						):
							reservation.status = 'Cancelled'
							reservation.cancelation_reason = (
								'Lot deleted by administrator'
							)
							canceled_reservations.append(reservation)
						reservation.spot_id = None
					for spot in spots:
						db.session.delete(spot)
					db.session.delete(floor)
			db.session.commit()
		except IntegrityError:
			db.session.rollback()
			return "duplicate_name"
		except Exception:
			db.session.rollback()
			raise
		return {
			'canceled_reservations': canceled_reservations,
			'scheduled_floor_ids': scheduled_floor_ids,
		}

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
		"""Compatibility wrapper: schedule for at least the validated minimum date."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return None
		lots, spots = cls._scope(lot)
		blockers = cls._blocking_reservations(spots)
		deletion_date = cls._minimum_deletion_datetime(blockers)
		result = cls.request_deletion(
			lot_id,
			override=False,
			scheduled_date=deletion_date,
			minimum_token=cls._make_deletion_minimum_token(
				lot_id, deletion_date
			),
		)
		if isinstance(result, dict) and result.get('status') == 'scheduled':
			return deletion_date
		return None

	@classmethod
	def deactivate_parent_lot(cls, lot_id):
		"""Disable a parent lot and its floors while retaining their data."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return False
		cls._apply_lot_transaction(lot, 'deactivate')
		return True

	@classmethod
	def activate_parent_lot(cls, lot_id):
		"""Enable a parent lot and its floors, cancelling any scheduled deletion."""
		lot = cls.get_parent_lot_by_id(lot_id)
		if lot is None:
			return False
		lot.is_active = True
		lot.date_to_be_deleted = None
		lot.date_to_be_deactivated = None
		for spot in lot.spots:
			spot.date_to_be_deleted = None
		for floor in cls.get_floors(lot):
			floor.is_active = True
			floor.date_to_be_deleted = None
			floor.date_to_be_deactivated = None
			for spot in floor.spots:
				spot.date_to_be_deleted = None
		db.session.commit()
		return True

	@classmethod
	def delete_parent_lot(cls, lot_id):
		"""Compatibility wrapper for the new validated deletion workflow."""
		result = cls.request_deletion(lot_id, override=False)
		if result is None:
			return None
		if isinstance(result, dict) and result.get('status') == 'scheduled':
			return result
		return {'status': 'deleted'}

	@classmethod
	def _now(cls):
		return datetime.now(PUERTO_RICO).replace(tzinfo=None)

	@classmethod
	def _normalize_deletion_datetime(cls, scheduled_datetime):
		if scheduled_datetime is None:
			return None
		if isinstance(scheduled_datetime, datetime):
			return scheduled_datetime.replace(tzinfo=None)
		if isinstance(scheduled_datetime, date):
			return datetime.combine(scheduled_datetime, time.min)
		try:
			return datetime.fromisoformat(str(scheduled_datetime))
		except ValueError:
			raise ValueError(
				'La fecha y hora programadas deben tener formato YYYY-MM-DDTHH:MM.'
			)

	@classmethod
	def _minimum_deactivation_datetime(cls, blockers, current=None):
		current = cls._now() if current is None else current
		minimum = current.replace(second=0, microsecond=0)
		if minimum < current:
			minimum += timedelta(minutes=1)
		if blockers:
			last_reservation_end_exact = max(
				reservation.end_time for reservation in blockers
			)
			last_reservation_end = last_reservation_end_exact.replace(
				second=0, microsecond=0
			)
			if last_reservation_end < last_reservation_end_exact:
				last_reservation_end += timedelta(minutes=1)
			minimum = max(minimum, last_reservation_end)
		return minimum

	@classmethod
	def _scope(cls, lot):
		"""Return the target lot, its floors and their spots when it is a parent."""
		floors = cls.get_floors(lot) if lot.parent_id is None else []
		lots = [lot, *floors]
		lot_ids = {item.id for item in lots}
		spots = Spots.query.filter(Spots.lot_id.in_(lot_ids)).all() if lot_ids else []
		return lots, spots

	@classmethod
	def _blocking_reservations(cls, spots, current=None):
		from app.models.Reservations import Reservation
		current = cls._now() if current is None else current
		if not spots:
			return Reservation.query.filter(db.false()).all()
		spot_ids = {spot.id for spot in spots}
		return Reservation.query.filter(
			Reservation.spot_id.in_(spot_ids),
			Reservation.status == 'Active',
			Reservation.end_time >= current,
		).all()

	@classmethod
	def _minimum_deletion_datetime(cls, blockers, current=None):
		current = cls._now() if current is None else current
		return current + timedelta(
			hours=current_app.config['RESERVATION_WINDOW_HOURS'],
			minutes=current_app.config['RESERVATION_SLOT_MINUTES'],
		)

	@classmethod
	def _is_no_reservable_deletion_datetime(cls, scheduled_at, clicked_at):
		reservation_window_end = clicked_at + timedelta(
			hours=current_app.config['RESERVATION_WINDOW_HOURS']
		)
		return (
			scheduled_at
			== reservation_window_end
			+ timedelta(minutes=current_app.config['RESERVATION_SLOT_MINUTES'])
			and scheduled_at > cls._now()
		)

	@classmethod
	def _deletion_schedule_info(cls, lot_id, blockers, clicked_at=None):
		clicked_at = cls._now() if clicked_at is None else clicked_at
		scheduled_at = cls._minimum_deletion_datetime(
			blockers, current=clicked_at
		)
		window_end = clicked_at + timedelta(
			hours=current_app.config['RESERVATION_WINDOW_HOURS']
		)
		blockers_fit = all(
			reservation.end_time <= scheduled_at for reservation in blockers
		)
		return {
			'minimum_datetime': scheduled_at.isoformat(timespec='microseconds'),
			'window_end': window_end.isoformat(timespec='microseconds'),
			'window_hours': current_app.config['RESERVATION_WINDOW_HOURS'],
			'slot_minutes': current_app.config['RESERVATION_SLOT_MINUTES'],
			'minimum_token': cls._make_deletion_minimum_token(
				lot_id, scheduled_at, clicked_at=clicked_at
			),
			'can_schedule': blockers_fit,
			'blockers_end_after_schedule': not blockers_fit,
		}

	@classmethod
	def _deletion_minimum_serializer(cls):
		return URLSafeTimedSerializer(
			current_app.config['SECRET_KEY'],
			salt='lot-deletion-minimum',
		)

	@classmethod
	def _make_deletion_minimum_token(
		cls, lot_id, scheduled_at, clicked_at=None
	):
		clicked_at = (
			scheduled_at
			- timedelta(
				hours=current_app.config['RESERVATION_WINDOW_HOURS'],
				minutes=current_app.config['RESERVATION_SLOT_MINUTES'],
			)
			if clicked_at is None
			else clicked_at
		)
		return cls._deletion_minimum_serializer().dumps({
			'lot_id': lot_id,
			'clicked_at': clicked_at.isoformat(timespec='microseconds'),
			'scheduled_at': scheduled_at.isoformat(timespec='microseconds'),
		})

	@classmethod
	def _read_deletion_minimum_token(cls, token, lot_id):
		if not isinstance(token, str):
			return None
		try:
			payload = cls._deletion_minimum_serializer().loads(token, max_age=900)
			if not isinstance(payload, dict) or payload.get('lot_id') != lot_id:
				return None
			clicked_at = datetime.fromisoformat(payload['clicked_at'])
			scheduled_at = datetime.fromisoformat(payload['scheduled_at'])
			if not cls._is_no_reservable_deletion_datetime(
				scheduled_at, clicked_at
			):
				return None
			return {
				'clicked_at': clicked_at,
				'scheduled_at': scheduled_at,
			}
		except (BadData, KeyError, TypeError, ValueError):
			return None

	@classmethod
	def _apply_lot_transaction(cls, lot, action, reason=None):
		"""Apply deletion or deactivation in one transaction."""
		from app.models.Reservations import Reservation

		lots, spots = cls._scope(lot)
		canceled = []
		try:
			db.session.refresh(lot, with_for_update=True)
			if action == 'deactivate':
				from app.models.Reservations import Reservation
				for item in lots:
					item.is_active = False
					item.date_to_be_deactivated = None
					item.date_to_be_deleted = None
				for spot in spots:
					spot.date_to_be_deleted = None
				spot_ids = {spot.id for spot in spots}
				blockers = Reservation.query.filter(
					Reservation.spot_id.in_(spot_ids),
					Reservation.status == 'Active',
					Reservation.end_time >= cls._now(),
				).all() if spot_ids else []
				for reservation in blockers:
					reservation.status = 'Cancelled'
					reservation.cancelation_reason = 'Lot deactivated by administrator'
					canceled.append(reservation)
			else:
				spot_ids = {spot.id for spot in spots}
				reservations = Reservation.query.filter(
					Reservation.spot_id.in_(spot_ids)
				).all() if spot_ids else []
				for reservation in reservations:
					if reservation.status == 'Active':
						reservation.status = 'Cancelled'
						reservation.cancelation_reason = reason or 'Lot deleted by administrator'
						canceled.append(reservation)
					reservation.spot_id = None

				for spot in spots:
					db.session.delete(spot)
				for item in reversed(lots):
					if item is lot:
						continue
					db.session.delete(item)
				db.session.delete(lot)

			db.session.commit()
		except Exception:
			db.session.rollback()
			raise
		return {
			'canceled': canceled,
			'lots': lots,
			'spots': spots,
		}

	@classmethod
	def request_deletion(
		cls,
		lot_id,
		override,
		scheduled_date=None,
		confirmed=False,
		minimum_token=None,
	):
		lot = cls.query.filter_by(id=lot_id).first()
		if lot is None:
			return None

		lots, spots = cls._scope(lot)
		blockers = cls._blocking_reservations(spots)
		minimum_datetime = cls._minimum_deletion_datetime(blockers)
		scheduled_date = cls._normalize_deletion_datetime(scheduled_date)

		if override:
			if scheduled_date is not None:
				raise ValueError('El borrado inmediato no debe incluir una fecha programada.')
			return cls._apply_lot_transaction(
				lot,
				'delete',
				reason='Lot deleted by administrator',
			)

		if scheduled_date is not None:
			token_payload = cls._read_deletion_minimum_token(
				minimum_token, lot_id
			)
			if (
				token_payload is None
				or scheduled_date != token_payload['scheduled_at']
				or not cls._is_no_reservable_deletion_datetime(
					scheduled_date, token_payload['clicked_at']
				)
				or any(
					reservation.end_time > scheduled_date
					for reservation in blockers
				)
			):
				schedule_info = cls._deletion_schedule_info(lot_id, blockers)
				raise SchedulingRequired(
					datetime.fromisoformat(schedule_info['minimum_datetime']),
					lot_id,
					'eliminar el lote',
					has_pending_reservations=bool(blockers),
				)
			for item in lots:
				item.date_to_be_deleted = scheduled_date
				item.date_to_be_deactivated = None
			for spot in spots:
				spot.date_to_be_deleted = scheduled_date
			db.session.commit()
			return {'status': 'scheduled', 'date_to_be_deleted': scheduled_date}

		if blockers:
			raise SchedulingRequired(
				minimum_datetime, lot_id, 'eliminar el lote',
				has_pending_reservations=True,
			)
		if lot.is_active and spots and not confirmed:
			raise SchedulingRequired(minimum_datetime, lot_id, 'eliminar el lote')
		return cls._apply_lot_transaction(
			lot,
			'delete',
			reason='Lot deleted by administrator',
		)

	@classmethod
	def deletion_preview(cls, lot_id, clicked_at=None):
		"""Return whether deletion needs a reservation-related admin decision."""
		lot = cls.query.filter_by(id=lot_id).first()
		if lot is None:
			return None
		_, spots = cls._scope(lot)
		blockers = cls._blocking_reservations(spots)
		return {
			'has_pending_reservations': bool(blockers),
			'is_active': bool(lot.is_active),
			'date_to_be_deleted': (
				lot.date_to_be_deleted.isoformat()
				if lot.date_to_be_deleted
				else None
			),
			'date_to_be_deactivated': (
				lot.date_to_be_deactivated.isoformat()
				if lot.date_to_be_deactivated
				else None
			),
			'minimum_deactivation_datetime': (
				cls._minimum_deactivation_datetime(blockers).isoformat(
					timespec='minutes'
				)
			),
			'date_to_be_deleted_inherited': bool(
				lot.parent
				and lot.parent.date_to_be_deleted
				and lot.parent.date_to_be_deleted == lot.date_to_be_deleted
			),
			'date_to_be_deactivated_inherited': bool(
				lot.parent
				and lot.parent.date_to_be_deactivated
				and lot.parent.date_to_be_deactivated
				== lot.date_to_be_deactivated
			),
			**cls._deletion_schedule_info(
				lot_id, blockers, clicked_at=clicked_at
			),
		}

	@classmethod
	def cancel_scheduled_action(cls, lot_id, action):
		"""Cancel one scheduled action without affecting the other schedule type."""
		lot = cls.query.filter_by(id=lot_id).first()
		if lot is None:
			return None
		lots, spots = cls._scope(lot)
		try:
			if action == 'delete':
				scheduled_at = lot.date_to_be_deleted
				if scheduled_at is None:
					return False
				if (
					lot.parent
					and lot.parent.date_to_be_deleted == scheduled_at
				):
					raise ValueError(
						"La eliminación está programada para el lote padre; cancélala desde su fila."
					)
				for item in lots:
					if item.date_to_be_deleted == scheduled_at:
						item.date_to_be_deleted = None
				for spot in spots:
					if spot.date_to_be_deleted == scheduled_at:
						spot.date_to_be_deleted = None
			elif action == 'deactivate':
				scheduled_date = lot.date_to_be_deactivated
				if scheduled_date is None:
					return False
				if (
					lot.parent
					and lot.parent.date_to_be_deactivated == scheduled_date
				):
					raise ValueError(
						"La desactivación está programada para el lote padre; cancélala desde su fila."
					)
				for item in lots:
					if item.date_to_be_deactivated == scheduled_date:
						item.date_to_be_deactivated = None
			else:
				raise ValueError("La acción programada no es válida.")
			db.session.commit()
		except Exception:
			db.session.rollback()
			raise
		return True

	@classmethod
	def request_deactivation(cls, lot_id, override, scheduled_date=None):
		lot = cls.query.filter_by(id=lot_id).first()
		if lot is None:
			return None

		lots, spots = cls._scope(lot)
		blockers = cls._blocking_reservations(spots)
		minimum_datetime = cls._minimum_deactivation_datetime(blockers)
		scheduled_date = cls._normalize_deletion_datetime(scheduled_date)

		if override:
			if scheduled_date is not None:
				raise ValueError('La desactivación inmediata no debe incluir una fecha programada.')
			return cls._apply_lot_transaction(lot, 'deactivate')

		if scheduled_date is not None:
			if scheduled_date < minimum_datetime:
				raise SchedulingRequired(
					minimum_datetime, lot_id, 'desactivar el lote',
					has_pending_reservations=bool(blockers),
				)
			deletion_date = lot.date_to_be_deleted
			if deletion_date is not None:
				for item in lots:
					if item.date_to_be_deleted == deletion_date:
						item.date_to_be_deleted = None
				for spot in spots:
					if spot.date_to_be_deleted == deletion_date:
						spot.date_to_be_deleted = None
			try:
				for item in lots:
					item.date_to_be_deactivated = scheduled_date
				db.session.commit()
			except Exception:
				db.session.rollback()
				raise
			return {'status': 'scheduled', 'date_to_be_deactivated': scheduled_date}

		if blockers:
			raise SchedulingRequired(
				minimum_datetime, lot_id, 'desactivar el lote',
				has_pending_reservations=True,
			)
		return cls._apply_lot_transaction(lot, 'deactivate')

	@classmethod
	def reservable_until(cls, lot_id):
		lot = cls.query.filter_by(id=lot_id).first()
		if lot is None:
			return None
		dates = [
			lot.date_to_be_deleted,
			lot.date_to_be_deactivated,
		]
		if lot.parent_id is not None:
			dates.extend([
				lot.parent.date_to_be_deleted,
				lot.parent.date_to_be_deactivated,
			])
		dates = [item for item in dates if item is not None]
		return min(dates) if dates else None

	@classmethod
	def process_due_scheduled_actions(cls, today=None):
		"""Process lot deletions and deactivations that have reached their schedule."""
		current = cls._now()
		if isinstance(today, datetime):
			current = today
		elif today is not None:
			current = datetime.combine(today, time.max)
		result = {'deleted': [], 'deactivated': [], 'canceled': []}

		deletions = cls.query.filter(
			cls.date_to_be_deleted.isnot(None),
			cls.date_to_be_deleted <= current,
		).all()
		for lot in deletions:
			if cls.query.filter_by(id=lot.id).first() is None:
				continue
			applied = cls._apply_lot_transaction(
				lot,
				'delete',
				reason='Lot deleted by administrator',
			)
			result['deleted'].append(lot.id)
			for reservation in applied['canceled']:
				result['canceled'].append(reservation)

		deactivations = cls.query.filter(
			cls.date_to_be_deactivated.isnot(None),
			cls.date_to_be_deactivated <= current,
		).order_by(cls.parent_id.asc(), cls.id.asc()).all()
		for lot in deactivations:
			current_lot = cls.query.filter_by(id=lot.id).first()
			if (
				current_lot is None
				or current_lot.date_to_be_deactivated is None
				or current_lot.date_to_be_deactivated > current
			):
				continue
			applied = cls._apply_lot_transaction(current_lot, 'deactivate')
			result['deactivated'].append(current_lot.id)
			result['canceled'].extend(applied['canceled'])

		return result

	@classmethod
	def get_floors(cls, lot):
		"""Return a parent's floors in their persisted display order."""
		return sorted(lot.floors, key=lambda floor: floor.id)

	@classmethod
	def is_parent_lot(cls, lot):
		"""Parent lots remain editable even when they have no floors."""
		return lot is not None and lot.parent_id is None
