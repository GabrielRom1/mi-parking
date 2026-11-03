CREATE TABLE roles (
	id int AUTO_INCREMENT PRIMARY KEY,
	name varchar(20) NOT NULL UNIQUE,
	description varchar(500) NULL
);

CREATE TABLE users (
	id int AUTO_INCREMENT PRIMARY KEY,
	email varchar(320) NOT NULL UNIQUE,
	first_name varchar(100) NOT NULL,
	last_name varchar(100) NOT NULL,
	password_hash varchar(255) NOT NULL,
	requires_accessible_spot TINYINT DEFAULT 0,
	role_id int NULL,
	FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE lots (
	id int AUTO_INCREMENT PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	location varchar(255) NOT NULL,
	is_paid TINYINT DEFAULT 0,
	date_to_be_deleted DATE NULL,
	is_active TINYINT DEFAULT 1,
	parent_id int NULL,
	accessible TINYINT DEFAULT 0,
	role_id int NULL,
	FOREIGN KEY (parent_id) REFERENCES lots(id),
	FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE spots (
	id int AUTO_INCREMENT PRIMARY KEY,
	is_accessible TINYINT DEFAULT 0,
	date_to_be_deleted DATE NULL,
	lot_id int NULL,
	FOREIGN KEY (lot_id) REFERENCES lots(id)
);

CREATE TABLE reservations (
	id int AUTO_INCREMENT PRIMARY KEY,
	user_id int NULL,
	spot_id int NULL,
	start_time DATETIME NOT NULL,
	end_time DATETIME NOT NULL,
	status ENUM('Active', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Active',
	check_in_time DATETIME NULL,
	check_out_time DATETIME NULL,
	cancelation_reason varchar(500) NULL,
	FOREIGN KEY (user_id) REFERENCES users(id),
	FOREIGN KEY (spot_id) REFERENCES spots(id)
);

CREATE TABLE incident_reports (
	id int AUTO_INCREMENT PRIMARY KEY,
	user_id int NULL,
	reservation_id int NOT NULL UNIQUE,
	description varchar(500) NULL,
	photo_path varchar(255) NULL,
	incident_type ENUM('Spot Occupied by Unauthorized Vehicle', 'Spot Blocked/Inaccessible', 'Other') NOT NULL,
	status ENUM('Open', 'In Progress', 'Resolved') NOT NULL,
	admin_notes varchar(500) NULL,
	FOREIGN KEY (user_id) REFERENCES users(id),
	FOREIGN KEY (reservation_id) REFERENCES reservations(id)
);
