from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.database import db


PUERTO_RICO = ZoneInfo('America/Puerto_Rico')

class Spots(db.Model):
	__tablename__ = 'spots'

	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	is_accessible TINYINT DEFAULT 0,
	is_accessible = db.Column(db.Boolean, default=False)

	date_to_be_deleted = db.Column(db.DateTime, nullable=True)


	# 	lot_id int,
	# 	FOREIGN KEY (lot_id) REFERENCES lots(id)
	lot_id = db.Column(db.Integer, db.ForeignKey('lots.id'))
	lot = db.relationship('Lots', backref=db.backref('spots', lazy=True))

	def is_reservable_by(self, user):
		"""Accessible spots are kept for users who need one."""
		return not self.is_accessible or bool(user.requires_accessible_spot)

	@classmethod
	def _now(cls):
		return datetime.now(PUERTO_RICO).replace(tzinfo=None)

	@classmethod
	def process_due_deletions(cls, today=None):
		"""Delete due spots, or postpone one deletion when active reservations block it."""
		from app.models.Lots import Lots
		from app.models.Reservations import Reservation

		current = cls._now()
		if isinstance(today, datetime):
			current = today
		elif today is not None:
			current = datetime.combine(today, time.max)

		lot_ids_due = {
			lot.id
			for lot in Lots.query.filter(
				Lots.date_to_be_deleted.isnot(None),
				Lots.date_to_be_deleted <= current,
			).all()
		}

		result = {'deleted': [], 'postponed': [], 'admin_notices': []}
		candidates = cls.query.filter(
			cls.date_to_be_deleted.isnot(None),
			cls.date_to_be_deleted <= current,
		).all()
		for spot in candidates:
			if spot.lot_id in lot_ids_due:
				continue

			blockers = Reservation.query.filter(
				Reservation.spot_id == spot.id,
				Reservation.status == 'Active',
				Reservation.end_time >= cls._now(),
			).all()
			try:
				if blockers:
					new_date = datetime.combine(
						max(reservation.end_time for reservation in blockers).date()
						+ timedelta(days=1),
						time.min,
					)
					spot.date_to_be_deleted = new_date
					db.session.commit()
					result['postponed'].append((spot.id, new_date))
					result['admin_notices'].append((spot, new_date, blockers))
					continue

				reservations = Reservation.query.filter(
					Reservation.spot_id == spot.id
				).all()
				for reservation in reservations:
					reservation.spot_id = None
				spots = [spot]
				db.session.delete(spot)
				db.session.commit()
				result['deleted'].append(spot.id)
			except Exception:
				db.session.rollback()
				raise
		return result
