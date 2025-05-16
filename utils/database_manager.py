#!/usr/bin/env python3
"""
Enhanced Database Manager
Provides robust database connectivity and operations for the Stock Checker system.
"""

import os
import json
import time
import logging
import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from pathlib import Path
from contextlib import contextmanager

# Try to import PostgreSQL adapter
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

# Import SQLite
import sqlite3

# Define logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DatabaseManager")


class DatabaseManager:
    """Enhanced database manager with connection pooling and optimized queries"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize database connection pool

        Args:
            config: Database configuration dictionary
        """
        self.config = config
        self.db_type = self._determine_db_type()
        self.pool = None

        # Initialize connection pool
        self._setup_connection_pool()

        # Create tables if needed
        self._ensure_tables_exist()

        logger.info(f"Database manager initialized with {self.db_type} backend")

    def _determine_db_type(self) -> str:
        """Determine database type from configuration"""
        if not self.config.get("enabled", True):
            return "disabled"

        db_type = self.config.get("type", "").lower()

        if db_type == "postgres" or db_type == "postgresql":
            if POSTGRES_AVAILABLE:
                return "postgres"
            else:
                logger.warning("PostgreSQL selected but psycopg2 not available, falling back to SQLite")
                return "sqlite"
        else:
            return "sqlite"

    def _setup_connection_pool(self):
        """Set up connection pool based on database type"""
        if self.db_type == "disabled":
            return

        if self.db_type == "postgres":
            # PostgreSQL connection pool
            try:
                min_conn = self.config.get("min_connections", 1)
                max_conn = self.config.get("max_connections", 10)

                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=min_conn,
                    maxconn=max_conn,
                    host=self.config.get("host", "localhost"),
                    port=self.config.get("port", 5432),
                    database=self.config.get("name", "stockchecker"),
                    user=self.config.get("user", "postgres"),
                    password=self.config.get("password", "")
                )
                logger.info(f"PostgreSQL connection pool created (min={min_conn}, max={max_conn})")
            except Exception as e:
                logger.error(f"Error creating PostgreSQL connection pool: {str(e)}")
                self.db_type = "disabled"
        else:
            # SQLite doesn't need a real connection pool, but we'll create a simple wrapper
            try:
                db_path = Path(self.config.get("file", "data/stockchecker.db"))
                db_path.parent.mkdir(parents=True, exist_ok=True)

                # Create initial connection to verify it works
                conn = sqlite3.connect(db_path)
                conn.close()

                # Store path for future connections
                self.pool = {"db_path": str(db_path)}
                logger.info(f"SQLite connection configured at {db_path}")
            except Exception as e:
                logger.error(f"Error setting up SQLite database: {str(e)}")
                self.db_type = "disabled"

    @contextmanager
    def get_connection(self):
        """
        Get a database connection from the pool

        Yields:
            Database connection
        """
        connection = None
        cursor = None

        try:
            if self.db_type == "postgres":
                connection = self.pool.getconn()
                # Configure handling of JSON data
                psycopg2.extras.register_default_jsonb(connection)
                cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
            elif self.db_type == "sqlite":
                db_path = self.pool["db_path"]
                connection = sqlite3.connect(db_path)
                connection.row_factory = sqlite3.Row
                # Enable foreign keys
                connection.execute("PRAGMA foreign_keys = ON")
                cursor = connection.cursor()
            else:
                raise ValueError("Database is not configured or disabled")

            yield cursor, connection

            # If we get here without an exception, commit any changes
            if connection:
                connection.commit()

        except Exception as e:
            logger.error(f"Database operation error: {str(e)}")
            # Roll back any changes
            if connection:
                connection.rollback()
            raise
        finally:
            # Close cursor and return connection to pool
            if cursor:
                cursor.close()
            if connection:
                if self.db_type == "postgres":
                    self.pool.putconn(connection)
                else:
                    connection.close()

    def _ensure_tables_exist(self):
        """Create database tables if they don't exist"""
        if self.db_type == "disabled":
            return

        # Load schema from file or use inline definition
        schema_path = Path("database/schema.sql")

        try:
            with self.get_connection() as (cursor, conn):
                if schema_path.exists():
                    # Load schema from file
                    with open(schema_path, "r") as f:
                        schema_sql = f.read()

                    if self.db_type == "sqlite":
                        # SQLite requires each statement to be executed separately
                        for statement in schema_sql.split(";"):
                            if statement.strip():
                                cursor.execute(statement)
                    else:
                        # PostgreSQL can execute the whole script
                        cursor.execute(schema_sql)
                else:
                    # Use inline minimal schema if file not found
                    self._create_minimal_schema(cursor)

                logger.info("Database tables created or verified")
        except Exception as e:
            logger.error(f"Error creating database tables: {str(e)}")

    def _create_minimal_schema(self, cursor):
        """Create a minimal schema if schema file not found"""
        # Define tables based on database type
        if self.db_type == "sqlite":
            cursor.executescript("""
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
            """)
        else:
            # PostgreSQL schema
            cursor.execute("""
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
                alert_type VARCHAR(50) NOT NULL,
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
            """)

    # Product operations

    def add_product(self, product: Dict[str, Any]) -> bool:
        """
        Add or update a product in the database

        Args:
            product: Product data dictionary

        Returns:
            bool: True if successful, False otherwise
        """
        if self.db_type == "disabled":
            return False

        try:
            with self.get_connection() as (cursor, conn):
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

                logger.info(f"Added/updated product: {product['pid']} - {product['title']}")
                return True

        except Exception as e:
            logger.error(f"Error adding product: {str(e)}")
            return False

    def get_product(self, pid: str) -> Optional[Dict[str, Any]]:
        """
        Get a product by PID

        Args:
            pid: Product ID

        Returns:
            Dict with product data or None if not found
        """
        if self.db_type == "disabled":
            return None

        try:
            with self.get_connection() as (cursor, conn):
                sql = "SELECT * FROM products WHERE pid = ?"
                if self.db_type == "postgres":
                    sql = sql.replace("?", "%s")

                cursor.execute(sql, (pid,))
                result = cursor.fetchone()

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
                               in_stock: Optional[bool] = None,
                               order_by: str = "last_check",
                               order_direction: str = "ASC") -> List[Dict[str, Any]]:
        """
        Get products for a specific module with advanced filtering

        Args:
            module: Module name
            limit: Maximum number of products to return
            in_stock: If provided, filter by in_stock status
            order_by: Field to order by (last_check, pid, etc.)
            order_direction: ASC or DESC

        Returns:
            List of product dictionaries
        """
        if self.db_type == "disabled":
            return []

        # Validate order params
        valid_order_fields = ["last_check", "pid", "title", "price", "first_seen"]
        if order_by not in valid_order_fields:
            order_by = "last_check"

        if order_direction not in ["ASC", "DESC"]:
            order_direction = "ASC"

        try:
            with self.get_connection() as (cursor, conn):
                # Build query based on parameters
                sql = "SELECT * FROM products WHERE module = ?"
                params = [module]

                if in_stock is not None:
                    sql += " AND in_stock = ?"
                    in_stock_val = in_stock
                    if self.db_type == "sqlite":
                        in_stock_val = 1 if in_stock else 0
                    params.append(in_stock_val)

                sql += f" ORDER BY {order_by} {order_direction} LIMIT ?"
                params.append(limit)

                # Convert placeholders for Postgres
                if self.db_type == "postgres":
                    sql = sql.replace("?", "%s")

                cursor.execute(sql, params)
                results = cursor.fetchall()

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
                            stores: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Update a product's stock status with optional store information

        Args:
            pid: Product ID
            in_stock: Whether the product is in stock
            stores: List of store information where the product is available

        Returns:
            bool: True if successful, False otherwise
        """
        if self.db_type == "disabled":
            return False

        try:
            with self.get_connection() as (cursor, conn):
                # Get current stock status to check for changes
                current_status_sql = "SELECT in_stock FROM products WHERE pid = ?"
                if self.db_type == "postgres":
                    current_status_sql = current_status_sql.replace("?", "%s")

                cursor.execute(current_status_sql, (pid,))
                result = cursor.fetchone()

                if not result:
                    logger.warning(f"Product not found for stock update: {pid}")
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
                    store_updates = []
                    for store_data in stores:
                        # First ensure store exists
                        store_id = self._ensure_store_exists(cursor, store_data)

                        if store_id:
                            store_updates.append((store_id, pid))

                    # Batch update store availability for performance
                    if store_updates:
                        if self.db_type == "postgres":
                            # PostgreSQL can use more efficient batch insert
                            avail_sql = """
                            INSERT INTO product_availability (store_id, pid, available, check_time)
                            VALUES %s
                            ON CONFLICT (pid, store_id) DO UPDATE
                            SET available = TRUE, check_time = CURRENT_TIMESTAMP
                            """
                            # Use execute_values for batch insert
                            psycopg2.extras.execute_values(
                                cursor,
                                avail_sql,
                                [(store_id, pid, True, datetime.datetime.now()) for store_id, pid in store_updates]
                            )
                        else:
                            # SQLite needs individual inserts
                            avail_sql = """
                            INSERT INTO product_availability (store_id, pid, available, check_time)
                            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                            ON CONFLICT (pid, store_id) DO UPDATE
                            SET available = 1, check_time = CURRENT_TIMESTAMP
                            """

                            for store_id, pid in store_updates:
                                cursor.execute(avail_sql, (store_id, pid))

                logger.info(f"Updated stock status for {pid}: {'IN STOCK' if in_stock else 'OUT OF STOCK'}")
                return True

        except Exception as e:
            logger.error(f"Error updating stock status for {pid}: {str(e)}")
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

    # Cookie management with database

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
        if self.db_type == "disabled":
            return False

        try:
            with self.get_connection() as (cursor, conn):
                # Calculate expiration timestamp
                expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)

                # Convert cookies to JSON
                cookies_json = json.dumps(cookies)

                # Upsert cookies
                if self.db_type == "postgres":
                    sql = """
                    INSERT INTO cookies (module, domain, cookies, timestamp, expires_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (module, domain) DO UPDATE
                    SET cookies = %s, timestamp = CURRENT_TIMESTAMP, expires_at = %s
                    """
                    cursor.execute(sql, (
                        module, domain, cookies_json, expires_at,
                        cookies_json, expires_at
                    ))
                else:
                    sql = """
                    INSERT INTO cookies (module, domain, cookies, timestamp, expires_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT (module, domain) DO UPDATE
                    SET cookies = ?, timestamp = CURRENT_TIMESTAMP, expires_at = ?
                    """
                    cursor.execute(sql, (
                        module, domain, cookies_json, expires_at,
                        cookies_json, expires_at
                    ))

                logger.info(f"Saved cookies for {module} on domain {domain}")
                return True

        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")
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
        if self.db_type == "disabled":
            return None

        try:
            with self.get_connection() as (cursor, conn):
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

    # Advanced queries and batch operations

    def batch_add_products(self, products: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Add multiple products in a single batch operation

        Args:
            products: List of product dictionaries

        Returns:
            Tuple[int, int]: (number of successful inserts, number of failures)
        """
        if self.db_type == "disabled" or not products:
            return (0, 0)

        success_count = 0
        failure_count = 0

        try:
            with self.get_connection() as (cursor, conn):
                if self.db_type == "postgres":
                    # PostgreSQL supports efficient batch insert
                    values = []
                    for product in products:
                        # Convert JSON fields for database storage
                        data_json = json.dumps(product.get("data", {}))

                        values.append((
                            product["pid"],
                            product["title"],
                            product.get("price"),
                            product.get("url"),
                            product.get("image_url"),
                            product.get("in_stock", False),
                            data_json,
                            product["module"]
                        ))

                    sql = """
                    INSERT INTO products 
                        (pid, title, price, url, image_url, in_stock, data, module)
                    VALUES %s
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

                    # Use execute_values for batch insert
                    psycopg2.extras.execute_values(cursor, sql, values)
                    success_count = len(products)
                else:
                    # SQLite needs individual inserts
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

                    for product in products:
                        try:
                            # Convert JSON fields for database storage
                            data_json = json.dumps(product.get("data", {}))

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
                            success_count += 1
                        except Exception as e:
                            logger.error(f"Error in batch insert for {product.get('pid', 'unknown')}: {str(e)}")
                            failure_count += 1

                logger.info(f"Batch added {success_count} products, {failure_count} failures")
                return (success_count, failure_count)

        except Exception as e:
            logger.error(f"Error in batch product insert: {str(e)}")
            return (success_count, len(products) - success_count)

    def search_products(self, query: str, module: Optional[str] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search for products matching query

        Args:
            query: Search query
            module: Optional module filter
            limit: Maximum results to return

        Returns:
            List of matching product dictionaries
        """
        if self.db_type == "disabled":
            return []

        try:
            with self.get_connection() as (cursor, conn):
                params = []

                if self.db_type == "postgres":
                    # PostgreSQL has more powerful text search
                    sql = """
                    SELECT * FROM products
                    WHERE to_tsvector('english', title || ' ' || coalesce(data->>'description', '')) @@ 
                          plainto_tsquery('english', %s)
                    """
                    params.append(query)

                    if module:
                        sql += " AND module = %s"
                        params.append(module)

                    sql += " ORDER BY in_stock DESC, ts_rank_cd(to_tsvector('english', title), plainto_tsquery('english', %s)) DESC LIMIT %s"
                    params.append(query)
                    params.append(limit)
                else:
                    # SQLite basic search
                    sql = """
                    SELECT * FROM products
                    WHERE title LIKE ? OR data LIKE ?
                    """
                    search_term = f"%{query}%"
                    params.append(search_term)
                    params.append(search_term)

                    if module:
                        sql += " AND module = ?"
                        params.append(module)

                    sql += " ORDER BY in_stock DESC LIMIT ?"
                    params.append(limit)

                cursor.execute(sql, params)
                results = cursor.fetchall()

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
            logger.error(f"Error searching products: {str(e)}")
            return []

    def get_stock_history(self, pid: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get stock change history for a product

        Args:
            pid: Product ID
            days: Number of days of history

        Returns:
            List of alert history records
        """
        if self.db_type == "disabled":
            return []

        try:
            with self.get_connection() as (cursor, conn):
                if self.db_type == "postgres":
                    sql = """
                    SELECT * FROM alert_history
                    WHERE pid = %s 
                      AND alert_type IN ('in_stock', 'out_of_stock')
                      AND alert_time > (CURRENT_TIMESTAMP - INTERVAL '%s days')
                    ORDER BY alert_time DESC
                    """
                    cursor.execute(sql, (pid, days))
                else:
                    sql = """
                    SELECT * FROM alert_history
                    WHERE pid = ?
                      AND alert_type IN ('in_stock', 'out_of_stock')
                      AND alert_time > datetime('now', '-? days')
                    ORDER BY alert_time DESC
                    """
                    cursor.execute(sql, (pid, days))

                results = cursor.fetchall()

                history = []
                for row in results:
                    # Convert row to dictionary
                    if self.db_type == "postgres":
                        entry = dict(row)
                    else:
                        entry = {key: row[key] for key in row.keys()}

                    # Parse JSON data if present
                    if entry.get("data"):
                        try:
                            entry["data"] = json.loads(entry["data"])
                        except:
                            entry["data"] = {}

                    # Convert SQLite boolean to Python boolean
                    if self.db_type == "sqlite" and "webhook_sent" in entry:
                        entry["webhook_sent"] = bool(entry["webhook_sent"])

                    history.append(entry)

                return history

        except Exception as e:
            logger.error(f"Error getting stock history for {pid}: {str(e)}")
            return []

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics

        Returns:
            Dict with database statistics
        """
        if self.db_type == "disabled":
            return {"status": "disabled"}

        stats = {
            "type": self.db_type,
            "tables": {}
        }

        try:
            with self.get_connection() as (cursor, conn):
                # Count products
                cursor.execute("SELECT COUNT(*) FROM products")
                stats["tables"]["products"] = cursor.fetchone()[0]

                # Count in-stock products
                if self.db_type == "postgres":
                    cursor.execute("SELECT COUNT(*) FROM products WHERE in_stock = TRUE")
                else:
                    cursor.execute("SELECT COUNT(*) FROM products WHERE in_stock = 1")
                stats["tables"]["in_stock_products"] = cursor.fetchone()[0]

                # Count stores
                cursor.execute("SELECT COUNT(*) FROM stores")
                stats["tables"]["stores"] = cursor.fetchone()[0]

                # Count product availability records
                cursor.execute("SELECT COUNT(*) FROM product_availability")
                stats["tables"]["product_availability"] = cursor.fetchone()[0]

                # Count alerts
                cursor.execute("SELECT COUNT(*) FROM alert_history")
                stats["tables"]["alert_history"] = cursor.fetchone()[0]

                # Count by module
                if self.db_type == "postgres":
                    cursor.execute("SELECT module, COUNT(*) FROM products GROUP BY module")
                else:
                    cursor.execute("SELECT module, COUNT(*) as count FROM products GROUP BY module")

                module_counts = {}
                for row in cursor.fetchall():
                    module_counts[row[0]] = row[1]

                stats["modules"] = module_counts

                # Database size (PostgreSQL only)
                if self.db_type == "postgres":
                    try:
                        cursor.execute("""
                        SELECT pg_size_pretty(pg_database_size(current_database())) as size
                        """)
                        result = cursor.fetchone()
                        stats["database_size"] = result[0]
                    except:
                        stats["database_size"] = "unknown"

                return stats

        except Exception as e:
            logger.error(f"Error getting database stats: {str(e)}")
            return {"status": "error", "message": str(e)}

    def archive_old_data(self, days: int = 90) -> int:
        """
        Archive old data to prevent database bloat

        Args:
            days: Keep data newer than this many days

        Returns:
            int: Number of records archived
        """
        if self.db_type == "disabled":
            return 0

        try:
            with self.get_connection() as (cursor, conn):
                archived = 0

                # Archive old alert history
                if self.db_type == "postgres":
                    sql = """
                    DELETE FROM alert_history
                    WHERE alert_time < (CURRENT_TIMESTAMP - INTERVAL '%s days')
                    """
                    cursor.execute(sql, (days,))
                else:
                    sql = """
                    DELETE FROM alert_history
                    WHERE alert_time < datetime('now', '-? days')
                    """
                    cursor.execute(sql, (days,))

                archived += cursor.rowcount

                # Archive old product availability records for products no longer in stock
                if self.db_type == "postgres":
                    sql = """
                    DELETE FROM product_availability
                    WHERE check_time < (CURRENT_TIMESTAMP - INTERVAL '%s days')
                      AND pid IN (SELECT pid FROM products WHERE in_stock = FALSE)
                    """
                    cursor.execute(sql, (days,))
                else:
                    sql = """
                    DELETE FROM product_availability
                    WHERE check_time < datetime('now', '-? days')
                      AND pid IN (SELECT pid FROM products WHERE in_stock = 0)
                    """
                    cursor.execute(sql, (days,))

                archived += cursor.rowcount

                logger.info(f"Archived {archived} old records")
                return archived

        except Exception as e:
            logger.error(f"Error archiving old data: {str(e)}")
            return 0

    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """
        Create a backup of the database

        Args:
            backup_path: Optional path for backup file

        Returns:
            bool: True if successful, False otherwise
        """
        if self.db_type == "disabled":
            return False

        try:
            # Generate backup path if not provided
            if not backup_path:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                if self.db_type == "postgres":
                    backup_path = f"data/backup_{timestamp}.sql"
                else:
                    backup_path = f"data/backup_{timestamp}.sqlite"

            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            if self.db_type == "postgres":
                # Use pg_dump for PostgreSQL backup
                conn_params = self.config
                cmd = [
                    "pg_dump",
                    "-h", conn_params.get("host", "localhost"),
                    "-p", str(conn_params.get("port", 5432)),
                    "-U", conn_params.get("user", "postgres"),
                    "-d", conn_params.get("name", "stockchecker"),
                    "-f", backup_path
                ]

                import subprocess
                subprocess.run(cmd, env={"PGPASSWORD": conn_params.get("password", "")})
                logger.info(f"PostgreSQL database backed up to {backup_path}")
            else:
                # Use SQLite's backup API
                with self.get_connection() as (cursor, conn):
                    # Create a new SQLite database for backup
                    backup_conn = sqlite3.connect(backup_path)

                    # Use SQLite backup API
                    conn.backup(backup_conn)

                    backup_conn.close()
                    logger.info(f"SQLite database backed up to {backup_path}")

            return True

        except Exception as e:
            logger.error(f"Error backing up database: {str(e)}")
            return False

    def vacuum_database(self) -> bool:
        """
        Vacuum the database to optimize space and performance

        Returns:
            bool: True if successful, False otherwise
        """
        if self.db_type == "disabled":
            return False

        try:
            if self.db_type == "postgres":
                with self.get_connection() as (cursor, conn):
                    # PostgreSQL vacuum
                    cursor.execute("VACUUM ANALYZE")
                    logger.info("PostgreSQL database vacuumed")
            else:
                # SQLite needs a direct connection for vacuum
                db_path = self.pool["db_path"]
                conn = sqlite3.connect(db_path)
                conn.execute("VACUUM")
                conn.close()
                logger.info("SQLite database vacuumed")

            return True

        except Exception as e:
            logger.error(f"Error vacuuming database: {str(e)}")
            return False

    def close(self):
        """Close the database connection pool"""
        if self.db_type == "postgres" and self.pool:
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Simple module adapter to use file-based storage when database is disabled
class FileStorageAdapter:
    """
    Adapter to provide database-like interface using file storage
    Useful for modules that expect database functionality but when DB is disabled
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the file storage adapter

        Args:
            data_dir: Directory to store data files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Cache of loaded data to avoid frequent file operations
        self.cache = {}

    def add_product(self, product: Dict[str, Any]) -> bool:
        """Store product in file system"""
        module = product.get("module", "unknown")
        module_dir = self.data_dir / module
        module_dir.mkdir(exist_ok=True)

        # Load existing products
        products = self._load_module_products(module)

        # Update or add product
        products[product["pid"]] = {
            **product,
            "last_check": datetime.datetime.now().isoformat()
        }

        # Save updated products
        return self._save_module_products(module, products)

    def get_product(self, pid: str) -> Optional[Dict[str, Any]]:
        """Get product from file system"""
        # Search in all module files
        for module_file in self.data_dir.glob("*/*_products.json"):
            module = module_file.parent.name
            products = self._load_module_products(module)

            if pid in products:
                return products[pid]

        return None

    def get_products_by_module(self, module: str, limit: int = 100,
                               in_stock: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get products for a module from file system"""
        products = self._load_module_products(module)

        # Filter products
        result = []
        for product in products.values():
            if in_stock is not None and product.get("in_stock", False) != in_stock:
                continue

            result.append(product)

            if len(result) >= limit:
                break

        return result

    def update_stock_status(self, pid: str, in_stock: bool,
                            stores: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Update product stock status in file system"""
        product = self.get_product(pid)

        if not product:
            return False

        module = product.get("module", "unknown")
        products = self._load_module_products(module)

        # Skip if no change
        if product.get("in_stock", False) == in_stock:
            # Just update last check time
            products[pid]["last_check"] = datetime.datetime.now().isoformat()
            return self._save_module_products(module, products)

        # Update product
        products[pid]["in_stock"] = in_stock
        products[pid]["last_check"] = datetime.datetime.now().isoformat()

        if in_stock:
            products[pid]["last_in_stock"] = datetime.datetime.now().isoformat()
            if stores:
                products[pid]["stores"] = stores
        else:
            products[pid]["last_out_of_stock"] = datetime.datetime.now().isoformat()
            products[pid]["stores"] = []

        # Save updated products
        return self._save_module_products(module, products)

    def save_cookies(self, module: str, domain: str, cookies: Dict[str, str],
                     expires_hours: int = 24) -> bool:
        """Save cookies to file system"""
        cookies_file = self.data_dir / f"{module}_cookies.json"

        try:
            # Load existing cookies
            if cookies_file.exists():
                with open(cookies_file, "r") as f:
                    stored_cookies = json.load(f)
            else:
                stored_cookies = {}

            # Update cookies for domain
            expires_at = (datetime.datetime.now() +
                          datetime.timedelta(hours=expires_hours)).isoformat()

            stored_cookies[domain] = {
                "cookies": cookies,
                "timestamp": datetime.datetime.now().isoformat(),
                "expires_at": expires_at
            }

            # Save updated cookies
            with open(cookies_file, "w") as f:
                json.dump(stored_cookies, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")
            return False

    def load_cookies(self, module: str, domain: str) -> Optional[Dict[str, str]]:
        """Load cookies from file system"""
        cookies_file = self.data_dir / f"{module}_cookies.json"

        if not cookies_file.exists():
            return None

        try:
            with open(cookies_file, "r") as f:
                stored_cookies = json.load(f)

            if domain not in stored_cookies:
                return None

            domain_cookies = stored_cookies[domain]

            # Check if cookies are expired
            expires_at = datetime.datetime.fromisoformat(domain_cookies["expires_at"])
            if expires_at < datetime.datetime.now():
                return None

            return domain_cookies["cookies"]

        except Exception as e:
            logger.error(f"Error loading cookies: {str(e)}")
            return None

    def _load_module_products(self, module: str) -> Dict[str, Dict[str, Any]]:
        """Load products for a module from file"""
        cache_key = f"products_{module}"

        # Return from cache if available
        if cache_key in self.cache:
            return self.cache[cache_key]

        products_file = self.data_dir / f"{module}_products.json"

        if not products_file.exists():
            return {}

        try:
            with open(products_file, "r") as f:
                products = json.load(f)

            # Update cache
            self.cache[cache_key] = products

            return products

        except Exception as e:
            logger.error(f"Error loading products for {module}: {str(e)}")
            return {}

    def _save_module_products(self, module: str, products: Dict[str, Dict[str, Any]]) -> bool:
        """Save products for a module to file"""
        cache_key = f"products_{module}"

        # Update cache
        self.cache[cache_key] = products

        products_file = self.data_dir / f"{module}_products.json"

        try:
            with open(products_file, "w") as f:
                json.dump(products, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Error saving products for {module}: {str(e)}")
            return False

    def close(self):
        """Clean up resources"""
        # Nothing to do for file storage
        pass


# Helper function to get database instance
def get_database(config: Optional[Dict[str, Any]] = None) -> Union[DatabaseManager, FileStorageAdapter]:
    """
    Get a database instance based on configuration

    Args:
        config: Database configuration

    Returns:
        DatabaseManager or FileStorageAdapter instance
    """
    if not config:
        # Try to load from global config
        try:
            from utils.config_loader import load_global_config
            global_config = load_global_config()

            if "database" in global_config:
                config = global_config["database"]
            else:
                # Default configuration
                config = {
                    "enabled": True,
                    "type": "sqlite",
                    "file": "data/stockchecker.db"
                }
        except:
            # Fallback configuration
            config = {
                "enabled": True,
                "type": "sqlite",
                "file": "data/stockchecker.db"
            }

    if not config.get("enabled", True):
        logger.info("Database disabled, using file storage adapter")
        return FileStorageAdapter()

    db_type = config.get("type", "").lower()

    if db_type == "postgres" or db_type == "postgresql":
        if POSTGRES_AVAILABLE:
            return DatabaseManager(config)
        else:
            logger.warning("PostgreSQL selected but psycopg2 not available, falling back to SQLite")
            config["type"] = "sqlite"
            return DatabaseManager(config)
    else:
        return DatabaseManager(config)


# Example usage
if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing database manager...")

    # SQLite configuration for testing
    sqlite_config = {
        "enabled": True,
        "type": "sqlite",
        "file": "test_db.sqlite"
    }

    # Create database manager
    db = get_database(sqlite_config)

    # Test adding a product
    test_product = {
        "pid": "TEST123",
        "title": "Test Product",
        "price": "19.99",
        "url": "https://example.com/product/TEST123",
        "image_url": "https://example.com/images/TEST123.jpg",
        "in_stock": True,
        "module": "test_module"
    }

    print(f"Adding test product: {test_product['title']}")
    db.add_product(test_product)

    # Test retrieving the product
    retrieved = db.get_product("TEST123")
    if retrieved:
        print(f"Retrieved product: {retrieved['title']}")
        print(f"Price: ${retrieved['price']}")
        print(f"In Stock: {retrieved['in_stock']}")

    # Test retrieving by module
    module_products = db.get_products_by_module("test_module")
    print(f"Retrieved {len(module_products)} products for test_module")

    # Test updating stock status
    db.update_stock_status("TEST123", False)
    updated = db.get_product("TEST123")
    if updated:
        print(f"Updated stock status: {updated['in_stock']}")

    # Test cookie storage
    test_cookies = {
        "session": "abc123",
        "user": "test_user"
    }
    db.save_cookies("test_module", "example.com", test_cookies)

    # Test retrieving cookies
    cookies = db.load_cookies("test_module", "example.com")
    if cookies:
        print(f"Retrieved cookies: {cookies}")

    # Test batch operations
    batch_products = [
        {
            "pid": "BATCH1",
            "title": "Batch Product 1",
            "price": "10.99",
            "in_stock": True,
            "module": "test_module"
        },
        {
            "pid": "BATCH2",
            "title": "Batch Product 2",
            "price": "15.99",
            "in_stock": False,
            "module": "test_module"
        }
    ]
    success, failures = db.batch_add_products(batch_products)
    print(f"Batch added {success} products, {failures} failures")

    # Get database stats
    stats = db.get_database_stats()
    print(f"Database stats: {stats}")

    # Clean up
    print("Cleaning up...")
    db.close()

    # Remove test database
    import os

    if os.path.exists("test_db.sqlite"):
        os.remove("test_db.sqlite")
        print("Test database removed")