CREATE DATABASE IF NOT EXISTS my_control
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE my_control;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(150) NOT NULL,
  category VARCHAR(50),
  brand VARCHAR(100),
  model_number VARCHAR(100),
  purchase_date DATE,
  purchase_price DECIMAL(10,2),
  store VARCHAR(150),
  notes TEXT,
  image_path VARCHAR(255),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_products_user_category (user_id, category)
);

CREATE TABLE warranties (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  warranty_type VARCHAR(50),
  start_date DATE,
  expiry_date DATE NOT NULL,
  provider VARCHAR(150),
  document_path VARCHAR(255),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  INDEX idx_warranties_expiry (expiry_date)
);

CREATE TABLE maintenance (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  task VARCHAR(200) NOT NULL,
  last_done_date DATE,
  next_due_date DATE,
  service_provider VARCHAR(150),
  cost DECIMAL(10,2),
  notes TEXT,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  INDEX idx_maintenance_due (next_due_date)
);
