#!/usr/bin/env python3
"""
Database Utility Module
Provides database connection and operations for the stock checker.
Can use either PostgreSQL (preferred) or SQLite (fallback).
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("Database")

# Try to import PostgreSQL adapter
try:
    import psycopg2
    import psycopg2.extras

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.warning("psycopg2 not available, falling back to SQLite")


class Database:
    """Database connection and operations manager"""

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize database connection

        Args:
            config: Database configuration. If None, uses environment variables or defaults
        """
        self.config = config or {}
        self.connection = None
        self.db_type = "postgres" if POSTGRES_AVAILABLE else "sqlite"

        # Get database config from environment if not provided
        if not self.config:
            self._load_config_from_env()

        # Connect to database
        self.connect()

    def _load_config_from_env(self):
        """Load database configuration from environment variables"""
        if POSTGRES_AVAILABLE:
            self.config = {
                "host": os.environ.get("DB_HOST", "localhost"),
                "port": os.environ.get("DB_PORT", 5432),
                "database": os.environ.get("DB_NAME", "stockchecker"),
                "user": os.environ.get("DB_USER", "postgres"),
                "password": os.environ.get("DB_PASSWORD", ""),
            }
        else:
            self.config = {
                "database": os.environ.get("DB_FILE", "stockchecker.db"),
            }

    def connect(self):
        """Connect to the database"""
        if self.connection:
            return

        try:
            if self.db_type == "postgres":
                self.connection = psycopg2.connect(
                    host=self.config.get("host"),
                    port=self.config.get("port"),
                    database=self.config.get("database"),
                    user=self.config.get("user"),
                    password=self.config.get("password")
                )
                # Configure connection to handle JSON
                psycopg2.extras.register_default_jsonb(self.connection)
                logger.info(f"Connected to PostgreSQL database: {self.config.get('database')}")
            else:
                db_path = Path(self.config.get("database", "stockchecker.db"))
                self.connection = sqlite3.connect(db_path)
                # Enable foreign keys
                self.connection.execute("PRAGMA foreign_keys = ON")
                # Configure connection to handle JSON
                self.connection.row_factory = sqlite3.Row
                logger.info(f"Connected to SQLite database: {db_path}")

                # Initialize SQLite database if needed
                self._init_sqlite_schema()

        except Exception as e:
            logger.error(f"Error connecting to database: {str(e)}")
            raise

    def disconnect(self):
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from database")

    def _init_sqlite_schema(self):
        """Initialize SQLite database schema if needed"""
        # Define SQLite-compatible schema
        schema_sql = """
        -- Products table
        CREATE TABLE IF NOT EXISTS products (
            pid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            price REAL,
            url TEXT,
            image_url TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            in_stock INTEGER DEFAULT 0,
            last_in_stock TIMESTAMP,
            last_out_of_stock TIMESTAMP,
            data TEXT,
            module TEXT NOT NULL
        );

        -- Create index for faster searches
        CREATE INDEX IF NOT EXISTS idx_products_in_stock ON products(in_stock);
        CREATE INDEX IF NOT EXISTS idx_products_module ON products(module);

        -- Stores table
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            phone TEXT,
            latitude REAL,
            longitude REAL,
            module TEXT NOT NULL,
            UNIQUE(store_id, module)
        );

        -- Product availability in stores
        CREATE TABLE IF NOT EXISTS product_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pid TEXT REFERENCES products(pid),
            store_id INTEGER REFERENCES stores(id),
            available INTEGER DEFAULT 0,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quantity INTEGER,
            price REAL,
            UNIQUE(pid, store_id)
        );

        -- Create index for faster lookups
        CREATE INDEX IF NOT EXISTS idx_product_availability_pid ON product_availability(pid);
        CREATE INDEX IF NOT EXISTS idx_product_availability_store ON product_availability(store_id);

        -- Alert history
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pid TEXT REFERENCES products(pid),
            alert_type TEXT NOT NULL,
            alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message TEXT,
            webhook_sent INTEGER DEFAULT 0,
            data TEXT
        );

        -- Module configuration
        CREATE TABLE IF NOT EXISTS module_config (
            module TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            interval_seconds INTEGER DEFAULT 3600
        );

        -- Proxy table
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy_string TEXT NOT NULL UNIQUE,
            last_used TIMESTAMP,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1
        );

        -- Tasks queue
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            module TEXT NOT NULL,
            priority INTEGER DEFAULT 5,
            data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            result TEXT,
            error TEXT
        );

        -- Create index for task processing
        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority);
        CREATE INDEX IF NOT EXISTS idx_tasks_module ON tasks(module);

        -- Session cookies
        CREATE TABLE IF NOT EXISTS cookies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            domain TEXT NOT NULL,
            cookies TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            UNIQUE(module, domain)
        );

        -- Log table for debugging and metrics
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL,
            module TEXT,
            message TEXT NOT NULL,
            data TEXT
        );

        -- Create index for log filtering
        CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
        CREATE INDEX IF NOT EXISTS idx_logs_module ON logs(module);
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);

        -- Webhook configurations
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            config TEXT,
            UNIQUE(name)
        );

        -- Webhook event subscriptions
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER REFERENCES webhooks(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            module TEXT,
            filter TEXT,
            UNIQUE(webhook_id, event_type, module)
        );

        -- User-defined search queries
        CREATE TABLE IF NOT EXISTS search_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            interval_seconds INTEGER DEFAULT 3600,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            UNIQUE(module, name)
        );
        """

        cursor = self.connection.cursor()
        cursor.executescript(schema_sql)
        self.connection.commit()
        cursor.close()
        logger.info("Initialized SQLite database schema")

    def get_cursor(self):
        """Get a database cursor"""
        if not self.connection:
            self.connect()

        if self.db_type == "postgres":
            return self.connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            return self.connection.cursor()

    def add_product(self, product: Dict[str, Any]) -> bool:
        """
        Add a new product to the database

        Args:
            product: Product data dictionary

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Convert JSON fields for database storage
            data_json = json.dumps(product.get("data", {}))

            if self.db_type == "postgres":
                sql = """
                INSERT INTO products 
                    (pid, title, price, url, image_url, in_stock, data, module)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pid) DO UPDATE
                SET 
                    title = EXCLUDED.title,
                    price = EXCLUDED.price,
                    url = EXCLUDED.url,
                    image_url = EXCLUDED.image_url,
                    in_stock = EXCLUDED.in_stock,
                    data = EXCLUDED.data,
                    last_check = CURRENT_TIMESTAMP
                """
                cursor.execute(sql, (
                    product["pid"],
                    product["title"],
                    product.get("price"),
                    product.get("url"),
                    product.get("image_url"),
                    product.get("in_stock", False),
                    data_json,
                    product["module"]
                ))
            else:
                # SQLite version
                sql = """
                INSERT INTO products 
                    (pid, title, price, url, image_url, in_stock, data, module)
                VALUES 
                    (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (pid) DO UPDATE
                SET 
                    title = excluded.title,
                    price = excluded.price,
                    url = excluded.url,
                    image_url = excluded.image_url,
                    in_stock = excluded.in_stock,
                    data = excluded.data,
                    last_check = CURRENT_TIMESTAMP
                """
                cursor.execute(sql, (
                    product["pid"],
                    product["title"],
                    product.get("price"),
                    product.get("url"),
                    product.get("image_url"),
                    1 if product.get("in_stock", False) else 0,
                    data_json,
                    product["module"]
                ))

            self.connection.commit()
            cursor.close()
            logger.info(f"Added/updated product: {product['pid']} - {product['title']}")
            return True

        except Exception as e:
            logger.error(f"Error adding product: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def get_product(self, pid: str) -> Optional[Dict[str, Any]]:
        """
        Get a product by PID

        Args:
            pid: Product ID

        Returns:
            Dict with product data or None if not found
        """
        try:
            cursor = self.get_cursor()

            sql = "SELECT * FROM products WHERE pid = ?"
            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")

            cursor.execute(sql, (pid,))
            result = cursor.fetchone()
            cursor.close()

            if not result:
                return None

            # Convert row to dictionary
            if self.db_type == "postgres":
                product = dict(result)
            else:
                product = {key: result[key] for key in result.keys()}

            # Parse JSON data
            if product.get("data"):
                try:
                    product["data"] = json.loads(product["data"])
                except:
                    product["data"] = {}

            # Convert SQLite boolean to Python boolean
            if self.db_type == "sqlite":
                product["in_stock"] = bool(product["in_stock"])

            return product

        except Exception as e:
            logger.error(f"Error getting product {pid}: {str(e)}")
            return None

    def get_products_by_module(self, module: str, limit: int = 100,
                               in_stock: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get products for a specific module

        Args:
            module: Module name
            limit: Maximum number of products to return
            in_stock: If provided, filter by in_stock status

        Returns:
            List of product dictionaries
        """
        try:
            cursor = self.get_cursor()

            # Build query based on parameters
            sql = "SELECT * FROM products WHERE module = ?"
            params = [module]

            if in_stock is not None:
                sql += " AND in_stock = ?"
                in_stock_val = in_stock
                if self.db_type == "sqlite":
                    in_stock_val = 1 if in_stock else 0
                params.append(in_stock_val)

            sql += " ORDER BY last_check ASC LIMIT ?"
            params.append(limit)

            # Convert placeholders for Postgres
            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")

            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()

            products = []
            for row in results:
                # Convert row to dictionary
                if self.db_type == "postgres":
                    product = dict(row)
                else:
                    product = {key: row[key] for key in row.keys()}

                # Parse JSON data
                if product.get("data"):
                    try:
                        product["data"] = json.loads(product["data"])
                    except:
                        product["data"] = {}

                # Convert SQLite boolean to Python boolean
                if self.db_type == "sqlite":
                    product["in_stock"] = bool(product["in_stock"])

                products.append(product)

            return products

        except Exception as e:
            logger.error(f"Error getting products for module {module}: {str(e)}")
            return []

    def update_stock_status(self, pid: str, in_stock: bool,
                            stores: List[Dict[str, Any]] = None) -> bool:
        """
        Update a product's stock status

        Args:
            pid: Product ID
            in_stock: Whether the product is in stock
            stores: List of store information where the product is available

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Get current stock status to check for changes
            current_status_sql = "SELECT in_stock FROM products WHERE pid = ?"
            if self.db_type == "postgres":
                current_status_sql = current_status_sql.replace("?", "%s")

            cursor.execute(current_status_sql, (pid,))
            result = cursor.fetchone()

            if not result:
                logger.warning(f"Trying to update stock status for unknown product: {pid}")
                cursor.close()
                return False

            # Get current status
            current_in_stock = result[0]
            if self.db_type == "sqlite":
                current_in_stock = bool(current_in_stock)

            # Update product status
            if in_stock:
                update_sql = """
                UPDATE products
                SET in_stock = ?, last_in_stock = CURRENT_TIMESTAMP, last_check = CURRENT_TIMESTAMP
                WHERE pid = ?
                """
            else:
                update_sql = """
                UPDATE products
                SET in_stock = ?, last_out_of_stock = CURRENT_TIMESTAMP, last_check = CURRENT_TIMESTAMP
                WHERE pid = ?
                """

            if self.db_type == "postgres":
                update_sql = update_sql.replace("?", "%s")
                in_stock_val = in_stock
            else:
                in_stock_val = 1 if in_stock else 0

            cursor.execute(update_sql, (in_stock_val, pid))

            # If stock status has changed, log the event
            if current_in_stock != in_stock:
                alert_type = "in_stock" if in_stock else "out_of_stock"
                message = f"Product is now {'IN STOCK' if in_stock else 'OUT OF STOCK'}"

                alert_sql = """
                INSERT INTO alert_history (pid, alert_type, message)
                VALUES (?, ?, ?)
                """

                if self.db_type == "postgres":
                    alert_sql = alert_sql.replace("?", "%s")

                cursor.execute(alert_sql, (pid, alert_type, message))

            # Update store availability if provided
            if stores and in_stock:
                for store_data in stores:
                    # Add or update store
                    store_id = self._ensure_store_exists(cursor, store_data)

                    if store_id:
                        # Update product availability for this store
                        avail_sql = """
                        INSERT INTO product_availability (pid, store_id, available, check_time)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT (pid, store_id) DO UPDATE
                        SET available = ?, check_time = CURRENT_TIMESTAMP
                        """

                        if self.db_type == "postgres":
                            avail_sql = avail_sql.replace("?", "%s")
                            avail_val = True
                        else:
                            avail_val = 1

                        cursor.execute(avail_sql, (pid, store_id, avail_val, avail_val))

            self.connection.commit()
            cursor.close()

            # Log the stock update event
            if current_in_stock != in_stock:
                logger.info(f"Stock status changed for {pid}: {'IN STOCK' if in_stock else 'OUT OF STOCK'}")
                return True
            else:
                logger.debug(f"Stock status unchanged for {pid}: {'IN STOCK' if in_stock else 'OUT OF STOCK'}")
                return False

        except Exception as e:
            logger.error(f"Error updating stock status for {pid}: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def _ensure_store_exists(self, cursor, store_data: Dict[str, Any]) -> Optional[int]:
        """
        Ensure a store exists in the database, adding it if needed

        Args:
            cursor: Database cursor
            store_data: Store information

        Returns:
            int: Store ID if successful, None otherwise
        """
        try:
            store_id = store_data.get("store_id")
            module = store_data.get("module")

            if not store_id or not module:
                logger.error("Store data missing required fields: store_id and module")
                return None

            # Check if store already exists
            check_sql = "SELECT id FROM stores WHERE store_id = ? AND module = ?"
            if self.db_type == "postgres":
                check_sql = check_sql.replace("?", "%s")

            cursor.execute(check_sql, (store_id, module))
            result = cursor.fetchone()

            if result:
                # Store exists, return its ID
                return result[0]

            # Store doesn't exist, add it
            insert_sql = """
            INSERT INTO stores (
                store_id, name, address, city, state, zip,
                phone, latitude, longitude, module
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            if self.db_type == "postgres":
                insert_sql = insert_sql.replace("?", "%s")
                # Get store ID using RETURNING clause
                insert_sql += " RETURNING id"

            params = (
                store_id,
                store_data.get("name", ""),
                store_data.get("address", ""),
                store_data.get("city", ""),
                store_data.get("state", ""),
                store_data.get("zip", ""),
                store_data.get("phone", ""),
                store_data.get("latitude"),
                store_data.get("longitude"),
                module
            )

            if self.db_type == "postgres":
                cursor.execute(insert_sql, params)
                result = cursor.fetchone()
                return result[0]
            else:
                cursor.execute(insert_sql, params)
                return cursor.lastrowid

        except Exception as e:
            logger.error(f"Error ensuring store exists: {str(e)}")
            return None

    def save_cookies(self, module: str, domain: str, cookies: Dict[str, str],
                     expires_hours: int = 24) -> bool:
        """
        Save cookies for a module and domain

        Args:
            module: Module name
            domain: Domain name
            cookies: Cookie dictionary
            expires_hours: Hours until cookies expire

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Calculate expiration timestamp
            expires_at = datetime.now().timestamp() + (expires_hours * 3600)

            # Convert cookies to JSON
            cookies_json = json.dumps(cookies)

            # Upsert cookies
            sql = """
            INSERT INTO cookies (module, domain, cookies, timestamp, expires_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, datetime(?, 'unixepoch'))
            ON CONFLICT (module, domain) DO UPDATE
            SET cookies = ?, timestamp = CURRENT_TIMESTAMP, expires_at = datetime(?, 'unixepoch')
            """

            if self.db_type == "postgres":
                sql = """
                INSERT INTO cookies (module, domain, cookies, timestamp, expires_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, to_timestamp(%s))
                ON CONFLICT (module, domain) DO UPDATE
                SET cookies = %s, timestamp = CURRENT_TIMESTAMP, expires_at = to_timestamp(%s)
                """
                cursor.execute(sql, (
                    module, domain, cookies_json, expires_at,
                    cookies_json, expires_at
                ))
            else:
                cursor.execute(sql, (
                    module, domain, cookies_json, expires_at,
                    cookies_json, expires_at
                ))

            self.connection.commit()
            cursor.close()

            logger.info(f"Saved cookies for {module} on domain {domain}")
            return True

        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def load_cookies(self, module: str, domain: str) -> Optional[Dict[str, str]]:
        """
        Load cookies for a module and domain

        Args:
            module: Module name
            domain: Domain name

        Returns:
            Dict: Cookie dictionary if valid, None otherwise
        """
        try:
            cursor = self.get_cursor()

            # Get cookies, checking expiration
            if self.db_type == "postgres":
                sql = """
                SELECT cookies 
                FROM cookies 
                WHERE module = %s 
                  AND domain = %s 
                  AND expires_at > CURRENT_TIMESTAMP
                """
            else:
                sql = """
                SELECT cookies 
                FROM cookies 
                WHERE module = ? 
                  AND domain = ? 
                  AND expires_at > datetime('now')
                """

            cursor.execute(sql, (module, domain))
            result = cursor.fetchone()
            cursor.close()

            if not result:
                logger.info(f"No valid cookies found for {module} on domain {domain}")
                return None

            # Parse cookies JSON
            try:
                cookies = json.loads(result[0])
                logger.info(f"Loaded cookies for {module} on domain {domain}")
                return cookies
            except json.JSONDecodeError:
                logger.error(f"Error parsing cookies JSON for {module} on domain {domain}")
                return None

        except Exception as e:
            logger.error(f"Error loading cookies: {str(e)}")
            return None

    def add_task(self, task_type: str, module: str, data: Dict[str, Any] = None,
                 priority: int = 5, schedule_delay_seconds: int = 0) -> Optional[int]:
        """
        Add a task to the task queue

        Args:
            task_type: Type of task ('check_stock', 'scan_new', etc.)
            module: Module name
            data: Task data (will be stored as JSON)
            priority: Task priority (higher number = higher priority)
            schedule_delay_seconds: Delay before task should be executed

        Returns:
            int: Task ID if successful, None otherwise
        """
        try:
            cursor = self.get_cursor()

            # Convert data to JSON
            data_json = json.dumps(data or {})

            # Calculate scheduled_at timestamp
            if self.db_type == "postgres":
                scheduled_at_sql = f"CURRENT_TIMESTAMP + interval '{schedule_delay_seconds} seconds'"
                sql = f"""
                INSERT INTO tasks (
                    task_type, module, data, priority, scheduled_at
                ) VALUES (
                    %s, %s, %s, %s, {scheduled_at_sql}
                ) RETURNING id
                """
                cursor.execute(sql, (task_type, module, data_json, priority))
                result = cursor.fetchone()
                task_id = result[0]
            else:
                scheduled_at_sql = f"datetime('now', '+{schedule_delay_seconds} seconds')"
                sql = f"""
                INSERT INTO tasks (
                    task_type, module, data, priority, scheduled_at
                ) VALUES (
                    ?, ?, ?, ?, {scheduled_at_sql}
                )
                """
                cursor.execute(sql, (task_type, module, data_json, priority))
                task_id = cursor.lastrowid

            self.connection.commit()
            cursor.close()

            logger.info(f"Added task {task_id}: {task_type} for {module}")
            return task_id

        except Exception as e:
            logger.error(f"Error adding task: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return None

    def get_next_task(self, module: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the next task to execute from the queue

        Args:
            module: Optional module filter

        Returns:
            Dict: Task data if available, None otherwise
        """
        try:
            cursor = self.get_cursor()

            # Build query based on parameters
            base_sql = """
            SELECT id, task_type, module, data, priority, created_at, scheduled_at, attempts, max_attempts
            FROM tasks
            WHERE status = 'pending'
              AND scheduled_at <= CURRENT_TIMESTAMP
            """

            params = []
            if module:
                base_sql += " AND module = ?"
                params.append(module)

                if self.db_type == "postgres":
                    base_sql = base_sql.replace("?", "%s")

            # Order by priority (desc) and scheduled_at (asc)
            base_sql += " ORDER BY priority DESC, scheduled_at ASC LIMIT 1"

            cursor.execute(base_sql, params)
            result = cursor.fetchone()

            if not result:
                cursor.close()
                return None

            # Convert row to dictionary
            if self.db_type == "postgres":
                task = dict(result)
            else:
                task = {key: result[key] for key in result.keys()}

            # Parse JSON data
            if task.get("data"):
                try:
                    task["data"] = json.loads(task["data"])
                except:
                    task["data"] = {}

            # Mark task as running
            update_sql = """
            UPDATE tasks
            SET status = 'running', started_at = CURRENT_TIMESTAMP, attempts = attempts + 1
            WHERE id = ?
            """

            if self.db_type == "postgres":
                update_sql = update_sql.replace("?", "%s")

            cursor.execute(update_sql, (task["id"],))
            self.connection.commit()
            cursor.close()

            logger.info(f"Started task {task['id']}: {task['task_type']} for {task['module']}")
            return task

        except Exception as e:
            logger.error(f"Error getting next task: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return None

    def complete_task(self, task_id: int, result: Dict[str, Any] = None) -> bool:
        """
        Mark a task as completed

        Args:
            task_id: Task ID
            result: Optional result data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Convert result to JSON
            result_json = json.dumps(result or {})

            # Update task status
            sql = """
            UPDATE tasks
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, result = ?
            WHERE id = ?
            """

            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")

            cursor.execute(sql, (result_json, task_id))
            self.connection.commit()
            cursor.close()

            logger.info(f"Completed task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error completing task {task_id}: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def fail_task(self, task_id: int, error: str, retry: bool = True) -> bool:
        """
        Mark a task as failed

        Args:
            task_id: Task ID
            error: Error message
            retry: Whether to retry the task if attempts < max_attempts

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Get current task info
            info_sql = "SELECT attempts, max_attempts FROM tasks WHERE id = ?"
            if self.db_type == "postgres":
                info_sql = info_sql.replace("?", "%s")

            cursor.execute(info_sql, (task_id,))
            result = cursor.fetchone()

            if not result:
                logger.warning(f"Task {task_id} not found for fail_task")
                cursor.close()
                return False

            attempts = result[0]
            max_attempts = result[1]

            # Determine status based on retry flag and attempt counts
            if retry and attempts < max_attempts:
                # Schedule for retry with exponential backoff
                backoff_seconds = 60 * (2 ** (attempts - 1))  # 1min, 2min, 4min, 8min, etc.

                if self.db_type == "postgres":
                    scheduled_at_sql = f"CURRENT_TIMESTAMP + interval '{backoff_seconds} seconds'"
                    status_sql = """
                    UPDATE tasks
                    SET status = 'pending', 
                        error = %s,
                        scheduled_at = {scheduled_at_sql}
                    WHERE id = %s
                    """.format(scheduled_at_sql=scheduled_at_sql)
                else:
                    scheduled_at_sql = f"datetime('now', '+{backoff_seconds} seconds')"
                    status_sql = """
                    UPDATE tasks
                    SET status = 'pending', 
                        error = ?,
                        scheduled_at = {scheduled_at_sql}
                    WHERE id = ?
                    """.format(scheduled_at_sql=scheduled_at_sql)

                cursor.execute(status_sql, (error, task_id))
                logger.info(f"Task {task_id} failed, scheduled for retry in {backoff_seconds} seconds")
            else:
                # Mark as failed permanently
                status_sql = """
                UPDATE tasks
                SET status = 'failed', 
                    completed_at = CURRENT_TIMESTAMP, 
                    error = ?
                WHERE id = ?
                """

                if self.db_type == "postgres":
                    status_sql = status_sql.replace("?", "%s")

                cursor.execute(status_sql, (error, task_id))
                logger.info(f"Task {task_id} failed permanently: {error}")

            self.connection.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Error failing task {task_id}: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def log_event(self, level: str, module: str, message: str, data: Dict[str, Any] = None) -> bool:
        """
        Log an event to the database

        Args:
            level: Log level ('INFO', 'WARNING', 'ERROR', etc.)
            module: Module name
            message: Log message
            data: Additional data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Convert data to JSON
            data_json = json.dumps(data or {})

            # Insert log entry
            sql = """
            INSERT INTO logs (level, module, message, data)
            VALUES (?, ?, ?, ?)
            """

            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")

            cursor.execute(sql, (level, module, message, data_json))
            self.connection.commit()
            cursor.close()

            return True

        except Exception as e:
            logger.error(f"Error logging event: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def get_module_config(self, module: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a module

        Args:
            module: Module name

        Returns:
            Dict: Module configuration if found, None otherwise
        """
        try:
            cursor = self.get_cursor()

            sql = "SELECT * FROM module_config WHERE module = ?"
            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")

            cursor.execute(sql, (module,))
            result = cursor.fetchone()
            cursor.close()

            if not result:
                return None

            # Convert row to dictionary
            if self.db_type == "postgres":
                config = dict(result)
            else:
                config = {key: result[key] for key in result.keys()}

            # Parse JSON config
            if config.get("config"):
                try:
                    config["config"] = json.loads(config["config"])
                except:
                    config["config"] = {}

            # Convert SQLite boolean to Python boolean
            if self.db_type == "sqlite":
                config["enabled"] = bool(config["enabled"])

            return config

        except Exception as e:
            logger.error(f"Error getting config for module {module}: {str(e)}")
            return None

    def update_module_config(self, module: str, config: Dict[str, Any],
                             enabled: bool = True, interval_seconds: int = None) -> bool:
        """
        Update configuration for a module

        Args:
            module: Module name
            config: Module configuration
            enabled: Whether the module is enabled
            interval_seconds: Check interval in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Convert config to JSON
            config_json = json.dumps(config or {})

            # Build the query and parameters
            params = [config_json, module]

            if self.db_type == "postgres":
                sql = """
                INSERT INTO module_config (module, config, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (module) DO UPDATE
                SET config = %s
                """
                # Add enabled parameter
                enabled_val = enabled
                params = [module, config_json, enabled_val, config_json]

                # Add interval if provided
                if interval_seconds is not None:
                    sql = sql[:-1] + ", interval_seconds = %s"
                    params.append(interval_seconds)
            else:
                sql = """
                INSERT INTO module_config (module, config, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT (module) DO UPDATE
                SET config = ?
                """
                # Add enabled parameter
                enabled_val = 1 if enabled else 0
                params = [module, config_json, enabled_val, config_json]

                # Add interval if provided
                if interval_seconds is not None:
                    sql = sql[:-1] + ", interval_seconds = ?"
                    params.append(interval_seconds)

            cursor.execute(sql, params)
            self.connection.commit()
            cursor.close()

            logger.info(f"Updated config for module {module}")
            return True

        except Exception as e:
            logger.error(f"Error updating config for module {module}: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def update_module_run_info(self, module: str, next_run_seconds: int = None) -> bool:
        """
        Update a module's last run time and calculate next run time

        Args:
            module: Module name
            next_run_seconds: Seconds until next run (if None, uses the module's interval)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.get_cursor()

            # Get module interval if next_run_seconds not provided
            if next_run_seconds is None:
                interval_sql = "SELECT interval_seconds FROM module_config WHERE module = ?"
                if self.db_type == "postgres":
                    interval_sql = interval_sql.replace("?", "%s")

                cursor.execute(interval_sql, (module,))
                result = cursor.fetchone()

                if not result:
                    logger.warning(f"Module {module} not found in config")
                    cursor.close()
                    return False

                next_run_seconds = result[0]

            # Update last run and next run times
            if self.db_type == "postgres":
                next_run_sql = f"CURRENT_TIMESTAMP + interval '{next_run_seconds} seconds'"
                sql = f"""
                UPDATE module_config
                SET last_run = CURRENT_TIMESTAMP,
                    next_run = {next_run_sql}
                WHERE module = %s
                """
            else:
                next_run_sql = f"datetime('now', '+{next_run_seconds} seconds')"
                sql = f"""
                UPDATE module_config
                SET last_run = CURRENT_TIMESTAMP,
                    next_run = {next_run_sql}
                WHERE module = ?
                """

            cursor.execute(sql, (module,))
            self.connection.commit()
            cursor.close()

            logger.info(f"Updated run info for module {module}, next run in {next_run_seconds} seconds")
            return True

        except Exception as e:
            logger.error(f"Error updating run info for module {module}: {str(e)}")
            if self.connection:
                self.connection.rollback()
            return False

    def get_due_modules(self) -> List[str]:
        """
        Get the names of modules that are due to run

        Returns:
            List: Module names
        """
        try:
            cursor = self.get_cursor()

            sql = """
            SELECT module
            FROM module_config
            WHERE enabled = ?
              AND (next_run IS NULL OR next_run <= CURRENT_TIMESTAMP)
            """

            if self.db_type == "postgres":
                sql = sql.replace("?", "%s")
                enabled_val = True
            else:
                enabled_val = 1

            cursor.execute(sql, (enabled_val,))
            results = cursor.fetchall()
            cursor.close()

            # Extract module names
            modules = [row[0] for row in results]

            return modules

        except Exception as e:
            logger.error(f"Error getting due modules: {str(e)}")
            return []


if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test the database with SQLite
    db = Database({
        "database": "stockchecker_test.db"
    })

    # Test adding a product
    test_product = {
        "pid": "9798400902550",
        "title": "Solo Leveling, Vol. 11 (Comic)",
        "price": "20.00",
        "url": "https://www.booksamillion.com/p/Solo-Leveling-Comic/Chugong/9798400902550",
        "image_url": "https://covers3.booksamillion.com/covers/bam/9/79/840/090/9798400902550_m.jpg",
        "in_stock": True,
        "module": "booksamillion"
    }

    db.add_product(test_product)

    # Test getting the product
    retrieved = db.get_product("9798400902550")
    if retrieved:
        print("Retrieved product:")
        print(f"  Title: {retrieved['title']}")
        print(f"  Price: ${retrieved['price']}")
        print(f"  In Stock: {retrieved['in_stock']}")

    # Test updating stock status
    store_data = {
        "store_id": "331",
        "name": "#331 Douglasville, GA",
        "address": "6700 Douglas Blvd",
        "city": "Douglasville",
        "state": "GA",
        "zip": "30135",
        "phone": "(770) 949-4014",
        "module": "booksamillion"
    }

    db.update_stock_status("9798400902550", True, [store_data])

    # Test adding a task
    task_id = db.add_task(
        task_type="check_stock",
        module="booksamillion",
        data={"pid": "9798400902550"},
        priority=8
    )

    if task_id:
        print(f"Added task with ID: {task_id}")

        # Test getting the task
        task = db.get_next_task()
        if task:
            print(f"Got task: {task['task_type']} for {task['module']}")

            # Test completing the task
            db.complete_task(task["id"], {"result": "success"})

    # Test updating module configuration
    module_config = {
        "search_urls": [
            "https://www.booksamillion.com/search?query=pokemon"
        ],
        "keywords": ["exclusive", "limited edition"],
        "search_radius": 250
    }

    db.update_module_config("booksamillion", module_config)

    # Test getting module configuration
    config = db.get_module_config("booksamillion")
    if config:
        print("Module config:")
        print(f"  Enabled: {config['enabled']}")
        print(f"  Search URLs: {config['config'].get('search_urls')}")

    # Clean up
    db.disconnect()

    print("Database tests completed")