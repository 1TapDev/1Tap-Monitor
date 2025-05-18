#!/usr/bin/env python3
"""
Optimized Books-A-Million Module
Checks stock of Pokemon products on booksamillion.com
"""

import os
import sys
import json
import re
import time
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Add project root to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import requests

# Create utils/__init__.py if it doesn't exist
utils_init = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils', '__init__.py')
if not os.path.exists(utils_init):
    os.makedirs(os.path.dirname(utils_init), exist_ok=True)
    with open(utils_init, 'w') as f:
        f.write("# This file makes the directory a Python package\n")

try:
    from utils.cloudflare_bypass import CloudflareBypass, get_cloudflare_bypass
except ImportError:
    # If import fails, create a simple version for compatibility
    class CloudflareBypass:
        def __init__(self, cookie_file, base_url, target_page):
            self.session = requests.Session()

        def get(self, url, **kwargs):
            return self.session.get(url, **kwargs)

        def post(self, url, **kwargs):
            return self.session.post(url, **kwargs)

        def refresh_session(self):
            self.session = requests.Session()

        def set_logging(self, enable_logging=True, save_readable=False):
            pass


    def get_cloudflare_bypass(base_url, cookie_file=None):
        return CloudflareBypass(cookie_file="", base_url=base_url, target_page="/")

try:
    from utils.config_loader import load_module_config
except ImportError:
    # If import fails, create a simple config loader
    def load_module_config(module_name):
        """Simplified config loader"""
        # Try to load from different possible locations
        config_paths = [
            f"config/modules/{module_name}.json",
            f"config/{module_name}.json",
            f"config_modules_{module_name}.json",
            f"config_{module_name}.json"
        ]

        for path in config_paths:
            try:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        return json.load(f)
            except Exception:
                pass

        # Return default config if none found
        return {
            "name": "Books-A-Million",
            "enabled": True,
            "interval": 300,
            "search_radius": 250,
            "target_zipcode": "30135",
            "cookie_file": "data/booksamillion_cookies.json",
            "search_urls": [],
            "pids": ["F820650412493", "F820650413315"]
        }

# Configure module logger
logger = logging.getLogger("Booksamillion")


class Booksamillion:
    """
    Module for checking Pokemon product stock on booksamillion.com
    """

    # Module metadata (used by the dispatcher)
    NAME = "Books-A-Million"
    VERSION = "2.1.0"
    INTERVAL = 300  # Default to 5 minutes

    def __init__(self):
        """Initialize the Books-A-Million module with configuration"""
        # Load configuration
        self.config = self._load_config()

        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        os.makedirs("logs/requests", exist_ok=True)

        # Initialize CloudflareBypass handler
        self.cf_bypass = get_cloudflare_bypass(
            base_url="https://www.booksamillion.com",
            cookie_file=self.config.get("cookie_file", "data/booksamillion_cookies.json"),
            cookie_max_age=3600  # Keep cookies valid for 1 hour
        )

        # Configure logging behavior
        self.cf_bypass.set_logging(
            enable_logging=self.config.get("debug", {}).get("log_requests", True),
            save_readable=self.config.get("debug", {}).get("save_html", False)
        )
        self.cf_bypass.aggressive_mode = True

        # Create session
        self.session = self.cf_bypass.create_session()

        # Load product data
        self.products = self._load_products()

        # Track last stock check time for each product
        self.last_check = {}

        # Store information about stock changes
        self.stock_changes = {}

        logger.info(f"Initialized {self.NAME} module v{self.VERSION}")
        logger.info(f"Loaded {len(self.products)} products from cache")
        logger.info(
            f"Configured for zip code {self.config.get('target_zipcode')} with radius {self.config.get('search_radius')}mi")

    def _load_config(self) -> Dict[str, Any]:
        """Load module configuration"""
        config = load_module_config("booksamillion")

        if not config:
            # Default configuration if none found
            config = {
                "name": "Books-A-Million",
                "enabled": True,
                "interval": 300,
                "timeout": 30,
                "retry_attempts": 3,
                "search_radius": 250,
                "target_zipcode": "30135",
                "bypass_method": "cloudscraper",
                "cookie_file": "data/booksamillion_cookies.json",
                "product_db_file": "data/booksamillion_products.json",
                "search_urls": [
                    "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date",
                    "https://www.booksamillion.com/search2?query=pokemon%20cards&filters%5Bcategory%5D=Toys&sort_by=release_date"
                ],
                "pids": [
                    "F820650412493",
                    "F820650413315",
                    "F820650859007"
                ],
                "keywords": [
                    "pokemon",
                    "limited edition"
                ],
                "debug": {
                    "log_requests": True,
                    "save_html": False
                }
            }
            logger.warning("No configuration found, using defaults")

            # Try to save default config
            try:
                os.makedirs("config/modules", exist_ok=True)
                with open("config/modules/booksamillion.json", "w") as f:
                    json.dump(config, f, indent=2)
                logger.info("Created default config file")
            except Exception as e:
                logger.error(f"Error creating default config: {str(e)}")

        return config

    def _load_products(self) -> Dict[str, Dict]:
        """Load product cache"""
        product_db_file = self.config.get("product_db_file", "data/booksamillion_products.json")

        if os.path.exists(product_db_file):
            try:
                with open(product_db_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading products from file: {str(e)}")

        return {}

    def _save_products(self):
        """Save products to cache file"""
        product_db_file = self.config.get("product_db_file", "data/booksamillion_products.json")

        try:
            with open(product_db_file, 'w') as f:
                json.dump(self.products, f, indent=2)
            logger.debug(f"Saved {len(self.products)} products to cache")
        except Exception as e:
            logger.error(f"Error saving products to file: {str(e)}")

    def check_stock(self, pid: str = None, proxy: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Check stock availability for products

        Args:
            pid: Specific product ID to check (optional)
            proxy: Optional proxy configuration

        Returns:
            List of product results with stock information
        """
        results = []

        # Determine which PIDs to check
        if pid:
            # Check specific PID
            pids_to_check = [pid]
        else:
            # Get PIDs from configuration
            pids_to_check = self.config.get("pids", [])

            # Add any PIDs from the product cache that aren't in the config
            for product_pid in self.products.keys():
                if product_pid not in pids_to_check:
                    pids_to_check.append(product_pid)

            if not pids_to_check:
                logger.warning("No PIDs configured to check")
                return results

        # Check stock for each PID
        for current_pid in pids_to_check:
            try:
                # Add small delay between checks
                if results:  # Not the first request
                    time.sleep(random.uniform(1.5, 3.0))

                # Check stock for this PID
                result = self._check_single_stock(current_pid, proxy)

                if result:
                    results.append(result)
                    self.last_check[current_pid] = time.time()

            except Exception as e:
                logger.error(f"Error checking stock for {current_pid}: {str(e)}")

        # Save updated product data
        self._save_products()

        logger.info(f"Completed stock check for {len(results)} products")
        return results

    def _check_single_stock(self, pid: str, proxy: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Check stock for a single product

        Args:
            pid: Product ID
            proxy: Optional proxy configuration

        Returns:
            Dictionary with stock information
        """
        logger.info(f"Checking stock for {pid}")

        # Setup proxy if provided
        if proxy and isinstance(proxy, dict) and proxy.get('http'):
            self.session.proxies.update(proxy)

        # Initialize result template
        result = {
            "pid": pid,
            "title": "",
            "price": "",
            "url": "",
            "image": "",
            "in_stock": False,
            "stores": [],
            "check_time": datetime.now().isoformat()
        }

        # Get zip code and radius from config - use defaults if not specified
        zipcode = self.config.get("target_zipcode", "30135")
        radius = self.config.get("search_radius", 250)

        # Build store inventory URL with proper zipcode and radius
        inventory_url = (
            f"https://www.booksamillion.com/bullseye"
            f"?PostalCode={zipcode}"
            f"&Radius={radius}"
            f"&action=bullseye"
            f"&pid={pid}"
            f"&code="
            f"&StartIndex=0"
            f"&PageSize=25"
        )

        # Get product page URL for referrer
        product_url = f"https://www.booksamillion.com/p/{pid}"

        # Create headers for the request
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": product_url,
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty"
        }

        # Make request with retry mechanism
        max_retries = self.config.get("retry_attempts", 3)
        backoff_base = 1.5

        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempt {attempt + 1}/{max_retries} for {pid}")

                # Make the request
                response = self.cf_bypass.get(
                    inventory_url,
                    headers=headers,
                    timeout=self.config.get("timeout", 30),
                    enable_logging=True,
                    log_filename=f"{pid}.log"  # Use PID for log filename
                )

                if response.status_code == 200:
                    break

                logger.warning(f"Got status code {response.status_code} on attempt {attempt + 1}")

                # Refresh session only if we hit a cloudflare challenge
                if "challenge" in response.text.lower() or response.status_code == 403:
                    logger.info("Refreshing cookies due to Cloudflare challenge")
                    self.cf_bypass.refresh_session()

                # Calculate backoff with jitter
                wait_time = backoff_base * (2 ** attempt) * (0.75 + 0.5 * random.random())
                time.sleep(min(wait_time, 30))  # Cap at 30 seconds

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")

                # Exponential backoff with jitter
                wait_time = backoff_base * (2 ** attempt) * (0.75 + 0.5 * random.random())
                time.sleep(min(wait_time, 30))

                # Refresh session before next attempt
                self.cf_bypass.refresh_session()

                # On last attempt, return the empty result
                if attempt == max_retries - 1:
                    return result

        # Process response
        try:
            # Try to parse JSON
            try:
                stock_data = response.json()
            except:
                # Try to extract JSON from HTML
                json_match = re.search(r'({"userinfo":.*?})', response.text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(1)
                    stock_data = json.loads(json_text)
                else:
                    # Try alternate pattern
                    json_match = re.search(r'({"pidinfo":.*?})', response.text, re.DOTALL)
                    if json_match:
                        json_text = json_match.group(1)
                        stock_data = json.loads(json_text)
                    else:
                        json_match = re.search(r'({"Error":[0-9]+,"ErrorText":".*?"})', response.text, re.DOTALL)
                        if json_match:
                            json_text = json_match.group(1)
                            stock_data = json.loads(json_text)
                            if "ErrorText" in stock_data:
                                logger.warning(f"Error from API: {stock_data['ErrorText']}")
                        else:
                            logger.error(f"Could not find JSON data in response for {pid}")
                            return result

            # Check for API error
            if "Error" in stock_data and stock_data.get("Error") != 0:
                logger.warning(f"API Error: {stock_data.get('ErrorText', 'Unknown error')}")
                # Continue to extract product details if available

            # Extract product details
            if 'pidinfo' in stock_data:
                result["title"] = stock_data['pidinfo'].get('title', '')
                result["price"] = stock_data['pidinfo'].get('retail_price', '')
                result["url"] = stock_data['pidinfo'].get('td_url', '')
                result["image"] = stock_data['pidinfo'].get('image_url', '')
                logger.info(f"Found product: {result['title']}")

            # Check store availability
            if 'ResultList' in stock_data and stock_data['ResultList']:
                stores_count = len(stock_data['ResultList'])
                in_stock_count = 0

                for store in stock_data['ResultList']:
                    availability = store.get('Availability', '').upper()
                    if availability in ['IN STOCK', 'LIMITED STOCK']:
                        result["in_stock"] = True
                        in_stock_count += 1

                        # Add store details
                        store_info = {
                            "store_id": store.get('StoreNumber', ''),
                            "name": store.get('Name', ''),
                            "address": f"{store.get('Address1', '')} {store.get('Address2', '')}".strip(),
                            "city": store.get('City', ''),
                            "state": store.get('State', ''),
                            "zip": store.get('PostCode', ''),
                            "phone": store.get('PhoneNumber', ''),
                            "distance": store.get('Distance', ''),
                            "quantity": store.get('ShowQty', ''),  # Stock quantity if available
                        }

                        result["stores"].append(store_info)

                logger.info(f"Found {in_stock_count} of {stores_count} stores with stock for {pid}")

            # Update product information
            self._update_product(result)
            if result.get("in_stock"):
                self.send_discord_notification(result)

            return result

        except Exception as e:
            logger.error(f"Error processing response for {pid}: {str(e)}")
            return result

    def _update_product(self, result: Dict[str, Any]) -> bool:
        """
        Update product information and detect stock changes

        Args:
            result: Product result with stock information

        Returns:
            bool: True if stock status changed, False otherwise
        """
        pid = result["pid"]
        in_stock = result["in_stock"]
        current_time = datetime.now().isoformat()

        # Check if this is a new product
        is_new = pid not in self.products

        # Get previous stock status to detect changes
        stock_changed = False

        if not is_new:
            previous_status = self.products[pid].get("in_stock", False)
            stock_changed = previous_status != in_stock

            if stock_changed:
                logger.info(f"Stock status changed for {pid}: {previous_status} -> {in_stock}")

                # Store change information for notification
                self.stock_changes[pid] = {
                    "pid": pid,
                    "title": result["title"],
                    "price": result["price"],
                    "url": result["url"],
                    "image": result["image"],
                    "in_stock": in_stock,
                    "previous_status": previous_status,
                    "change_time": current_time,
                    "stores": result["stores"] if in_stock else []
                }

        # Update or add product in cache
        self.products[pid] = {
            "pid": pid,
            "title": result["title"] or self.products.get(pid, {}).get("title", ""),
            "price": result["price"] or self.products.get(pid, {}).get("price", ""),
            "url": result["url"] or self.products.get(pid, {}).get("url", ""),
            "image": result["image"] or self.products.get(pid, {}).get("image", ""),
            "in_stock": in_stock,
            "first_seen": self.products.get(pid, {}).get("first_seen", current_time),
            "last_check": current_time,
            "last_in_stock": current_time if in_stock else self.products.get(pid, {}).get("last_in_stock"),
            "last_out_of_stock": current_time if not in_stock else self.products.get(pid, {}).get("last_out_of_stock"),
            "stores": result["stores"] if in_stock else []
        }

        return is_new or stock_changed

    def scan_new_items(self, proxy: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Scan search pages for new Pokemon products

        Args:
            proxy: Optional proxy configuration

        Returns:
            List of new products found
        """
        logger.info("Scanning for new Pokemon products")

        # Setup proxy if provided
        if proxy and isinstance(proxy, dict) and proxy.get('http'):
            self.session.proxies.update(proxy)

        new_products = []
        search_urls = self.config.get("search_urls", [])

        for url_index, url in enumerate(search_urls):
            logger.info(f"Scanning URL {url_index + 1}/{len(search_urls)}: {url}")

            try:
                # Add delay between requests
                if url_index > 0:
                    time.sleep(random.uniform(2.0, 4.0))

                # Fetch search page
                response = self.cf_bypass.get(
                    url,
                    timeout=self.config.get("timeout", 30)
                )

                if response.status_code != 200:
                    logger.warning(f"Got status code {response.status_code} for {url}")
                    continue

                # Extract product information
                products = self._extract_products_from_html(response.text, url)

                for product in products:
                    pid = product.get("pid")

                    # Skip if no PID or already in database
                    if not pid or pid in self.products:
                        continue

                    logger.info(f"Found new product: {product.get('title')} (PID: {pid})")

                    # Add to the products dictionary
                    current_time = datetime.now().isoformat()
                    self.products[pid] = {
                        "pid": pid,
                        "title": product.get("title", ""),
                        "price": product.get("price", ""),
                        "url": product.get("url", ""),
                        "image": product.get("image", ""),
                        "in_stock": False,  # Will be updated after stock check
                        "first_seen": current_time,
                        "last_check": current_time
                    }

                    # Add to new products list
                    new_products.append(product)

            except Exception as e:
                logger.error(f"Error scanning URL {url}: {str(e)}")

        logger.info(f"Found {len(new_products)} new products")

        # Save updated product data
        if new_products:
            self._save_products()

        # Check stock for new products
        for product in new_products:
            try:
                # Add small delay between checks
                time.sleep(random.uniform(1.0, 2.0))

                # Check stock
                self._check_single_stock(product["pid"], proxy)

            except Exception as e:
                logger.error(f"Error checking stock for new product {product.get('pid')}: {str(e)}")

        # Return new + updated in-stock products
        return [self.products[prod["pid"]] for prod in new_products]

    def _extract_products_from_html(self, html: str, base_url: str) -> List[Dict[str, Any]]:
        """
        Extract product information from HTML

        Args:
            html: HTML content
            base_url: Base URL for resolving relative URLs

        Returns:
            List of extracted products
        """
        products = []

        try:
            # Extract product blocks
            product_blocks = re.findall(r'<div class="search-result-item".*?</div>\s*</div>\s*</div>', html, re.DOTALL)

            for block in product_blocks:
                # Extract PID
                pid_match = re.search(r'pid=([A-Za-z0-9]+)', block) or re.search(r'/([A-Za-z0-9]+)"', block)

                if not pid_match:
                    continue

                pid = pid_match.group(1)

                # Extract title
                title_match = re.search(r'<div class="search-item-title">\s*<a[^>]*>(.*?)</a>', block, re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""

                # Check if title contains "pokemon" (case insensitive)
                keywords = self.config.get("keywords", ["pokemon"])
                if not any(kw.lower() in title.lower() for kw in keywords):
                    continue

                # Extract URL
                url_match = re.search(r'<a href="([^"]+)"[^>]*>.*?</a>', block)
                url = url_match.group(1) if url_match else ""

                # Make URL absolute
                if url and not url.startswith(('http://', 'https://')):
                    url = f"https://www.booksamillion.com{url}" if not url.startswith(
                        '/') else f"https://www.booksamillion.com{url}"

                # Extract price
                price_match = re.search(r'<span class="our-price">\s*\$([\d\.]+)', block)
                price = price_match.group(1) if price_match else ""

                # Extract image
                image_match = re.search(r'<img src="([^"]+)"', block)
                image = image_match.group(1) if image_match else ""

                # Make image URL absolute
                if image and not image.startswith(('http://', 'https://')):
                    image = f"https://www.booksamillion.com{image}" if not image.startswith(
                        '/') else f"https://www.booksamillion.com{image}"

                # Create product entry
                product = {
                    "pid": pid,
                    "title": title,
                    "url": url,
                    "price": price,
                    "image": image
                }

                products.append(product)

            logger.info(f"Extracted {len(products)} Pokemon products from page")

        except Exception as e:
            logger.error(f"Error extracting products from HTML: {str(e)}")

        return products

    def format_discord_message(self, product: Dict[str, Any], is_new: bool = False) -> Dict[str, Any]:
        """
        Format product information for Discord webhook

        Args:
            product: Product information
            is_new: Whether this is a new product notification

        Returns:
            Formatted Discord message
        """
        # Determine title prefix based on notification type
        if is_new:
            title = f"New Item: {product.get('title', 'Unknown Product')}"
        elif product.get('in_stock', False):
            title = f"🟢 IN STOCK: {product.get('title', 'Unknown Product')}"
        else:
            title = f"🔴 OUT OF STOCK: {product.get('title', 'Unknown Product')}"

        # Build description
        description = []

        if is_new:
            description.append(f"A new Pokemon product has been added to Books-A-Million!")

        if product.get('price'):
            description.append(f"Price: ${product.get('price')}")

        # Add SKU/PID
        description.append(f"SKU: {product.get('pid')}")

        # Add search term if it's a new product
        if is_new:
            description.append(f"Search Term: pokemon")

        # Add store information for in-stock products
        if product.get('in_stock', False) and product.get('stores'):
            description.append("\n**Available at these stores:**")

            for store in product.get('stores')[:5]:  # Limit to 5 stores to avoid too long message
                store_line = f"• {store.get('name', '')}: {store.get('address', '')}, {store.get('city', '')}, {store.get('state', '')} {store.get('zip', '')}"
                if store.get('quantity'):
                    store_line += f" (Qty: {store.get('quantity')})"
                description.append(store_line)

            if len(product.get('stores', [])) > 5:
                description.append(f"...and {len(product.get('stores', [])) - 5} more stores")

        # Add links
        links = [
            f"[eBay](https://www.ebay.com/sch/i.html?_nkw={product.get('pid')})",
            f"[Amazon](https://www.amazon.com/s?k={product.get('pid')})",
            f"[Walmart](https://www.walmart.com/search/?query={product.get('pid')})",
            f"[Keepa](https://keepa.com/#!search/amazon-{product.get('pid')})",
            f"[SellerAmp](https://selleramp.com/search?query={product.get('pid')})",
            f"[Google](https://www.google.com/search?q={product.get('pid')})"
        ]

        description.append("\n**Links:**")
        description.append(" - ".join(links))

        # Create embed
        embed = {
            "title": title,
            "description": "\n".join(description),
            "color": 5814783 if product.get('in_stock', False) else 15158332,
            # Green for in stock, red for out of stock
            "url": product.get('url', ''),
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "FastBreakCards Monitors • Books a million • " + datetime.now().strftime("%I:%M:%S %p EST")
            }
        }

        # Add thumbnail if image URL available
        if product.get('image'):
            embed["thumbnail"] = {
                "url": product.get('image')
            }

        return {
            "username": "FastBreakCards Monitors",
            "embeds": [embed]
        }

    def send_discord_notification(self, product: Dict[str, Any], is_new: bool = False) -> bool:
        """Send Discord notification for product"""
        # First check module-specific webhook from config
        webhook_url = self.config.get("webhook", {}).get("url", "")

        # If empty, check for environment variable
        if not webhook_url:
            import os
            webhook_url = os.getenv('BOOKSAMILLION_WEBHOOK') or os.getenv('DISCORD_WEBHOOK', "")

        # Then check discord_webhook from main config
        if not webhook_url:
            webhook_url = self.config.get("discord_webhook", "")

        if not webhook_url:
            logger.warning("No Discord webhook URL configured")
            return False

        # Format message
        message = self.format_discord_message(product, is_new)

        try:
            # Send webhook
            response = requests.post(
                webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=10  # Add timeout
            )

            if response.status_code == 204:
                logger.info(f"Discord notification sent for {product.get('pid')}")
                return True
            else:
                logger.error(f"Discord notification failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Discord notification: {str(e)}")
            return False

    def main_monitor_loop(self, proxy_manager=None, notifier=None):
        """
        Main monitoring loop for Books-A-Million

        Args:
            proxy_manager: Optional proxy manager
            notifier: Optional notifier instance (from the dispatcher)
        """
        logger.info("Starting main monitor loop")

        try:
            # Get proxy if available
            proxy = None
            if proxy_manager:
                try:
                    proxy = proxy_manager.get_proxy()
                except Exception as e:
                    logger.error(f"Error getting proxy: {str(e)}")

            # Step 1: Scan for new products
            new_products = self.scan_new_items(proxy=proxy)

            # Step 2: Send notifications for new products
            for product in new_products:
                # Use the notifier module if available, otherwise use internal Discord notification
                if notifier:
                    notifier.send_alert(
                        title=f"New Pokemon Product: {product.get('title', 'Unknown')}",
                        description=f"A new Pokemon product has been found on Books-A-Million.\nPrice: ${product.get('price', 'Unknown')}\nSKU: {product.get('pid', 'Unknown')}",
                        url=product.get('url', ''),
                        image=product.get('image', ''),
                        store=self.NAME
                    )
                else:
                    # Use internal Discord notification
                    self.send_discord_notification(product, is_new=True)

            # Step 3: Check stock for existing products
            results = self.check_stock(proxy=proxy)

            # Step 4: Send notifications for stock changes
            for pid, change_info in self.stock_changes.items():
                logger.info(f"Sending notification for stock change: {pid}")

                # Make sure to send to both notifier and webhook
                # First try the notifier module if available
                if notifier:
                    if change_info.get('in_stock', False):
                        notifier.send_alert(
                            title=f"🟢 NOW IN STOCK: {change_info.get('title', 'Unknown')}",
                            description=f"This Pokemon product is now IN STOCK at Books-A-Million!\nPrice: ${change_info.get('price', 'Unknown')}\nAvailable at {len(change_info.get('stores', []))} stores",
                            url=change_info.get('url', ''),
                            image=change_info.get('image', ''),
                            store=self.NAME
                        )
                    else:
                        notifier.send_alert(
                            title=f"🔴 OUT OF STOCK: {change_info.get('title', 'Unknown')}",
                            description=f"This Pokemon product is now OUT OF STOCK at Books-A-Million\nPrice: ${change_info.get('price', 'Unknown')}",
                            url=change_info.get('url', ''),
                            image=change_info.get('image', ''),
                            store=self.NAME
                        )

                # Always send through the internal webhook too as a backup
                success = self.send_discord_notification(change_info)
                if success:
                    logger.info(f"Successfully sent Discord notification for {pid}")
                else:
                    logger.error(f"Failed to send Discord notification for {pid}")

            # Clear stock changes after notifications
            self.stock_changes = {}

            logger.info("Main monitor loop completed successfully")

        except Exception as e:
            logger.error(f"Error in main monitor loop: {str(e)}")


# For standalone testing
if __name__ == "__main__":
    # Force logging configuration for "Booksamillion" logger
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if rerunning
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        file_handler = logging.FileHandler("booksamillion.log")
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    # Create module instance
    monitor = Booksamillion()

    # Scan for new products
    new_products = monitor.scan_new_items()
    print(f"Found {len(new_products)} new products")

    # Check stock for products
    results = monitor.check_stock()
    monitor._save_products()
    print(f"Checked stock for {len(results)} products")

    # Send webhook for all in-stock items (test mode)
    for product in results:
        if product.get("in_stock"):
            print(f"Sending Discord test webhook for {product['pid']}")
            monitor.send_discord_notification(product, is_new=True)

    # Display in-stock products
    for product in results:
        if product.get('in_stock'):
            print(f"IN STOCK: {product.get('title')} at {len(product.get('stores', []))} stores")