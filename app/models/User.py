from app.database import db

class User(db.Model):
	__tablename__ = 'users'

	# CREATE TABLE users (
	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	email varchar(255) NOT NULL UNIQUE,
	email = db.Column(db.String(255), unique=True, nullable=False, index=True)

	# 	first_name varchar(255) NOT NULL,
	first_name = db.Column(db.String(255), nullable=False)

	# 	last_name varchar(255) NOT NULL,
	last_name = db.Column(db.String(255), nullable=False)

	# 	password_hash varchar(255) NOT NULL,
	password_hash = db.Column(db.String(255), nullable=False)

	# 	requires_accessible_spot TINYINT DEFAULT 0,
	requires_accessible_spot = db.Column(db.Boolean, default=False)

	# 	role_id int NULL,
	# 	FOREIGN KEY (role_id) REFERENCES roles(id)
	role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
	role = db.relationship('Role', back_populates='users')
