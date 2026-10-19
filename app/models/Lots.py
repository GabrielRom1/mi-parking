from app.database import db

class Lots(db.Model):
	__tablename__ = 'lots'

	# 	id int AUTO_INCREMENT PRIMARY KEY
	id = db.Column(db.Integer, primary_key=True)
 
	# 	name varchar(50) NOT NULL UNIQUE,
	name = db.Column(db.String(50), unique=True, nullable=False)

	# 	location varchar(255) NOT NULL,
	location = db.Column(db.String(255), nullable=False)

	# 	is_paid TINYINT DEFAULT 0,
	is_paid = db.Column(db.Boolean, default=False)

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
