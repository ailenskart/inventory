-- Initialize databases for all services
CREATE DATABASE mlflow;
CREATE DATABASE dagster;
CREATE DATABASE feast;

-- Create schemas in the main database
\c lenskart_retail;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS ml;

-- Core tables for app metadata
CREATE TABLE IF NOT EXISTS raw.stores (
    store_id VARCHAR(32) PRIMARY KEY,
    store_name VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    state VARCHAR(100),
    region VARCHAR(50),
    pincode VARCHAR(10),
    store_type VARCHAR(20),
    store_format VARCHAR(20),
    cluster_id VARCHAR(32),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    opening_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    display_capacity INTEGER DEFAULT 0,
    storage_capacity INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.skus (
    sku_id VARCHAR(32) PRIMARY KEY,
    product_name VARCHAR(255),
    brand VARCHAR(100),
    category VARCHAR(50),
    subcategory VARCHAR(50),
    gender VARCHAR(10),
    frame_type VARCHAR(50),
    frame_shape VARCHAR(50),
    frame_material VARCHAR(50),
    frame_color VARCHAR(50),
    lens_type VARCHAR(50),
    size VARCHAR(20),
    mrp NUMERIC(10,2) DEFAULT 0,
    cost_price NUMERIC(10,2) DEFAULT 0,
    fulfillment_type VARCHAR(20) DEFAULT 'order_capture',
    is_display_only BOOLEAN DEFAULT FALSE,
    lifecycle_stage VARCHAR(20) DEFAULT 'active',
    vendor_id VARCHAR(32),
    lead_time_days INTEGER DEFAULT 7,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.vendors (
    vendor_id VARCHAR(32) PRIMARY KEY,
    vendor_name VARCHAR(255),
    vendor_type VARCHAR(50),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(100),
    avg_lead_time_days INTEGER DEFAULT 7,
    min_order_value NUMERIC(12,2) DEFAULT 0,
    min_order_qty INTEGER DEFAULT 0,
    reliability_score NUMERIC(3,2) DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.daily_sales (
    store_id VARCHAR(32),
    sku_id VARCHAR(32),
    sale_date DATE,
    qty_sold INTEGER DEFAULT 0,
    revenue NUMERIC(12,2) DEFAULT 0,
    discount NUMERIC(12,2) DEFAULT 0,
    fulfillment_type VARCHAR(20),
    is_return BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (store_id, sku_id, sale_date)
);

CREATE TABLE IF NOT EXISTS raw.daily_inventory (
    store_id VARCHAR(32),
    sku_id VARCHAR(32),
    snapshot_date DATE,
    on_hand_qty INTEGER DEFAULT 0,
    on_display_qty INTEGER DEFAULT 0,
    in_storage_qty INTEGER DEFAULT 0,
    in_transit_qty INTEGER DEFAULT 0,
    allocated_qty INTEGER DEFAULT 0,
    available_qty INTEGER DEFAULT 0,
    PRIMARY KEY (store_id, sku_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS raw.store_trials (
    trial_id VARCHAR(64) PRIMARY KEY,
    store_id VARCHAR(32),
    sku_id VARCHAR(32),
    trial_date DATE,
    trial_time TIMESTAMP,
    customer_id VARCHAR(32),
    resulted_in_order BOOLEAN DEFAULT FALSE,
    order_id VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS raw.store_traffic (
    store_id VARCHAR(32),
    traffic_date DATE,
    footfall_count INTEGER DEFAULT 0,
    walk_ins INTEGER DEFAULT 0,
    appointments INTEGER DEFAULT 0,
    PRIMARY KEY (store_id, traffic_date)
);
