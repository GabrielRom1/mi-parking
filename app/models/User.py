from app.database import db

class User(db.Model):
	__tablename__ = 'users'

	# CREATE TABLE users (
	# 	id int AUTO_INCREMENT PRIMARY KEY,
	id = db.Column(db.Integer, primary_key=True)

	# 	email varchar(320)) NOT NULL UNIQUE,
	email = db.Column(db.String(320), unique=True, nullable=False, index=True)

	# 	first_name varchar(100) NOT NULL,
	first_name = db.Column(db.String(100), nullable=False)

	# 	last_name varchar(100) NOT NULL,
	last_name = db.Column(db.String(100), nullable=False)

	# 	password_hash varchar(255) NOT NULL,
	password_hash = db.Column(db.String(255), nullable=False)

	# 	requires_accessible_spot TINYINT DEFAULT 0,
	requires_accessible_spot = db.Column(db.Boolean, default=False)

	# 	role_id int NULL,
	# 	FOREIGN KEY (role_id) REFERENCES roles(id)
	role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
	role = db.relationship('Role', back_populates='users')

	@classmethod
	def get_user_by_id(cls, user_id):
		"""Return a user for route authorization without querying outside the model."""
		return cls.query.filter_by(id=user_id).first()

	@classmethod
	def get_user_by_email(cls, email):
		normalized_email = email.strip().lower()
		return cls.query.filter(
			db.func.lower(cls.email) == normalized_email
		).first()

	@property
	def is_admin(self):
		return self.role is not None and self.role.name == 'admin'

	def update_profile(self, email, first_name, last_name, requires_accessible_spot):
		"""Save the fields the user can edit on /profile. Every page reads the user
		from the DB on each request, so the change shows up everywhere right away."""
		self.email = email.strip().lower()
		self.first_name = first_name.strip()
		self.last_name = last_name.strip()
		self.requires_accessible_spot = requires_accessible_spot
		db.session.commit()

	def update_password(self, password_hash):
		self.password_hash = password_hash
		db.session.commit()

	@classmethod
	def create_user(
		cls,
		email,
		first_name,
		last_name,
		password_hash,
		requires_accessible_spot,
		role,
	):
		return cls(
			email=email.strip().lower(),
			first_name=first_name.strip(),
			last_name=last_name.strip(),
			password_hash=password_hash,
			requires_accessible_spot=requires_accessible_spot,
			role=role,
		)
