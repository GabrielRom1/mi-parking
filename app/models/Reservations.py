# CREATE TABLE reservations(
from app.database import db

class Reservation(db.Model):
	__tablename__ = 'reservations'

	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	user_id int NOT NULL,
	# 	FOREIGN KEY (user_id) REFERENCES users(id),
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
	user = db.relationship('User', backref=db.backref('reservations', lazy=True))

	# 	spot_id int NOT NULL,
	# 	FOREIGN KEY (spot_id) REFERENCES spots(id)
	spot_id = db.Column(db.Integer, db.ForeignKey('spots.id'))
	spot = db.relationship('Spots', backref=db.backref('reservations', lazy=True))

	# 	start_time DATETIME NOT NULL,
	start_time = db.Column(db.DateTime, nullable=False)

	# 	end_time DATETIME NOT NULL,
	end_time = db.Column(db.DateTime, nullable=False)

	incident_report = db.relationship('IncidentReport', back_populates='reservation', uselist=False)

	# 	status ENUM('Active', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Active',
	status = db.Column(db.Enum('Active', 'Completed', 'Cancelled', name='reservation_status'), nullable=False, default='Active')

	# 	check_in_time DATETIME NULL,
	check_in_time = db.Column(db.DateTime, nullable=True)

	# 	check_out_time DATETIME NULL,
	check_out_time = db.Column(db.DateTime, nullable=True)

	# 	cancelation_reason TEXT NULL,
	cancelation_reason = db.Column(db.Text, nullable=True)

	
