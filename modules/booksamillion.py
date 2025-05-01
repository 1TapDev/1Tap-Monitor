#!/usr/bin/env python3
"""
Books-A-Million Module
Checks stock of items on booksamillion.com
"""

import json
import re
import time
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import random
import requests
import urllib.parse

# Optional imports for different Cloudflare bypass methods
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import tls_client
    TLS_CLIENT_AVAILABLE = True
except ImportError:
    TLS_CLIENT_AVAILABLE = False

# Import shared utility modules
from utils.cloudflare_bypass import create_session
from utils.headers_generator import generate_chrome_headers

logger = logging.getLogger("BooksAMillion")

class Booksamillion:
    """
    Module for checking stock on booksamillion.com
    """

    # Module metadata
    NAME = "Books-A-Million"
    VERSION = "1.0.0"
    INTERVAL = 300  # Default check interval in seconds

    def __init__(self):
        """Initialize the Books-A-Million module"""
        self.config = {
            "keywords": ["exclusive", "limited edition", "signed", "pokemon"],
            "search_urls": [
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date",
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date&page=2",
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date&page=3",
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date&page=4"
            ],
            "timeout": 15,
            "retry_attempts": 3,
            "search_radius": 250,  # Miles
            "target_zipcode": "30135",  # Default zip
            "bypass_method": "cloudscraper",  # Options: cloudscraper, selenium, tls_client
            "cookie_file": "booksamillion_cookies.json",
            "product_db_file": "booksamillion_products.json"
        }

        # Load module-specific config if available
        self._load_module_config()

        # Load or initialize cookies
        self.cookies = self._load_cookies()

        # Load or initialize product database
        self.products = self._load_products()

        # Create a session with the appropriate bypass method
        self.session = self._create_session()

    def _load_module_config(self):
        """Load module-specific configuration if available"""
        module_config_file = Path('config_booksamillion.json')
        if module_config_file.exists():
            try:
                with open(module_config_file, 'r') as f:
                    module_config = json.load(f)
                    self.config.update(module_config)
                    logger.info("Loaded module-specific configuration")
            except Exception as e:
                logger.error(f"Error loading module config: {str(e)}")

    def _load_cookies(self) -> Dict[str, str]:
        """Load cookies from file or return empty dict"""
        cookie_file = Path(self.config["cookie_file"])
        if cookie_file.exists():
            try:
                with open(cookie_file, 'r') as f:
                    cookies = json.load(f)
                    # Check if cookies are still valid (within 23 hours)
                    if cookies.get('timestamp', 0) > time.time() - 82800:
                        logger.info("Loaded valid cookies from file")
                        return cookies.get('cookies', {})
            except Exception as e:
                logger.error(f"Error loading cookies: {str(e)}")

        # If we get here, either no cookies or expired cookies
        logger.info("No valid cookies found, will generate new ones")
        return {}

    def _save_cookies(self, cookies: Dict[str, str]):
        """Save cookies to file with timestamp"""
        cookie_file = Path(self.config["cookie_file"])
        try:
            cookie_data = {
                'timestamp': time.time(),
                'cookies': cookies
            }
            with open(cookie_file, 'w') as f:
                json.dump(cookie_data, f, indent=2)
            logger.info("Saved cookies to file")
        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")

    def _load_products(self) -> Dict[str, Dict]:
        """Load product database from file or return empty dict"""
        product_file = Path(self.config["product_db_file"])
        if product_file.exists():
            try:
                with open(product_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading product database: {str(e)}")

        # If we get here, either no product DB or error
        return {}

    def _save_products(self):
        """Save product database to file"""
        product_file = Path(self.config["product_db_file"])
        try:
            with open(product_file, 'w') as f:
                json.dump(self.products, f, indent=2)
            logger.info(f"Saved {len(self.products)} products to database")
        except Exception as e:
            logger.error(f"Error saving product database: {str(e)}")

    def _create_session(self):
        """Create a session with the appropriate bypass method"""
        method = self.config.get("bypass_method", "cloudscraper")

        if method == "cloudscraper" and CLOUDSCRAPER_AVAILABLE:
            session = cloudscraper.create_scraper()
            logger.info("Created CloudScraper session")
        elif method == "tls_client" and TLS_CLIENT_AVAILABLE:
            session = tls_client.Session(client_identifier="chrome112")
            logger.info("Created TLS Client session")
        else:
            # Fallback to regular requests
            session = requests.Session()
            logger.info("Created regular requests session")

        # Update the session with our headers and cookies
        headers = generate_chrome_headers()
        session.headers.update(headers)

        # Add any saved cookies
        for name, value in self.cookies.items():
            session.cookies.set(name, value)

        return session

    def get_fresh_cookies(self) -> bool:
        """
        Get fresh Cloudflare cookies using browser automation.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Generating fresh Cloudflare cookies...")

        # Method 1: Selenium with undetected_chromedriver (if available)
        if SELENIUM_AVAILABLE:
            try:
                # Configure Chrome options
                options = uc.ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-gpu')

                # Create driver
                driver = uc.Chrome(options=options)
                driver.get('https://www.booksamillion.com')

                # Wait for page to load fully and Cloudflare to resolve
                time.sleep(5)

                # Extract cookies
                cookies = {}
                for cookie in driver.get_cookies():
                    cookies[cookie['name']] = cookie['value']

                # Close browser
                driver.quit()

                # Check if we got the Cloudflare cookies
                if 'cf_clearance' in cookies:
                    self.cookies = cookies
                    self._save_cookies(cookies)
                    logger.info("Successfully obtained Cloudflare cookies with Selenium")
                    return True
                else:
                    logger.warning("Failed to get Cloudflare cookies with Selenium")
            except Exception as e:
                logger.error(f"Error using Selenium for cookies: {str(e)}")

        # Method 2: CloudScraper
        if CLOUDSCRAPER_AVAILABLE:
            try:
                scraper = cloudscraper.create_scraper()
                response = scraper.get('https://www.booksamillion.com')

                if response.status_code == 200:
                    # Extract cookies from cloudscraper
                    cookies = {}
                    for cookie_name, cookie_value in scraper.cookies.get_dict().items():
                        cookies[cookie_name] = cookie_value

                    # Save cookies
                    self.cookies = cookies
                    self._save_cookies(cookies)
                    logger.info("Successfully obtained cookies with CloudScraper")
                    return True
                else:
                    logger.warning(f"Failed to get cookies with CloudScraper: {response.status_code}")
            except Exception as e:
                logger.error(f"Error using CloudScraper for cookies: {str(e)}")

        # Method 3: TLS Client
        if TLS_CLIENT_AVAILABLE:
            try:
                client = tls_client.Session(client_identifier="chrome112")
                response = client.get('https://www.booksamillion.com')

                if response.status_code == 200:
                    # Extract cookies
                    cookies = client.cookies.get_dict()

                    # Save cookies
                    self.cookies = cookies
                    self._save_cookies(cookies)
                    logger.info("Successfully obtained cookies with TLS Client")
                    return True
                else:
                    logger.warning(f"Failed to get cookies with TLS Client: {response.status_code}")
            except Exception as e:
                logger.error(f"Error using TLS Client for cookies: {str(e)}")

        logger.error("All cookie generation methods failed")
        return False

    def check_stock(self, pid: str, proxy: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Check stock availability for a specific PID

        Args:
            pid: Product ID to check
            proxy: Optional proxy configuration

        Returns:
            Dictionary with product and stock information
        """
        logger.info(f"Checking stock for PID: {pid}")

        # Set up proxies if provided
        if proxy:
            self.session.proxies.update(proxy)

        # Check if we need to refresh cookies first
        if 'cf_clearance' not in self.cookies:
            self.get_fresh_cookies()

        # Setup result template
        result = {
            "pid": pid,
            "title": "",
            "price": "",
            "url": "",
            "image": "",
            "in_stock": False,
            "stores": [],
            "check_time": datetime.now().isoformat(),
            "search_radius": self.config["search_radius"],
            "zipcode": self.config["target_zipcode"]
        }

        # Build the URL for stock check
        bullseye_url = (
            f"https://www.booksamillion.com/bullseye"
            f"?PostalCode={self.config['target_zipcode']}"
            f"&Radius={self.config['search_radius']}"
            f"&action=bullseye"
            f"&pid={pid}"
            f"&code="
            f"&StartIndex=0"
            f"&PageSize=25"
        )

        # Attempt the request with retries
        response = None
        for attempt in range(self.config["retry_attempts"]):
            try:
                response = self.session.get(
                    bullseye_url,
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Referer": f"https://www.booksamillion.com/p/{pid}"
                    },
                    timeout=self.config["timeout"]
                )

                # If we get a 403 or Cloudflare challenge, refresh cookies and retry
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning("Got Cloudflare challenge, refreshing cookies...")
                    self.get_fresh_cookies()
                    continue

                # If we get a successful response, break the retry loop
                if response.status_code == 200:
                    break

                logger.warning(f"Attempt {attempt+1} failed: HTTP {response.status_code}")
                time.sleep(2 * (attempt + 1))  # Increasing backoff

            except Exception as e:
                logger.error(f"Request error on attempt {attempt+1}: {str(e)}")
                time.sleep(2 * (attempt + 1))

        # Check if we got a valid response
        if not response or response.status_code != 200:
            logger.error(f"Failed to check stock for {pid} after {self.config['retry_attempts']} attempts")
            return result

        # Parse the JSON response
        try:
            stock_data = response.json()

            # Extract product details from pidinfo
            if 'pidinfo' in stock_data:
                result["title"] = stock_data['pidinfo'].get('title', '')
                result["price"] = stock_data['pidinfo'].get('retail_price', '')
                result["url"] = stock_data['pidinfo'].get('td_url', '')
                result["image"] = stock_data['pidinfo'].get('image_url', '')

            # Extract store availability from ResultList
            if 'ResultList' in stock_data:
                for store in stock_data['ResultList']:
                    if store.get('Availability', '').upper() == 'IN STOCK':
                        result["in_stock"] = True

                        # Add store details
                        store_info = {
                            "name": store.get('Name', ''),
                            "address": f"{store.get('Address1', '')} {store.get('Address2', '')}".strip(),
                            "city": store.get('City', ''),
                            "state": store.get('State', ''),
                            "zip": store.get('PostCode', ''),
                            "phone": store.get('PhoneNumber', ''),
                            "distance": store.get('Distance', ''),
                            "hours": store.get('BusinessHours', '')
                        }

                        result["stores"].append(store_info)

            logger.info(f"Stock check for {pid} complete: {'IN STOCK' if result['in_stock'] else 'OUT OF STOCK'}")

            # Update product database with results
            self._update_product_db(result)

            return result

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response for {pid}")
            return result
        except Exception as e:
            logger.error(f"Error processing stock data for {pid}: {str(e)}")
            return result

    def scan_new_items(self, proxy: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Scan search pages for new items

        Args:
            proxy: Optional proxy configuration

        Returns:
            List of new PIDs found
        """
        logger.info("Scanning for new items...")

        # Set up proxies if provided
        if proxy:
            self.session.proxies.update(proxy)

        # Check if we need to refresh cookies first
        if 'cf_clearance' not in self.cookies:
            self.get_fresh_cookies()

        new_pids = []

        # Process each search URL
        for url in self.config["search_urls"]:
            logger.info(f"Scanning URL: {url}")

            # Attempt the request with retries
            response = None
            for attempt in range(self.config["retry_attempts"]):
                try:
                    response = self.session.get(
                        url,
                        timeout=self.config["timeout"]
                    )

                    # If we get a 403 or Cloudflare challenge, refresh cookies and retry
                    if response.status_code == 403 or "challenge" in response.text.lower():
                        logger.warning("Got Cloudflare challenge, refreshing cookies...")
                        self.get_fresh_cookies()
                        continue

                    # If we get a successful response, break the retry loop
                    if response.status_code == 200:
                        break

                    logger.warning(f"Attempt {attempt+1} failed: HTTP {response.status_code}")
                    time.sleep(2 * (attempt + 1))  # Increasing backoff

                except Exception as e:
                    logger.error(f"Request error on attempt {attempt+1}: {str(e)}")
                    time.sleep(2 * (attempt + 1))

            # Check if we got a valid response
            if not response or response.status_code != 200:
                logger.error(f"Failed to scan URL {url} after {self.config['retry_attempts']} attempts")
                continue

            # Parse the HTML to find product PIDs
            try:
                html = response.text

                # Extract PIDs using regex pattern matching
                # Looking for patterns like: pid=F820650412493 or pid=9798400902550
                pid_pattern = r'pid=([A-Za-z0-9]+)'
                pids = re.findall(pid_pattern, html)

                # Clean up the PIDs (remove duplicates)
                pids = list(set(pids))

                logger.info(f"Found {len(pids)} PIDs on page")

                # Check which PIDs are new
                for pid in pids:
                    if pid not in self.products:
                        logger.info(f"Found new PID: {pid}")
                        new_pids.append(pid)

                # Delay between requests to avoid rate limiting
                time.sleep(random.uniform(1.0, 3.0))

            except Exception as e:
                logger.error(f"Error parsing search results from {url}: {str(e)}")

        logger.info(f"Scan complete. Found {len(new_pids)} new PIDs")
        return new_pids

    def _update_product_db(self, result: Dict[str, Any]):
        """
        Update the product database with new stock check results

        Args:
            result: Stock check result dictionary
        """
        pid = result["pid"]
        current_time = datetime.now().isoformat()
        in_stock = result["in_stock"]

        # Check if this is a new product
        is_new = pid not in self.products

        # If new product, initialize its entry
        if is_new:
            self.products[pid] = {
                "pid": pid,
                "title": result["title"],
                "price": result["price"],
                "url": result["url"],
                "image": result["image"],
                "first_seen": current_time,
                "last_check": current_time,
                "in_stock": in_stock,
                "last_in_stock": current_time if in_stock else None,
                "last_out_of_stock": current_time if not in_stock else None,
                "stores": result["stores"] if in_stock else []
            }
        else:
            # Update existing product
            product = self.products[pid]

            # Update basic info
            product["title"] = result["title"] or product["title"]
            product["price"] = result["price"] or product["price"]
            product["url"] = result["url"] or product["url"]
            product["image"] = result["image"] or product["image"]
            product["last_check"] = current_time

            # Check for stock status change
            stock_changed = product["in_stock"] != in_stock
            product["in_stock"] = in_stock

            if in_stock:
                product["last_in_stock"] = current_time
                product["stores"] = result["stores"]
            else:
                product["last_out_of_stock"] = current_time
                product["stores"] = []

        # Save the updated database
        self._save_products()

        # Return whether this is a new product or a stock change
        return is_new or (not is_new and stock_changed)

    def main_monitor_loop(self, proxy_manager=None, notifier=None):
        """
        Main monitoring loop that combines scanning and stock checking

        Args:
            proxy_manager: Optional proxy manager for rotation
            notifier: Optional notifier for sending alerts
        """
        logger.info("Starting main monitor loop")

        try:
            # Step 1: Scan for new items
            proxy = proxy_manager.get_proxy() if proxy_manager else None
            new_pids = self.scan_new_items(proxy=proxy)

            # Step 2: Process new PIDs
            for pid in new_pids:
                # Get a fresh proxy for each check
                if proxy_manager:
                    proxy = proxy_manager.get_proxy()

                # Check stock for the new PID
                result = self.check_stock(pid=pid, proxy=proxy)

                # Send notification for new product
                if notifier:
                    notifier.send_alert(
                        title=f"New Product: {result['title']}",
                        description=f"Found new product on Books-A-Million: {result['title']}\nPrice: ${result['price']}\nStatus: {'IN STOCK' if result['in_stock'] else 'OUT OF STOCK'}",
                        url=result["url"],
                        image=result["image"],
                        store=self.NAME
                    )

            # Step 3: Check existing products (prioritize ones not checked recently)
            # Sort by last check time, oldest first
            existing_pids = [(pid, data["last_check"]) for pid, data in self.products.items()]
            existing_pids.sort(key=lambda x: x[1])

            # Check up to 10 existing products per run
            for pid, _ in existing_pids[:10]:
                # Get a fresh proxy for each check
                if proxy_manager:
                    proxy = proxy_manager.get_proxy()

                # Get the old stock status
                old_status = self.products[pid]["in_stock"]

                # Check stock for the product
                result = self.check_stock(pid=pid, proxy=proxy)

                # If stock status changed, send notification
                if old_status != result["in_stock"] and notifier:
                    if result["in_stock"]:
                        # Changed from out of stock to in stock
                        notifier.send_alert(
                            title=f"🟢 NOW IN STOCK: {result['title']}",
                            description=(
                                f"Product is now IN STOCK at Books-A-Million!\n"
                                f"Price: ${result['price']}\n"
                                f"Available at {len(result['stores'])} stores"
                            ),
                            url=result["url"],
                            image=result["image"],
                            store=self.NAME
                        )
                    else:
                        # Changed from in stock to out of stock
                        notifier.send_alert(
                            title=f"🔴 OUT OF STOCK: {result['title']}",
                            description=(
                                f"Product is now OUT OF STOCK at Books-A-Million\n"
                                f"Price: ${result['price']}"
                            ),
                            url=result["url"],
                            image=result["image"],
                            store=self.NAME
                        )

                # Delay between checks to avoid rate limiting
                time.sleep(random.uniform(1.0, 3.0))

            logger.info("Main monitor loop completed successfully")

        except Exception as e:
            logger.error(f"Error in main monitor loop: {str(e)}")

if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and test the module
    bam = BooksAMillion()

    # Test cookie generation
    bam.get_fresh_cookies()

    # Scan for items
    new_pids = bam.scan_new_items()
    print(f"Found {len(new_pids)} new PIDs")

    # Test stock check with a known PID
    test_pid = "9798400902550"  # Solo Leveling Vol. 11
    if new_pids:
        test_pid = new_pids[0]

    result = bam.check_stock(test_pid)
    print(f"Stock check result for {test_pid}:")
    print(json.dumps(result, indent=2))