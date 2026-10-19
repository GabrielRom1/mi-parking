
CREATE TABLE users (
	id int AUTO_INCREMENT PRIMARY KEY,
	email varchar(255) NOT NULL UNIQUE,
	first_name varchar(255) NOT NULL,
	last_name varchar(255) NOT NULL,
	password_hash varchar(255) NOT NULL,
	role_id int NULL,
	requires_accessible_spot TINYINT DEFAULT 0,
	FOREIGN KEY (role_id) REFERENCES roles(id)
);



CREATE TABLE lots(
	id int AUTO_INCREMENT PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	location varchar(255) NOT NULL,
	is_paid TINYINT DEFAULT 0,
	is_active TINYINT DEFAULT 1,
	parent_id int NULL,
	accessible TINYINT DEFAULT 0,
	role_id int NULL,
	FOREIGN KEY (role_id) REFERENCES roles(id),
	FOREIGN KEY (parent_id) REFERENCES lots(id)
);


CREATE TABLE roles(
	id int AUTO_INCREMENT PRIMARY KEY,
	name varchar(20) NOT NULL UNIQUE,
	description TEXT NULL
);


CREATE TABLE spots(
	id int AUTO_INCREMENT PRIMARY KEY,
	lot_id int,
	is_accessible TINYINT DEFAULT 0,
	FOREIGN KEY (lot_id) REFERENCES lots(id)
);



CREATE TABLE reservations(
	id int AUTO_INCREMENT PRIMARY KEY,
	user_id int NOT NULL,
	spot_id int NOT NULL,

	start_time DATETIME NOT NULL,
	end_time DATETIME NOT NULL,
	status ENUM('Active', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Active',

	check_in_time DATETIME NULL,
	check_out_time DATETIME NULL,
	cancelation_reason TEXT NULL,

	FOREIGN KEY (user_id) REFERENCES users(id),
	FOREIGN KEY (spot_id) REFERENCES spots(id)
);



CREATE TABLE incident_report(
	id int AUTO_INCREMENT PRIMARY KEY,
	user_id int NOT NULL,
	reservation_id int NOT NULL,


	description TEXT NULL,
	photo_path varchar(255) NULL,
	incident_type ENUM('Spot Occupied by Unauthorized Vehicle', 'Spot Blocked/Inaccessible', 'Other') NOT NULL,
	status ENUM('Open', 'In Progress', 'Resolved') NOT NULL DEFAULT 'Open',
	admin_notes TEXT NULL,

	FOREIGN KEY (user_id) REFERENCES users(id),
	FOREIGN KEY (reservation_id) REFERENCES reservations(id)
);

