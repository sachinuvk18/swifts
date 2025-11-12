
-- SwiftServe v3 schema for PostgreSQL (supports both online/local video)
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS menu_items;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS users;

CREATE TABLE users(
  id SERIAL PRIMARY KEY,
  username VARCHAR(150) NOT NULL,
  gmail VARCHAR(255) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role VARCHAR(30) NOT NULL CHECK (role IN ('customer','restaurant','agent')),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE restaurants(
  id SERIAL PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(200) NOT NULL,
  address TEXT,
  cuisine VARCHAR(100),
  image_path TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE menu_items(
  id SERIAL PRIMARY KEY,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  name VARCHAR(200) NOT NULL,
  description TEXT,
  price NUMERIC(10,2) NOT NULL DEFAULT 0.00,
  image_path TEXT,
  video_path TEXT,
  video_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders(
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  total_amount NUMERIC(10,2) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'Placed',
  delivery_name VARCHAR(120),
  delivery_phone VARCHAR(30),
  delivery_address TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE order_items(
  id SERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  item_id INTEGER REFERENCES menu_items(id) ON DELETE SET NULL,
  name VARCHAR(200) NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  qty INTEGER NOT NULL
);


select * from users;

DELETE FROM users;

select* from order_items;

-- New Role: Delivery Agent
CREATE TABLE delivery_agents (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    gmail VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'available'
);

-- Add delivery_agent_id to orders table
ALTER TABLE orders ADD COLUMN delivery_agent_id INTEGER REFERENCES delivery_agents(id);

-- Add new statuses for delivery flow
-- Placed → Preparing → Ready → Picked Up → Out for Delivery → Delivered

select * from users;

DELETE FROM users
WHERE gmail = 'anil@gmail.com';

ALTER TABLE orders
ADD COLUMN agent_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Ensure order statuses support full flow:
-- Placed → Preparing → Ready → Out for Delivery → Delivered → Rejected

