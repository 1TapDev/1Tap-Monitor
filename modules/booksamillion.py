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

from utils.cloudflare_bypass import CloudflareBypass
from utils.headers_generator import generate_chrome_headers
from utils.config_loader import load_module_config, load_module_targets, update_pid_list
from utils.request_logger import get_request_logger
from utils.http_logger import get_http_logger

logger = logging.getLogger("Booksamillion")

class Booksamillion:
    """
    Module for checking stock on booksamillion.com
    """

    # Module metadata
    NAME = "Books-A-Million"
    VERSION = "1.1.0"
    INTERVAL = 300  # Default check interval in seconds

    request_logger = get_request_logger()
    http_logger = get_http_logger()

    def __init__(self):
        """Initialize the Books-A-Million module"""
        # Default configuration
        self.config = {
            "timeout": 30,
            "retry_attempts": 5,
            "search_radius": 250,  # Miles
            "target_zipcode": "30135",  # Default zip
            "cookie_file": "data/booksamillion_cookies.json",
            "product_db_file": "data/booksamillion_products.json",
            "max_backoff_time": 60  # Maximum backoff time in seconds
        }

        # Load module-specific config
        module_config = load_module_config("booksamillion")
        if module_config:
            self.config.update(module_config)
            logger.info("Loaded module-specific configuration")

        # Load target configurations (URLs, PIDs, keywords)
        targets = load_module_targets("booksamillion")
        self.search_urls = targets.get("search_urls", [])
        self.item_urls = targets.get("item_urls", [])
        self.pids = targets.get("pids", [])
        self.keywords = targets.get("keywords", ["exclusive", "limited edition", "signed", "pokemon"])

        logger.info(f"Loaded {len(self.search_urls)} search URLs, {len(self.item_urls)} item URLs, "
                    f"{len(self.pids)} PIDs, and {len(self.keywords)} keywords")

        # Ensure data directory exists
        data_dir = Path("data")
        if not data_dir.exists():
            data_dir.mkdir()

        # Initialize CloudflareBypass handler
        self.cf_bypass = CloudflareBypass(
            cookie_file=self.config["cookie_file"],
            base_url="https://www.booksamillion.com",
            target_page="/"
        )

        # Create session from the CloudflareBypass
        self.session = self.cf_bypass.create_session()

        # Load or initialize product database
        self.products = self._load_products()

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

    def refresh_session(self):
        """Refresh the session with new cookies and headers"""
        # Get fresh cookies
        self.cf_bypass.get_fresh_cookies()

        # Create a new session with the fresh cookies
        self.session = self.cf_bypass.create_session()

        logger.info("Refreshed session with new cookies and headers")

    def check_stock(self, pid: str = None, proxy: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Check stock availability for a specific PID or all configured PIDs

        Args:
            pid: Product ID to check (optional)
            proxy: Optional proxy configuration

        Returns:
            List of dictionaries with product and stock information
        """
        results = []

        # If no PID is specified, check all configured PIDs
        if pid is None:
            logger.info("No PID specified, checking configured PIDs")

            # Check PIDs from configuration
            pids_to_check = self.pids

            # If no configured PIDs, extract from item URLs
            if not pids_to_check and self.item_urls:
                for url in self.item_urls:
                    # Extract PID from URL
                    pid_match = re.search(r'/([A-Za-z0-9]+)$', url)
                    if pid_match:
                        pids_to_check.append(pid_match.group(1))

            # If still no PIDs, check some from the product database
            if not pids_to_check and self.products:
                pids_to_check = list(self.products.keys())[:10]  # Limit to 10

            # Check each PID
            if pids_to_check:
                logger.info(f"Checking {len(pids_to_check)} PIDs")
                for pid_to_check in pids_to_check:
                    result = self._check_single_stock(pid_to_check, proxy)
                    results.append(result)
                    # Small delay between checks
                    time.sleep(random.uniform(1.0, 2.0))
            else:
                logger.warning("No PIDs configured to check")

        else:
            # Check the specified PID
            result = self._check_single_stock(pid, proxy)
            results.append(result)

        return results

    def _check_single_stock(self, pid: str, proxy: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Internal method to check stock for a single PID with detailed debugging

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

        # Create the product page URL for referer
        product_url = f"https://www.booksamillion.com/p/{pid}"

        # Log the URLs we're using
        logger.info(f"Bullseye URL: {bullseye_url}")
        logger.info(f"Product URL (referer): {product_url}")

        # Add the required headers based on successful request
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": product_url,
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-bitness": "64",
            "sec-ch-ua-arch": "x86",
            "sec-ch-ua-full-version": "135.0.7049.115",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "DNT": "1"
        }

        # Log the headers we're using
        logger.debug(f"Request headers: {headers}")

        # Attempt the request with retries and exponential backoff
        response = None
        max_retries = self.config["retry_attempts"]
        max_backoff = self.config["max_backoff_time"]

        for attempt in range(max_retries):
            try:
                # Enable detailed logging for this request
                try:
                    # Make the request with our enhanced bypass utility
                    response = self.cf_bypass.get(
                        bullseye_url,
                        headers=headers,
                        timeout=self.config["timeout"],
                        max_retries=2,  # Internal retries for Cloudflare issues
                        enable_logging=True  # Enable detailed request logging
                    )

                    # If we get a successful response, break the retry loop
                    if response.status_code == 200:
                        logger.info(f"Got successful response (HTTP 200) on attempt {attempt + 1}")
                        break
                    else:
                        logger.warning(f"Got HTTP {response.status_code} on attempt {attempt + 1}")

                except Exception as e:
                    logger.error(f"Cloudflare bypass request error: {str(e)}")
                    # If the Cloudflare bypass didn't handle the retry, we'll do it here
                    pass

                # If we get here, either the request failed or returned a non-200 status
                logger.warning(
                    f"Attempt {attempt + 1} failed: HTTP {response.status_code if response else 'No response'}")

                # Calculate backoff time with jitter, capped at max_backoff
                backoff_seconds = min(max_backoff, 1.5 * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                logger.info(f"Waiting {backoff_seconds:.2f} seconds before retry")
                time.sleep(backoff_seconds)

                # Refresh session for next attempt
                self.refresh_session()

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")

                # Log the failed request details
                self.request_logger.log_request(
                    url=bullseye_url,
                    method="GET",
                    headers=headers,
                    error=str(e)
                )

                # Calculate backoff time with jitter, capped at max_backoff
                backoff_seconds = min(max_backoff, 1.5 * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                logger.info(f"Waiting {backoff_seconds:.2f} seconds before retry")
                time.sleep(backoff_seconds)

                # Refresh session for next attempt
                self.refresh_session()

        # Check if we got a valid response
        if not response or response.status_code != 200:
            logger.error(f"Failed to check stock for {pid} after {max_retries} attempts")
            return result

        # Log response details
        logger.info(f"Response content type: {response.headers.get('Content-Type', 'unknown')}")
        logger.info(f"Response length: {len(response.text)} characters")

        if response and response.status_code == 200:
            # Log the complete HTTP transaction
            log_path = self.http_logger.log_transaction(
                request_url=bullseye_url,
                request_method="GET",
                request_headers=headers,
                response=response,
                pid=pid
            )
            logger.info(f"Complete HTTP transaction logged to {log_path}")

        # Always save the full response for debugging
        debug_dir = Path("logs/responses")
        debug_dir.mkdir(parents=True, exist_ok=True)
        response_file = debug_dir / f"{pid}_{int(time.time())}.html"

        try:
            with open(response_file, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"Saved full response to {response_file}")
        except Exception as e:
            logger.error(f"Failed to save response: {str(e)}")

        # Parse the response, handling different content types
        try:
            # First check the content type
            content_type = response.headers.get('Content-Type', '')

            # Look for JSON in the response regardless of content type
            # Try direct JSON parsing first
            try:
                stock_data = response.json()
                logger.info("Successfully parsed JSON response")
            except:
                # If direct parsing fails, try to extract JSON from the HTML
                logger.warning("Failed to parse as direct JSON, attempting to extract from HTML")

                # The successful response shows JSON at the bottom of the HTML
                # Look for a JSON object that starts with {"userinfo":
                json_match = re.search(r'({"userinfo":.*})', response.text)
                if json_match:
                    try:
                        json_text = json_match.group(1)
                        logger.info(f"Found potential JSON with userinfo in HTML response")
                        stock_data = json.loads(json_text)
                        logger.info("Successfully extracted JSON from HTML response")
                    except json.JSONDecodeError as e:
                        logger.error(f"Found potential JSON but couldn't parse it: {str(e)}")
                        return result
                else:
                    # If no match for userinfo, try to find any JSON object
                    logger.warning("No JSON with userinfo found, trying alternative patterns")

                    # Look for any object with pidinfo
                    json_match = re.search(r'({"pidinfo":.*})', response.text)
                    if json_match:
                        try:
                            json_text = json_match.group(1)
                            stock_data = json.loads(json_text)
                            logger.info("Found JSON with pidinfo")
                        except:
                            logger.error("Found potential JSON with pidinfo but couldn't parse it")
                            return result
                    else:
                        logger.error("Could not find any valid JSON in the response")
                        return result

            # Log the stock data structure
            logger.info(f"Stock data keys: {list(stock_data.keys())}")

            # Extract product details from pidinfo
            if 'pidinfo' in stock_data:
                result["title"] = stock_data['pidinfo'].get('title', '')
                result["price"] = stock_data['pidinfo'].get('retail_price', '')
                result["url"] = stock_data['pidinfo'].get('td_url', '')
                result["image"] = stock_data['pidinfo'].get('image_url', '')

                logger.info(f"Extracted product details: {result['title']} (${result['price']})")

            # Extract store availability from ResultList
            if 'ResultList' in stock_data:
                stores_count = len(stock_data['ResultList'])
                in_stock_count = 0

                for store in stock_data['ResultList']:
                    availability = store.get('Availability', '')
                    if availability.upper() == 'IN STOCK':
                        result["in_stock"] = True
                        in_stock_count += 1

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

                logger.info(f"Found {stores_count} stores, {in_stock_count} have stock")

            logger.info(f"Stock check for {pid} complete: {'IN STOCK' if result['in_stock'] else 'OUT OF STOCK'}")

            # Update product database with results
            self._update_product_db(result)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for {pid}: {str(e)}")
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

        new_pids = []

        # Process each search URL
        for url in self.search_urls:
            logger.info(f"Scanning URL: {url}")

            # Use the Cloudflare bypass utility for the request
            try:
                response = self.cf_bypass.get(
                    url,
                    timeout=self.config["timeout"],
                    max_retries=3
                )

                # Parse the HTML to find product PIDs
                if response.status_code == 200:
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
                        if pid not in self.products and pid not in self.pids:
                            logger.info(f"Found new PID: {pid}")
                            new_pids.append(pid)

                            # Add to the PIDs list
                            self.pids.append(pid)
                else:
                    logger.warning(f"Failed to scan URL {url}: HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"Error scanning URL {url}: {str(e)}")

            # Delay between requests to avoid rate limiting
            time.sleep(random.uniform(2.0, 4.0))

        # If new PIDs were found, update the PID list in the configuration
        if new_pids:
            try:
                update_pid_list("booksamillion", new_pids)
                logger.info(f"Updated PID list with {len(new_pids)} new PIDs")
            except Exception as e:
                logger.error(f"Error updating PID list: {str(e)}")

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
                result = self._check_single_stock(pid=pid, proxy=proxy)

                # Send notification for new product
                if notifier and result:
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
                result = self._check_single_stock(pid=pid, proxy=proxy)

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
                time.sleep(random.uniform(2.0, 4.0))

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
    bam = Booksamillion()

    # Test cookie generation
    bam.refresh_session()

    # Scan for items
    new_pids = bam.scan_new_items()
    print(f"Found {len(new_pids)} new PIDs")

    # Test stock check with a known PID
    test_pid = "F820650412493"  # Pokemon card
    if new_pids:
        test_pid = new_pids[0]

    result = bam.check_stock(test_pid)
    print(f"Stock check result for {test_pid}:")
    print(json.dumps(result, indent=2))