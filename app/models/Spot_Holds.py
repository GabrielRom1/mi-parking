from app.database import db

class SpotHold(db.Model):
	"""A spot set aside for a few minutes while a user looks at a Quick Find suggestion (SRS REQ.5.1)."""
	__tablename__ = 'spot_holds'

	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	spot_id int NOT NULL,
	# 	FOREIGN KEY (spot_id) REFERENCES spots(id),
	spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'), nullable=False)

	# 	user_id int NOT NULL,
	# 	FOREIGN KEY (user_id) REFERENCES users(id),
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

	# 	start_time DATETIME NOT NULL,
	start_time = db.Column(db.DateTime, nullable=False)

	# 	end_time DATETIME NOT NULL,
	end_time = db.Column(db.DateTime, nullable=False)

	# 	expires_at DATETIME NOT NULL
	expires_at = db.Column(db.DateTime, nullable=False)

	@classmethod
	def held_by_others(cls, spot_ids, start, end, user_id, current):
		"""IDs of the spots someone else is holding for any part of [start, end)."""
		if not spot_ids:
			return set()
		return {
			spot_id
			for (spot_id,) in cls.query.filter(
				cls.spot_id.in_(spot_ids),
				cls.user_id != user_id,
				cls.expires_at > current,
				cls.start_time < end,
				cls.end_time > start,
			).with_entities(cls.spot_id)
		}

	@classmethod
	def release_for_user(cls, user_id):
		"""The caller commits."""
		cls.query.filter(cls.user_id == user_id).delete()

	@classmethod
	def delete_expired(cls, current):
		"""The caller commits."""
		cls.query.filter(cls.expires_at <= current).delete()
