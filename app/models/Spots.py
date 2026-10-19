from app.database import db

class Spots(db.Model):
	__tablename__ = 'spots'

	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	is_accessible TINYINT DEFAULT 0,
	is_accessible = db.Column(db.Boolean, default=False)

	# 	lot_id int,
	# 	FOREIGN KEY (lot_id) REFERENCES lots(id)
	lot_id = db.Column(db.Integer, db.ForeignKey('lots.id'))
	lot = db.relationship('Lots', backref=db.backref('spots', lazy=True))
