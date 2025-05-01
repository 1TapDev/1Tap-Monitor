
📦 Suggested Project Structure

project/
│
├── modules/                  # Website-specific logic
│   ├── booksamillion.py
│   ├── popshelf.py
│   └── ...
│
├── proxies.txt               # ip:port:user:pass list
├── config.json               # Global config, Discord webhook, item keywords, etc
├── main.py                   # Runner, GUI or CLI logic
├── dispatcher.py             # Loads modules, manages threading/scheduling
├── notifier.py               # Sends alerts to Discord
├── proxy_manager.py          # Handles rotating proxies
└── utils/                    # Shared tools (headers, bypass tools, logging)
You're helping build a modular Python web scraper that checks stock for specific items across multiple retail websites and sends alerts to Discord using webhooks.
🧩 Core features:
* Each website will be a separate Python module (e.g., booksamillion.py, popshelf.py).
* The main program should support loading these modules dynamically and running them either concurrently (multithreaded) or one-by-one.
* I want to be able to add, edit, or remove modules without restarting the entire program.
* Proxy support using ip:port:user:pass from a text file (over 1000+ proxies).
* Optional GUI (Tkinter or simple web dashboard), or a CLI-based module controller.
* Cloudflare/anti-bot bypass support using request-based tools (tls-client, cloudscraper, or similar).
* Each module will be built separately. I will send you the request info (URL, headers, cookies) and you will turn that into a module.
🛠 Start by generating the boilerplate and structure:
1. main.py that initializes the system.
2. dispatcher.py that loads modules, handles threading.
3. notifier.py to send messages to Discord via webhook.
4. proxy_manager.py that reads proxies and returns a rotating one.
5. One working module (e.g., booksamillion.py) that shows the interface and logic to follow.
Let’s get the base skeleton ready so I can drop in modules later.
🔧 Suggestions for Additional Improvements
* Logging: Log each module’s run (errors, success, requests sent).
* Hot reload: Use importlib.reload() to live-reload a modified module.
* Module config overrides: Let each module have its own config_booksamillion.json.
* Cooldowns per module: Custom time intervals (e.g., check popshelf every 5 mins, booksamillion every 2).
* CLI menu: Start/stop modules, see status, load/unload modules.
* Alerts customization: Add item name, image, link, and store name to Discord alerts.

I'll help you build a modular web scraper with the features you've outlined. Let's start by creating the core structure that will let you easily add website modules later.

Let me create the foundation code for each of the main components:


main.py
Code 

dispatcher.py
Code 

notifier.py
Code 

Untitled
Text 




Continue

Can you create the config

I'll create the proxy_manager.py file and a default config.json file for you.


proxy_manager.py
Code ∙ Version 2 

config.json
Code 
Now let's create a sample module for Books-A-Million that demonstrates how to structure a module and check stock:


modules/booksamillion.py
Code 
Let's create a utility module with shared functions for headers generation, bypassing protections, and other common tasks:


utils/headers_generator.py
Code 

utils/cloudflare_bypass.py
Code 





67_Response.txt
2,089 lines

txt


130_Request.txt
26 lines

txt


115_Request.txt
26 lines

txt


101_Request.txt
26 lines

txt


67_Request.txt
27 lines

txt


4_Full.txt
43 lines

txt

Continue building the booksamillion.py module using the architecture we discussed.
Cloudflare Cookie Bypass Logic:
* cf_clearance and __cf_bm cookies expire frequently.
* Implement a bypass system using cloudflare_bypass.py that:
   * Launches a headless browser (or TLS client) to access the site homepage
   * Waits until cookies are set (cf_clearance, etc.)
   * Extracts the cookies and stores them for later use
   * Updates config.json or a shared cookie handler with fresh values
* Reuse these cookies in the stock-check request header.
* Fallback: if a request fails due to 403 or bot protection, force regeneration.
Stock Check by PID:
* Accept a list of PIDs from task queue or DB
* For each PID, send the request in 4_Full.txt, but change:
   * "radius": 250
   * "pid": "<CURRENT_PID>"
* Parse response:
   * From pidinfo: title, retail_price, publish_date, td_url
   * From ResultList: availability, address1, address2, city, postcode, phone
PostgreSQL Behavior:
* Table: booksamillion_products
* Store PID data + list of stores as JSONB
* Track timestamps for last_seen_instock, last_seen_outstock
* On new PID: insert + alert via webhook
* On stock status change: update + send updated alert
Search for New Items:
* Use 4 search URLs (67_Request.txt, 101_Request.txt, etc.)
* Extract PIDs from HTML like:

html
CopyEdit
<a href="https://www.booksamillion.com/wishlist?pid=F820650412493&...
* If not in DB, add PID, trigger initial stock check + Discord alert
Proxies + Multithreading:
* Rotate from proxies.txt using proxy_manager.py
* Allow modules to run independently in threads or async tasks
Please continue generating booksamillion.py, broken into clear sections:
* def get_fresh_cookies()
* def check_stock(pid)
* def scan_new_items()
* def main_monitor_loop()

I'll continue creating the booksamillion.py module with all the requested features. Based on the website response data and structure, I'll implement a comprehensive module that handles Cloudflare bypassing, stock checking, and product discovery.


modules/booksamillion.py
Code ∙ Version 2 
Now, let's create the utils/cloudflare_bypass.py module to complete the functionality:


utils/cloudflare_bypass.py
Code ∙ Version 2 




Continue

I'll continue implementing the utils/cloudflare_bypass.py module:


utils/cloudflare_bypass.py
Code ∙ Version 3 
Let me create a utility file for parsing HTML to extract product information:


utils/html_parser.py
Code 
Let's create a schema file for the database:


database/schema.sql
Code 




Continue

I'll continue implementing the database schema file:


database/schema.sql
Code 
Now, let's create a database utility file to interface with either PostgreSQL or use SQLite as a fallback:


utils/database.py
Code 

Continue

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
