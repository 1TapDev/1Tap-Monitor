-- Database schema for the stock checker

-- Products table
CREATE TABLE IF NOT EXISTS products (
    pid VARCHAR(50) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2),
    url TEXT,
    image_url TEXT,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_check TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    in_stock BOOLEAN DEFAULT FALSE,
    last_in_stock TIMESTAMP WITH TIME ZONE,
    last_out_of_stock TIMESTAMP WITH TIME ZONE,
    data JSONB,
    module VARCHAR(100) NOT NULL
);

-- Create index for faster searches
CREATE INDEX IF NOT EXISTS idx_products_in_stock ON products(in_stock);
CREATE INDEX IF NOT EXISTS idx_products_module ON products(module);

-- Stores table
CREATE TABLE IF NOT EXISTS stores (
    id SERIAL PRIMARY KEY,
    store_id VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(50),
    zip VARCHAR(20),
    phone VARCHAR(20),
    latitude DECIMAL(9, 6),
    longitude DECIMAL(9, 6),
    module VARCHAR(100) NOT NULL,
    UNIQUE(store_id, module)
);

-- Product availability in stores
CREATE TABLE IF NOT EXISTS product_availability (
    id SERIAL PRIMARY KEY,
    pid VARCHAR(50) REFERENCES products(pid),
    store_id INT REFERENCES stores(id),
    available BOOLEAN DEFAULT FALSE,
    check_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    quantity INT,
    price DECIMAL(10, 2),
    UNIQUE(pid, store_id)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_product_availability_pid ON product_availability(pid);
CREATE INDEX IF NOT EXISTS idx_product_availability_store ON product_availability(store_id);

-- Alert history
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    pid VARCHAR(50) REFERENCES products(pid),
    alert_type VARCHAR(50) NOT NULL, -- 'new_product', 'in_stock', 'out_of_stock', etc.
    alert_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    message TEXT,
    webhook_sent BOOLEAN DEFAULT FALSE,
    data JSONB
);

-- Module configuration
CREATE TABLE IF NOT EXISTS module_config (
    module VARCHAR(100) PRIMARY KEY,
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP WITH TIME ZONE,
    next_run TIMESTAMP WITH TIME ZONE,
    interval_seconds INT DEFAULT 3600
);

-- Proxy table
CREATE TABLE IF NOT EXISTS proxies (
    id SERIAL PRIMARY KEY,
    proxy_string VARCHAR(255) NOT NULL UNIQUE,
    last_used TIMESTAMP WITH TIME ZONE,
    success_count INT DEFAULT 0,
    fail_count INT DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE
);

-- Tasks queue
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL, -- 'check_stock', 'scan_new', etc.
    module VARCHAR(100) NOT NULL,
    priority INT DEFAULT 5,
    data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    result JSONB,
    error TEXT
);

-- Create index for task processing
CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_module ON tasks(module);

-- Session cookies
CREATE TABLE IF NOT EXISTS cookies (
    id SERIAL PRIMARY KEY,
    module VARCHAR(100) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    cookies JSONB NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(module, domain)
);

-- Log table for debugging and metrics
CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(20) NOT NULL,
    module VARCHAR(100),
    message TEXT NOT NULL,
    data JSONB
);

-- Create index for log filtering
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_module ON logs(module);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);

-- Webhook configurations
CREATE TABLE IF NOT EXISTS webhooks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    url TEXT NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'discord', 'slack', 'custom', etc.
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB,
    UNIQUE(name)
);

-- Webhook event subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id SERIAL PRIMARY KEY,
    webhook_id INT REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'new_product', 'in_stock', 'out_of_stock', etc.
    module VARCHAR(100), -- NULL means all modules
    filter JSONB, -- Additional filtering criteria
    UNIQUE(webhook_id, event_type, module)
);

-- User-defined search queries
CREATE TABLE IF NOT EXISTS search_queries (
    id SERIAL PRIMARY KEY,
    module VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    url TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    interval_seconds INT DEFAULT 3600,
    last_run TIMESTAMP WITH TIME ZONE,
    next_run TIMESTAMP WITH TIME ZONE,
    UNIQUE(module, name)
);

-- Views for easy reporting

-- View for in-stock products with store details
CREATE OR REPLACE VIEW vw_in_stock_products AS
SELECT 
    p.pid,
    p.title,
    p.price,
    p.url,
    p.image_url,
    p.module,
    s.name AS store_name,
    s.address,
    s.city,
    s.state,
    s.zip,
    s.phone,
    pa.check_time
FROM 
    products p
JOIN 
    product_availability pa ON p.pid = pa.pid
JOIN 
    stores s ON pa.store_id = s.id
WHERE 
    pa.available = TRUE
ORDER BY 
    pa.check_time DESC;

-- View for product stock history (last 10 status changes)
CREATE OR REPLACE VIEW vw_product_stock_history AS
SELECT 
    pid,
    alert_type,
    alert_time,
    message
FROM 
    alert_history
WHERE 
    alert_type IN ('in_stock', 'out_of_stock')
ORDER BY 
    alert_time DESC
LIMIT 10;

-- View for pending tasks
CREATE OR REPLACE VIEW vw_pending_tasks AS
SELECT 
    id,
    task_type,
    module,
    priority,
    data,
    created_at,
    scheduled_at,
    attempts,
    max_attempts
FROM 
    tasks
WHERE 
    status = 'pending'
    AND scheduled_at <= CURRENT_TIMESTAMP
ORDER BY 
    priority DESC, 
    scheduled_at ASC;

-- Functions

-- Function to add a task to check stock for a product
CREATE OR REPLACE FUNCTION add_stock_check_task(
    p_pid VARCHAR(50),
    p_module VARCHAR(100),
    p_priority INT DEFAULT 5
) RETURNS INT AS $
DECLARE
    task_id INT;
BEGIN
    INSERT INTO tasks (
        task_type,
        module,
        priority,
        data
    ) VALUES (
        'check_stock',
        p_module,
        p_priority,
        jsonb_build_object('pid', p_pid)
    ) RETURNING id INTO task_id;
    
    RETURN task_id;
END;
$ LANGUAGE plpgsql;

-- Function to add a task to scan for new products
CREATE OR REPLACE FUNCTION add_scan_task(
    p_module VARCHAR(100),
    p_url TEXT DEFAULT NULL,
    p_priority INT DEFAULT 3
) RETURNS INT AS $
DECLARE
    task_id INT;
    task_data JSONB;
BEGIN
    IF p_url IS NULL THEN
        task_data := '{}';
    ELSE
        task_data := jsonb_build_object('url', p_url);
    END IF;
    
    INSERT INTO tasks (
        task_type,
        module,
        priority,
        data
    ) VALUES (
        'scan_new',
        p_module,
        p_priority,
        task_data
    ) RETURNING id INTO task_id;
    
    RETURN task_id;
END;
$ LANGUAGE plpgsql;

-- Function to log stock events and trigger notifications
CREATE OR REPLACE FUNCTION log_stock_event(
    p_pid VARCHAR(50),
    p_alert_type VARCHAR(50),
    p_message TEXT,
    p_data JSONB DEFAULT NULL
) RETURNS INT AS $
DECLARE
    alert_id INT;
BEGIN
    -- Insert the alert
    INSERT INTO alert_history (
        pid,
        alert_type,
        message,
        data
    ) VALUES (
        p_pid,
        p_alert_type,
        p_message,
        p_data
    ) RETURNING id INTO alert_id;
    
    -- Update the product status
    IF p_alert_type = 'in_stock' THEN
        UPDATE products
        SET in_stock = TRUE,
            last_in_stock = CURRENT_TIMESTAMP
        WHERE pid = p_pid;
    ELSIF p_alert_type = 'out_of_stock' THEN
        UPDATE products
        SET in_stock = FALSE,
            last_out_of_stock = CURRENT_TIMESTAMP
        WHERE pid = p_pid;
    END IF;
    
    RETURN alert_id;
END;
$ LANGUAGE plpgsql;

-- Triggers

-- Trigger to schedule a stock check when a new product is added
CREATE OR REPLACE FUNCTION trigger_stock_check_on_new_product()
RETURNS TRIGGER AS $
BEGIN
    PERFORM add_stock_check_task(NEW.pid, NEW.module, 8);
    RETURN NEW;
END;
$ LANGUAGE plpgsql;

CREATE TRIGGER trg_new_product_stock_check
AFTER INSERT ON products
FOR EACH ROW
EXECUTE FUNCTION trigger_stock_check_on_new_product();

-- Trigger to update product's last_check timestamp when availability is checked
CREATE OR REPLACE FUNCTION update_product_last_check()
RETURNS TRIGGER AS $
BEGIN
    UPDATE products
    SET last_check = CURRENT_TIMESTAMP
    WHERE pid = NEW.pid;
    RETURN NEW;
END;
$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_product_last_check
AFTER INSERT OR UPDATE ON product_availability
FOR EACH ROW
EXECUTE FUNCTION update_product_last_check();
