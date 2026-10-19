from app.database import db

class IncidentReport(db.Model):
	__tablename__ = 'incident_reports'

	# id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)
 
	# user_id int NOT NULL,
	# FOREIGN KEY (user_id) REFERENCES users(id),
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
	user = db.relationship('User', backref=db.backref('incident_reports', lazy=True))

	# reservation_id int NOT NULL,
	# FOREIGN KEY (reservation_id) REFERENCES reservations(id) unique,
	reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False, unique=True)
	reservation = db.relationship('Reservation', back_populates='incident_report', uselist=False)

	# description TEXT NULL,
	description = db.Column(db.Text, nullable=True)

	# photo_path varchar(255) NULL,
	photo_path = db.Column(db.String(255), nullable=True)

	# incident_type ENUM('Spot Occupied by Unauthorized Vehicle', 'Spot Blocked/Inaccessible', 'Other') NOT NULL,
	incident_type = db.Column(db.Enum('Spot Occupied by Unauthorized Vehicle', 'Spot Blocked/Inaccessible', 'Other'), nullable=False)

	# status ENUM('Open', 'In Progress', 'Resolved') NOT NULL DEFAULT 'Open',
	status = db.Column(db.Enum('Open', 'In Progress', 'Resolved'), nullable=False)

	admin_notes = db.Column(db.Text, nullable=True)

 