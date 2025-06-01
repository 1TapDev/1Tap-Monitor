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
import requests
import random
import base64  # Added for base64 decoding
import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from urllib.parse import urlparse  # Added for extracting file extensions
from dotenv import load_dotenv
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from notifier import DiscordNotifier

load_dotenv()
notifier = DiscordNotifier(webhook_url=os.getenv("DISCORD_WEBHOOK"))

# Add project root to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

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

# Reduce verbosity of other loggers
logging.getLogger("CloudflareBypass").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


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

        # Configure logging behavior - reduce verbosity
        self.cf_bypass.set_logging(
            enable_logging=self.config.get("debug", {}).get("log_requests", False),  # Changed to False
            save_readable=self.config.get("debug", {}).get("save_html", False)
        )

        # Set CloudflareBypass logger to WARNING level to reduce noise
        cf_logger = logging.getLogger("CloudflareBypass")
        cf_logger.setLevel(logging.WARNING)
        self.cf_bypass.aggressive_mode = True

        # Create session
        self.session = self.cf_bypass.create_session()

        # Load product data
        self.products = self._load_products()

        # Track last stock check time for each product
        self.last_check = {}

        # Store information about stock changes
        self.stock_changes = {}

        # Track products that have already been notified
        self.notified_products = set()

        # Load previously notified products
        self._load_notified_products()

        logger.info(f"Initialized {self.NAME} module v{self.VERSION}")
        logger.info(f"Loaded {len(self.products)} products from cache")
        logger.info(
            f"Configured for zip code {self.config.get('target_zipcode')} with radius {self.config.get('search_radius')}mi")

    def _load_config(self):
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
                "webhook": {
                    "url": "",
                    "image_cache_url": "",  # New field for image caching webhook
                    "placeholder_image": "https://cdn.discordapp.com/attachments/123456789/123456789/pokemon_card_placeholder.png",
                    # Default placeholder
                    "pokemon_placeholders": [
                        "https://cdn.discordapp.com/attachments/123456789/123456789/charizard.png",
                        "https://cdn.discordapp.com/attachments/123456789/123456789/pikachu.png",
                        "https://cdn.discordapp.com/attachments/123456789/123456789/eevee.png",
                        "https://cdn.discordapp.com/attachments/123456789/123456789/bulbasaur.png",
                        "https://cdn.discordapp.com/attachments/123456789/123456789/squirtle.png"
                    ]
                },
                "debug": {
                    "log_requests": False,
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

    def _load_products(self):
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

    def _save_notified_products(self):
        """Save notified products to prevent duplicate notifications"""
        try:
            with open("data/booksamillion_notified.json", 'w') as f:
                json.dump(list(self.notified_products), f)
            logger.debug(f"Saved {len(self.notified_products)} notified product IDs")
        except Exception as e:
            logger.error(f"Error saving notified products: {str(e)}")

    def _load_notified_products(self):
        """Load notified products to prevent duplicate notifications"""
        try:
            if os.path.exists("data/booksamillion_notified.json"):
                with open("data/booksamillion_notified.json", 'r') as f:
                    self.notified_products = set(json.load(f))
                logger.debug(f"Loaded {len(self.notified_products)} notified product IDs")

                # Clean up old notification records (older than 30 days)
                self._cleanup_old_notifications()
        except Exception as e:
            logger.error(f"Error loading notified products: {str(e)}")
            self.notified_products = set()

    def _cleanup_old_notifications(self):
        """Remove notification records older than 30 days to prevent file bloat"""
        try:
            current_date = datetime.datetime.now()
            cutoff_date = current_date - datetime.timedelta(days=30)

            initial_count = len(self.notified_products)
            cleaned_products = set()

            for notification_key in self.notified_products:
                try:
                    # Extract date from notification key (format: "PID:YYYY-MM-DD")
                    if ":" in notification_key:
                        date_str = notification_key.split(":", 1)[1]
                        notification_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')

                        # Keep notifications newer than cutoff date
                        if notification_date >= cutoff_date:
                            cleaned_products.add(notification_key)
                except (ValueError, IndexError):
                    # Keep malformed entries (shouldn't happen but be safe)
                    cleaned_products.add(notification_key)

            removed_count = initial_count - len(cleaned_products)
            if removed_count > 0:
                self.notified_products = cleaned_products
                self._save_notified_products()
                logger.info(f"Cleaned up {removed_count} old notification records (older than 30 days)")

        except Exception as e:
            logger.error(f"Error cleaning up old notifications: {str(e)}")

    def _is_product_new(self, pid):
        """
        Check if a product is truly new (not in database and not previously notified)

        Args:
            pid: Product ID

        Returns:
            bool: True if product is new, False otherwise
        """
        # Check if product exists in database
        if pid in self.products:
            logger.debug(f"Product {pid} already exists in database")
            return False

        # Check if product was already notified (any time, not just today)
        for notified_key in self.notified_products:
            if notified_key.startswith(f"{pid}:"):
                logger.debug(f"Product {pid} was already notified previously")
                return False

        return True

    def _should_send_notification(self, pid, notification_type="stock_change"):
        """
        Determine if a notification should be sent for a product
        """
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')

        if notification_type == "new_item":
            # For new items, check if it's truly new
            if not self._is_product_new(pid):
                return False

        # Check if already notified today
        today_key = f"{pid}:{current_date}"
        if today_key in self.notified_products:
            logger.debug(f"Product {pid} already notified today")
            return False

        return True

    def upload_image_to_discord(self, pid, image_url):
        """
        Upload product image to Discord using webhook and return the CDN URL.

        Args:
            pid: Product ID
            image_url: Original image URL

        Returns:
            Discord CDN URL if successful, None otherwise
        """
        if not pid or not image_url:
            logger.warning(f"Missing pid or image_url, skipping Discord image upload for PID: {pid}")
            return self._get_placeholder_image()

        webhook_url = self.config.get("webhook", {}).get("image_cache_url", "")
        if not webhook_url:
            webhook_url = os.getenv('DISCORD_IMAGE_WEBHOOK', "")

        if not webhook_url:
            logger.warning("No webhook image cache URL configured, skipping Discord image upload")
            return self._get_placeholder_image()

        try:
            # Check if this is a data URL (base64 embedded image)
            if "data:image" in image_url:
                # Handle malformed URLs where base URL is prepended to data URL
                if image_url.startswith("https://www.booksamillion.comdata:image"):
                    image_url = image_url.replace("https://www.booksamillion.comdata:image", "data:image")

                # Extract base64 data
                try:
                    # Parse the data URL
                    header, encoded = image_url.split(",", 1)
                    content_type = header.split(":")[1].split(";")[0]

                    # Create placeholder image name based on content type
                    extension = f".{content_type.split('/')[1]}"
                    if extension == ".jpeg":
                        extension = ".jpg"

                    # Decode base64 content
                    image_content = base64.b64decode(encoded)

                    # Check for tiny placeholder images or invalid content
                    if len(image_content) < 1000:  # Increased threshold
                        logger.warning(f"Image for {pid} is too small ({len(image_content)} bytes), using placeholder")
                        return self._get_pokemon_card_placeholder(pid)

                    # Check if image is valid by attempting to validate it
                    if not self._is_valid_image(image_content):
                        logger.warning(f"Image for {pid} failed validation, using placeholder")
                        return self._get_pokemon_card_placeholder(pid)

                    filename = f"{pid}{extension}"
                except Exception as e:
                    logger.error(f"Failed to decode data URL for {pid}: {str(e)}")
                    return self._get_placeholder_image()
            else:
                # Download the image
                logger.info(f"Downloading image for {pid} from {image_url}")

                # Create browser-like headers
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.booksamillion.com/p/" + pid,
                    "Sec-Fetch-Dest": "image",
                    "Sec-Fetch-Mode": "no-cors",
                    "Sec-Fetch-Site": "same-site",
                }

                try:
                    # Always use the CloudflareBypass for image downloads
                    # This is critical for covers.booksamillion.com which is protected
                    if not hasattr(self, 'cf_bypass') or not self.cf_bypass:
                        logger.error(f"CloudflareBypass not initialized, falling back to placeholder for {pid}")
                        return self._get_pokemon_card_placeholder(pid)

                    # Try to download using CloudflareBypass
                    image_response = self.cf_bypass.get(
                        image_url,
                        headers=headers,
                        timeout=self.config.get("timeout", 30),
                        enable_logging=True
                    )

                    if image_response.status_code != 200:
                        logger.error(f"Failed to download image for {pid}: HTTP {image_response.status_code}")
                        return self._get_pokemon_card_placeholder(pid)

                    # Prepare the image for upload
                    image_content = image_response.content

                    # Check for tiny placeholder images or invalid content
                    if len(image_content) < 1000:  # Increased threshold
                        logger.warning(f"Image for {pid} is too small ({len(image_content)} bytes), using placeholder")
                        return self._get_pokemon_card_placeholder(pid)

                    # Check if image is valid by attempting to validate it
                    if not self._is_valid_image(image_content):
                        logger.warning(f"Image for {pid} failed validation, using placeholder")
                        return self._get_pokemon_card_placeholder(pid)

                    file_extension = self._get_file_extension(image_url)
                    filename = f"{pid}{file_extension}"
                except Exception as e:
                    logger.error(f"Error downloading image for {pid}: {str(e)}")
                    return self._get_pokemon_card_placeholder(pid)

            # Final validation before upload
            if not self._is_valid_image(image_content):
                logger.warning(f"Final validation failed for {pid}, using placeholder")
                return self._get_pokemon_card_placeholder(pid)

            # Upload to Discord
            logger.info(f"Uploading image for {pid} to Discord CDN")
            files = {"file": (filename, image_content)}
            response = requests.post(webhook_url, files=files, timeout=30)

            if response.status_code != 200:
                logger.error(f"Failed to upload image to Discord: HTTP {response.status_code}")
                return self._get_pokemon_card_placeholder(pid)

            # Extract the CDN URL
            try:
                data = response.json()
                cdn_url = data["attachments"][0]["url"]
                logger.info(f"Successfully uploaded image for {pid} to Discord CDN: {cdn_url}")
                return cdn_url
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"Error extracting CDN URL from Discord response: {str(e)}")
                return self._get_pokemon_card_placeholder(pid)

        except Exception as e:
            logger.error(f"Error uploading image to Discord for {pid}: {str(e)}")
            return self._get_pokemon_card_placeholder(pid)

    def _get_placeholder_image(self):
        """Return a generic placeholder image URL from Discord CDN or a default one"""
        # Check if we have a cached placeholder image in config
        placeholder_url = self.config.get("webhook", {}).get("placeholder_image", "")
        if placeholder_url and placeholder_url.startswith("https://cdn.discordapp.com/"):
            return placeholder_url

        # Default placeholder if none configured
        return "https://cdn.discordapp.com/attachments/123456789/123456789/pokemon_card_placeholder.png"

    def _get_pokemon_card_placeholder(self, pid):
        """
        Return a Pokemon card placeholder image based on the product ID.
        This creates consistent but different images for different products.
        """
        # Check if we have a set of cached Pokemon card placeholder images
        pokemon_placeholders = self.config.get("webhook", {}).get("pokemon_placeholders", [])

        if pokemon_placeholders and isinstance(pokemon_placeholders, list) and len(pokemon_placeholders) > 0:
            # Choose a placeholder based on the PID hash to make it consistent
            hash_value = sum(ord(c) for c in pid) % len(pokemon_placeholders)
            return pokemon_placeholders[hash_value]

        # If no Pokemon placeholders configured, use default placeholder
        return self._get_placeholder_image()

    def _get_file_extension(self, url):
        """Extract file extension from URL"""
        # Handle data URLs
        if url.startswith("data:image/"):
            # Extract mime type and map to extension
            mime_type = url.split(";")[0].split("/")[1]
            if mime_type == "jpeg":
                return ".jpg"
            elif mime_type == "svg+xml":
                return ".svg"
            else:
                return f".{mime_type}"

        # Try to get the file extension from the URL
        parsed_url = urlparse(url)
        path = parsed_url.path
        _, ext = os.path.splitext(path)

        # If no extension found, try to guess from the last path component
        if not ext and "/" in path:
            last_part = path.split("/")[-1]
            if "." in last_part:
                ext = "." + last_part.split(".")[-1]

        # If still no extension or not a valid image extension, default to .jpg
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']
        if not ext or ext.lower() not in valid_extensions:
            return ".jpg"

        return ext.lower()

    def download_product_image(self, pid, image_url, max_retries=5):
        """
        Download a product image with multiple retries and validation

        Args:
            pid: Product ID
            image_url: Image URL to download
            max_retries: Maximum number of retry attempts

        Returns:
            Tuple of (image_content, success_flag)
        """
        if not image_url or not pid:
            return None, False

        # Skip data URLs
        if image_url.startswith("data:image"):
            return None, False

        logger.info(f"Downloading image for {pid} from {image_url}")

        # Various User-Agent strings to try
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ]

        for attempt in range(max_retries):
            try:
                # Try a different User-Agent for each attempt
                user_agent = user_agents[attempt % len(user_agents)]

                # Create browser-like headers
                headers = {
                    "User-Agent": user_agent,
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": f"https://www.booksamillion.com/p/{pid}",
                    "Origin": "https://www.booksamillion.com",
                    "Sec-Fetch-Dest": "image",
                    "Sec-Fetch-Mode": "no-cors",
                    "Sec-Fetch-Site": "same-site",
                    "Connection": "keep-alive",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                }

                logger.debug(f"Attempt {attempt + 1}/{max_retries} for {pid} image download")

                # Try direct requests first - often works better for images
                if attempt < 2:
                    try:
                        session = requests.Session()
                        image_response = session.get(
                            image_url,
                            headers=headers,
                            timeout=self.config.get("timeout", 30)
                        )
                        if image_response.status_code == 200 and len(image_response.content) > 1000:
                            # Validate image
                            if self._is_valid_image(image_response.content):
                                return image_response.content, True
                    except Exception as e:
                        logger.debug(f"Direct request failed for {pid}: {str(e)}")

                # Try CloudflareBypass
                image_response = self.cf_bypass.get(
                    image_url,
                    headers=headers,
                    timeout=self.config.get("timeout", 30),
                    enable_logging=True
                )

                if image_response.status_code != 200:
                    logger.warning(
                        f"Failed to download image for {pid}: HTTP {image_response.status_code} (attempt {attempt + 1})")
                    time.sleep(1 + attempt)  # Increase delay with each attempt
                    continue

                image_content = image_response.content

                # Check for valid, non-tiny image
                if len(image_content) < 1000:
                    logger.warning(f"Image for {pid} is too small ({len(image_content)} bytes), retrying...")
                    time.sleep(1 + attempt)
                    continue

                # Validate image
                if not self._is_valid_image(image_content):
                    logger.warning(f"Image for {pid} is not valid, retrying...")
                    time.sleep(1 + attempt)
                    continue

                return image_content, True

            except Exception as e:
                logger.warning(f"Error downloading image for {pid} (attempt {attempt + 1}): {str(e)}")
                time.sleep(1 + attempt)

        # If we get here, all attempts failed
        logger.error(f"All attempts to download image for {pid} failed")
        return None, False

    def _is_valid_image(self, image_data):
        """Check if the data is a valid image file"""
        if not image_data or len(image_data) < 1000:
            return False

        try:
            import io
            from PIL import Image

            # Create a copy of the data for verification
            img_copy = io.BytesIO(image_data)
            img = Image.open(img_copy)

            # Get image properties
            width, height = img.size
            mode = img.mode

            # Check if it's a reasonable size (not 1x1 pixel placeholder)
            if width < 50 or height < 50:
                logger.debug(f"Image too small: {width}x{height}")
                return False

            # Check if it's not a solid color (common for placeholder images)
            img_copy.seek(0)  # Reset stream position
            img_sample = Image.open(img_copy)
            img_sample = img_sample.convert('RGB')

            # Sample a few pixels to check for variation
            colors = []
            step = max(1, min(width, height) // 10)
            for x in range(0, min(width, 100), step):
                for y in range(0, min(height, 100), step):
                    try:
                        colors.append(img_sample.getpixel((x, y)))
                        if len(colors) >= 10:  # Sample enough pixels
                            break
                    except:
                        continue
                if len(colors) >= 10:
                    break

            # Check if all sampled pixels are the same (solid color = likely placeholder)
            if len(set(colors)) < 2:
                logger.debug("Image appears to be solid color (placeholder)")
                return False

            return True

        except Exception as e:
            logger.debug(f"Image validation failed: {str(e)}")
            return False

    def get_store_stock_qty(self, pid):
        """
        Get real-time stock quantity for a product at a specific store

        Args:
            pid: Product ID

        Returns:
            int: Stock quantity if available, None otherwise
        """
        try:
            # Build the payload for the request
            payload = f"https%3A%2F%2Fwww.booksamillion.com%2Fcart%3Faction=add&buyit={pid}&action=add_to_modal_cart"

            # Set headers for the request
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"https://www.booksamillion.com/p/{pid}",
                "X-Requested-With": "XMLHttpRequest",
            }

            # Make the POST request
            response = self.cf_bypass.post(
                "https://www.booksamillion.com/add_to_modal_cart",
                data=payload,
                headers=headers,
                timeout=self.config.get("timeout", 30)
            )

            # Check if the request was successful
            if response.status_code == 200:
                # Parse the JSON response
                try:
                    data = response.json()
                    # Extract the storeOnhand value
                    stock_qty = data.get("storeOnhand")
                    if stock_qty is not None:
                        return int(stock_qty)
                except (json.JSONDecodeError, ValueError):
                    logger.error(f"Failed to parse storeOnhand from response: {response.text}")

            return None
        except Exception as e:
            logger.error(f"Error getting stock quantity for {pid}: {str(e)}")
            return None

    def check_stock(self, pid=None, proxy=None):
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

    def _emoji_for_status(self, status):
        status = (status or "").upper()
        if status == "IN STOCK":
            return "🟢"
        elif status == "LIMITED STOCK":
            return "🟡"
        elif status == "OUT OF STOCK":
            return "🔴"
        return "⚫"

    def _check_single_stock(self, pid, proxy=None):
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
            "check_time": datetime.datetime.now().isoformat()
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

                # Try to upload the image to Discord CDN if it's not already cached
                if result["image"] and not self.products.get(pid, {}).get("cdn_image"):
                    cdn_image = self.upload_image_to_discord(pid, result["image"])
                    if cdn_image:
                        result["cdn_image"] = cdn_image
                elif pid in self.products and self.products[pid].get("cdn_image"):
                    # Use existing cached CDN image
                    result["cdn_image"] = self.products[pid].get("cdn_image")

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
                            "availability": availability,
                        }

                        # Always get real-time stock quantity for in-stock items
                        stock_qty = self.get_store_stock_qty(pid)
                        if stock_qty is not None:
                            store_info["stock_qty"] = stock_qty
                        else:
                            # Fallback to mmoh if available (in-store stock quantity)
                            mmoh = store.get('mmoh')
                            if mmoh is not None:
                                store_info["stock_qty"] = int(mmoh)

                        result["stores"].append(store_info)

                logger.info(f"Found {in_stock_count} of {stores_count} stores with stock for {pid}")

            # Update product information and collect store changes (but don't send notifications immediately)
            _ = self._update_product(result)

            return result

        except Exception as e:
            logger.error(f"Error processing response for {pid}: {str(e)}")
            return result

    def _update_product(self, result):
        pid = result["pid"]
        current_time = datetime.datetime.now().isoformat()
        previous_product = self.products.get(pid, {})

        # Get previous stores data to detect changes
        previous_stores = {}
        for s in previous_product.get("stores", []):
            store_id = s.get("store_id")
            if store_id:
                previous_stores[store_id] = {
                    "availability": s.get("availability", ""),
                    "stock_qty": s.get("stock_qty")
                }

        stores_with_changes = []

        for store in result.get("stores", []):
            store_id = store.get("store_id")
            if not store_id:
                continue

            prev_data = previous_stores.get(store_id, {})
            prev_availability = prev_data.get("availability", "")
            prev_stock_qty = prev_data.get("stock_qty")

            curr_availability = store.get("availability", "").upper()
            curr_stock_qty = store.get("stock_qty")

            # Detect changes in availability or stock quantity
            if curr_availability != prev_availability or curr_stock_qty != prev_stock_qty:
                # Determine the event type
                event_type = "new_item"
                if prev_availability:
                    if curr_availability in ['IN STOCK', 'LIMITED STOCK'] and prev_availability not in ['IN STOCK',
                                                                                                        'LIMITED STOCK']:
                        event_type = "restocked"
                    elif curr_availability not in ['IN STOCK', 'LIMITED STOCK'] and prev_availability in ['IN STOCK',
                                                                                                          'LIMITED STOCK']:
                        event_type = "oos"
                    elif curr_stock_qty is not None and prev_stock_qty is not None and curr_stock_qty != prev_stock_qty:
                        event_type = "restocked"  # Use restocked event type for quantity changes

                # Create status change string with emojis
                prev_emoji = self._emoji_for_status(prev_availability)
                curr_emoji = self._emoji_for_status(curr_availability)
                status_change = f"{prev_emoji} → {curr_emoji}"

                # Add store to the list of changed stores
                store["event_type"] = event_type
                store["status_change"] = status_change
                store["previous_availability"] = prev_availability
                store["previous_stock_qty"] = prev_stock_qty
                store["last_restocks"] = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

                stores_with_changes.append(store)

        # Check if we need to upload the image to Discord
        if result.get("image") and not previous_product.get("cdn_image"):
            cdn_image = self.upload_image_to_discord(pid, result["image"])
            if cdn_image:
                result["cdn_image"] = cdn_image
        elif previous_product.get("cdn_image"):
            # Keep existing CDN image if available
            result["cdn_image"] = previous_product.get("cdn_image")

        # Update product data
        self.products[pid] = {
            "pid": pid,
            "title": result["title"] or previous_product.get("title", ""),
            "price": result["price"] or previous_product.get("price", ""),
            "url": result["url"] or previous_product.get("url", ""),
            "image": result["image"] or previous_product.get("image", ""),
            "cdn_image": result.get("cdn_image") or previous_product.get("cdn_image", ""),
            "in_stock": result["in_stock"],
            "first_seen": previous_product.get("first_seen", current_time),
            "last_check": current_time,
            "last_in_stock": current_time if result["in_stock"] else previous_product.get("last_in_stock"),
            "last_out_of_stock": current_time if not result["in_stock"] else previous_product.get("last_out_of_stock"),
            "stores": result["stores"]
        }

        # If there are stores with changes, add to stock_changes for later notification
        if stores_with_changes:
            # Create a copy of the result with only the changed stores
            change_result = result.copy()
            change_result["stores"] = stores_with_changes

            # Add to stock_changes dictionary for later notification
            if pid not in self.stock_changes:
                self.stock_changes[pid] = change_result
            else:
                # Append new store changes to existing changes
                self.stock_changes[pid]["stores"].extend(stores_with_changes)

                # Send immediate notification for in-stock items
                if result["in_stock"]:
                    # For newly discovered products that are in stock, treat all stores as "changes"
                    notification_stores = stores_with_changes if stores_with_changes else result.get("stores", [])

                    if notification_stores:
                        print(
                            f"[DEBUG] Triggering Discord alert for {result['title']} - {len(notification_stores)} stores")
                        try:
                            success = notifier.send_alert(
                                title=f"{result['title']} is in stock!",
                                description=f"{len(notification_stores)} stores have it available.",
                                url=result.get("url", ""),
                                image=result.get("cdn_image", result.get("image", "")),
                                store="Books-A-Million"
                            )
                            print(f"[DEBUG] Notification sent: {success}")
                        except Exception as e:
                            print(f"[DEBUG] Notification failed: {e}")

        return stores_with_changes

    def scan_new_items(self, proxy=None):
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

                    # Skip if no PID
                    if not pid:
                        continue

                    # Use the enhanced check to see if this is truly a new product
                    if not self._is_product_new(pid):
                        logger.debug(f"Skipping product {pid} - already exists in database or was previously notified")
                        continue

                    logger.info(f"Found NEW product: {product.get('title')} (PID: {pid})")

                    # Try to upload the image to Discord CDN if available
                    if product.get("image"):
                        cdn_image = self.upload_image_to_discord(pid, product["image"])
                        if cdn_image:
                            product["cdn_image"] = cdn_image

                    # Add to the products dictionary
                    current_time = datetime.datetime.now().isoformat()
                    self.products[pid] = {
                        "pid": pid,
                        "title": product.get("title", ""),
                        "price": product.get("price", ""),
                        "url": product.get("url", ""),
                        "image": product.get("image", ""),
                        "cdn_image": product.get("cdn_image", ""),
                        "in_stock": False,  # Will be updated after stock check
                        "first_seen": current_time,
                        "last_check": current_time
                    }

                    # Add to new products list
                    new_products.append(product)

            except Exception as e:
                logger.error(f"Error scanning URL {url}: {str(e)}")

        logger.info(f"Found {len(new_products)} truly new products")

        # Save updated product data
        if new_products:
            self._save_products()

        # Check stock for new products
        for product in new_products:
            try:
                # Add small delay between checks
                time.sleep(random.uniform(1.0, 2.0))

                # Check stock
                result = self._check_single_stock(product["pid"], proxy)

                # Make sure the cdn_image field is preserved
                if product.get("cdn_image") and not result.get("cdn_image"):
                    result["cdn_image"] = product["cdn_image"]
                    # Update product in cache
                    self.products[product["pid"]]["cdn_image"] = product["cdn_image"]
                    self._save_products()

            except Exception as e:
                logger.error(f"Error checking stock for new product {product.get('pid')}: {str(e)}")

        # Return new + updated in-stock products
        return [self.products[prod["pid"]] for prod in new_products]

    def _extract_products_from_html(self, html, base_url):
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
                if image:
                    if image.startswith('data:image'):
                        # No changes needed for data URLs
                        pass
                    elif not image.startswith(('http://', 'https://')):
                        image = f"https://www.booksamillion.com{image}" if not image.startswith(
                            '/') else f"https://www.booksamillion.com{image}"
                    # Fix malformed URLs where base URL is incorrectly prepended to data URL
                    elif "data:image" in image and image.startswith("https://www.booksamillion.comdata:image"):
                        image = image.replace("https://www.booksamillion.comdata:image", "data:image")

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

    def build_embed(self, product, store, event_type):
        """
        Build a Discord embed for a product stock event
        """
        # Extract product details
        pid = product.get("pid", "")
        price = product.get("price", "")

        # Format price with $ if needed
        if price:
            price_str = str(price)
            if not price_str.startswith("$"):
                price = "$" + price_str

        title = product.get("title", "")
        url = product.get("url", "")

        # Prioritize using Discord CDN image if available, fall back to original image
        image = product.get("cdn_image", product.get("image", ""))

        # Extract store details
        store_name = store.get("name", "") or store.get("city", "")
        store_phone = store.get("phone", "")
        address = store.get("address", "")
        city = store.get("city", "")
        state = store.get("state", "")
        zip_code = store.get("zip", "")

        # Format stock quantity
        curr_stock_qty = store.get("stock_qty", 0)
        prev_stock_qty = store.get("previous_stock_qty", 0)

        # Format store address for code block
        formatted_address = f"{address}\n{city}, {state} {zip_code}"

        # Get current timestamp
        now = datetime.datetime.now()
        timestamp = store.get("last_restocks", now.strftime("%B %d, %Y at %I:%M %p"))
        time_footer = now.strftime("%m-%d-%Y %H:%M")  # Changed to MM-DD-YYYY HH:MM format

        # Build fields based on event type
        fields = []

        # SKU/Price fields are common to all event types
        fields.extend([
            {
                "name": "**SKU**:",
                "value": pid,
                "inline": True
            },
            {
                "name": "‎",  # Invisible character for spacing
                "value": "‎",
                "inline": True
            },
            {
                "name": "**Price**:",
                "value": price,
                "inline": True
            }
        ])

        # Store Name/Phone fields are common to all event types
        fields.extend([
            {
                "name": "**Store Name**:",
                "value": store_name,
                "inline": True
            },
            {
                "name": "‎",  # Invisible character for spacing
                "value": "‎",
                "inline": True
            },
            {
                "name": "**Store Phone**:",
                "value": store_phone,
                "inline": True
            }
        ])

        # Stock quantity field depends on event type
        if event_type == "new_item":
            fields.append({
                "name": "**Stock**:",
                "value": str(curr_stock_qty) if curr_stock_qty is not None else "0"
            })
            fields.append({
                "name": "**Added**",
                "value": timestamp
            })
        elif event_type == "restocked":
            stock_change = f"{prev_stock_qty if prev_stock_qty is not None else 0} → {curr_stock_qty if curr_stock_qty is not None else 0}"
            fields.append({
                "name": "**Stock**:",
                "value": stock_change
            })
            fields.append({
                "name": f"**Last Restock** {store.get('status_change', '🟡 → 🟢')}",
                "value": timestamp
            })
        elif event_type == "oos":
            stock_change = f"{prev_stock_qty if prev_stock_qty is not None else 1} → 0"
            fields.append({
                "name": "**Stock**:",
                "value": stock_change
            })
            fields.append({
                "name": "🔴 **Item Removed**",
                "value": timestamp
            })

        # Store address field is common to all event types
        fields.append({
            "name": "**Store Address**",
            "value": f"```{formatted_address}```"
        })

        # Set author name based on event type
        if event_type == "new_item":
            author_name = "New Item"
        elif event_type == "restocked":
            author_name = "Item Restocked"
        elif event_type == "oos":
            author_name = "🔴 Item OOS"
        else:
            author_name = "Stock Update"

        # Build the embed
        embed = {
            "title": title,
            "url": url,
            "color": 5814783,  # Blue color
            "fields": fields,
            "author": {
                "name": author_name,
                "icon_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQpTHIIj4Pq9DHaXJFruRF128hHOXsb6btFrg&so"
            },
            "footer": {
                "text": f"1Tap Monitors • Books a million • {time_footer}"
            },
            "timestamp": now.isoformat(),
            "thumbnail": {
                "url": "https://imgur.com/r4NlONt.png"
            }
        }

        # Only add image if it's valid
        if image and len(image) > 10:
            embed["image"] = {
                "url": image
            }

        return embed

    def format_discord_message(self, product, is_new=False):
        """
        Format product information for Discord webhook

        Args:
            product: Product information
            is_new: Whether this is a new product notification

        Returns:
            Formatted Discord message with embeds
        """
        # Get stores from the product
        stores = product.get("stores", [])
        embeds = []

        # Deduplicate stores by store_id if multiple exist with the same ID
        unique_stores = {}
        for store in stores:
            store_id = store.get("store_id")
            if store_id:
                # If this store already exists, only keep the one with the higher stock
                if store_id in unique_stores:
                    existing_stock = unique_stores[store_id].get("stock_qty", 0) or 0
                    new_stock = store.get("stock_qty", 0) or 0
                    if new_stock > existing_stock:
                        unique_stores[store_id] = store
                else:
                    unique_stores[store_id] = store
            else:
                # If no store_id, just add it (this should be rare)
                unique_stores[f"unknown_{len(unique_stores)}"] = store

        # Use the deduplicated stores
        deduplicated_stores = list(unique_stores.values())

        if deduplicated_stores:
            for store in deduplicated_stores:
                # Determine event type
                event_type = store.get("event_type", "restocked")
                if is_new:
                    event_type = "new_item"

                # Get real-time stock quantity for in-stock items if not already set
                if event_type != "oos" and "stock_qty" not in store:
                    stock_qty = self.get_store_stock_qty(product["pid"])
                    if stock_qty is not None:
                        store["stock_qty"] = stock_qty
                    else:
                        # Fallback to mmoh value if available
                        mmoh = store.get('mmoh', 0)
                        if mmoh:
                            store["stock_qty"] = int(mmoh)

                # Build embed for this store
                embed = self.build_embed(product, store, event_type)
                embeds.append(embed)
        else:
            # Handle out of stock products with no stores
            event_type = "oos"
            store = {
                "name": "Unknown",
                "phone": "",
                "address": "",
                "city": "",
                "state": "",
                "zip": "",
                "previous_stock_qty": 1,
                "stock_qty": 0,
                "status_change": "🟢 → 🔴",
                "last_restocks": datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
            }
            embed = self.build_embed(product, store, event_type)
            embeds.append(embed)

        return {
            "username": "1Tap Monitors",
            "avatar_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQpTHIIj4Pq9DHaXJFruRF128hHOXsb6btFrg&s",
            "embeds": embeds
        }

    def send_discord_notification(self, product, is_new=False):
        """Send Discord notification for product"""
        pid = product.get("pid")

        # Use the enhanced notification check
        notification_type = "new_item" if is_new else "stock_change"
        if not self._should_send_notification(pid, notification_type):
            logger.info(f"Skipping notification for {pid} - duplicate prevention triggered")
            return False

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

        # Limit embeds to max 10 (Discord limit)
        if len(message.get("embeds", [])) > 10:
            logger.warning(f"Too many embeds ({len(message.get('embeds', []))}), limiting to 10")
            message["embeds"] = message["embeds"][:10]

        try:
            # Send webhook
            response = requests.post(
                webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.json().get('retry_after', 1)
                logger.warning(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after + 0.1)  # Add small buffer
                # Retry once
                response = requests.post(
                    webhook_url,
                    json=message,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )

            if response.status_code == 204:
                logger.info(f"Discord notification sent for {product.get('pid')}")
                # Mark this product as notified
                product_store_key = f"{pid}:{datetime.datetime.now().strftime('%Y-%m-%d')}"
                self.notified_products.add(product_store_key)
                self._save_notified_products()
                return True
            else:
                logger.error(f"Discord notification failed with status {response.status_code}: {response.text}")

                # If too many embeds, try with fewer
                if response.status_code == 400 and len(message.get("embeds", [])) > 1:
                    logger.warning("Trying with fewer embeds")
                    message["embeds"] = message["embeds"][:1]
                    retry_response = requests.post(
                        webhook_url,
                        json=message,
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    )
                    if retry_response.status_code == 204:
                        logger.info(f"Discord notification sent with limited embeds for {product.get('pid')}")
                        # Mark this product as notified
                        product_store_key = f"{pid}:{datetime.datetime.now().strftime('%Y-%m-%d')}"
                        self.notified_products.add(product_store_key)
                        self._save_notified_products()
                        return True

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

        # Load list of already notified products
        self._load_notified_products()

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

            # Step 2: Send notifications for new products (only truly new ones)
            for product in new_products:
                product_id = product.get('pid')
                if product_id:
                    # Check if this should be notified as a new item
                    if self._should_send_notification(product_id, "new_item"):
                        logger.info(f"Sending NEW ITEM notification for {product_id}")

                        if notifier:
                            notifier.send_alert(
                                title=f"New Pokemon Product: {product.get('title', 'Unknown')}",
                                description=f"A new Pokemon product has been found on Books-A-Million.\nPrice: ${product.get('price', 'Unknown')}\nSKU: {product.get('pid', 'Unknown')}",
                                url=product.get('url', ''),
                                image=product.get('cdn_image', product.get('image', '')),
                                store=self.NAME
                            )
                        else:
                            # Use internal Discord notification
                            self.send_discord_notification(product, is_new=True)
                    else:
                        logger.info(
                            f"Skipping new item notification for {product_id} - already exists or previously notified")

            # Step 3: Check stock for existing products
            results = self.check_stock(proxy=proxy)

            # Step 4: Send notifications for stock changes (only for valid changes)
            for pid, change_info in self.stock_changes.items():
                logger.info(f"Processing stock change for {pid}")

                # Check if this stock change should be notified
                if self._should_send_notification(pid, "stock_change"):
                    logger.info(f"Sending STOCK CHANGE notification for {pid}")

                    # Make sure to send to both notifier and webhook
                    # First try the notifier module if available
                    if notifier:
                        if change_info.get('in_stock', False):
                            notifier.send_alert(
                                title=f"🟢 NOW IN STOCK: {change_info.get('title', 'Unknown')}",
                                description=f"This Pokemon product is now IN STOCK at Books-A-Million!\nPrice: ${change_info.get('price', 'Unknown')}\nAvailable at {len(change_info.get('stores', []))} stores",
                                url=change_info.get('url', ''),
                                image=change_info.get('cdn_image', change_info.get('image', '')),
                                store=self.NAME
                            )
                        else:
                            notifier.send_alert(
                                title=f"🔴 OUT OF STOCK: {change_info.get('title', 'Unknown')}",
                                description=f"This Pokemon product is now OUT OF STOCK at Books-A-Million\nPrice: ${change_info.get('price', 'Unknown')}",
                                url=change_info.get('url', ''),
                                image=change_info.get('cdn_image', change_info.get('image', '')),
                                store=self.NAME
                            )

                    # Always send through the internal webhook too as a backup
                    success = self.send_discord_notification(change_info)
                    if success:
                        logger.info(f"Successfully sent Discord notification for {pid}")
                    else:
                        logger.error(f"Failed to send Discord notification for {pid}")
                else:
                    logger.info(f"Skipping stock change notification for {pid} - already notified today")

            # Clear stock changes after notifications
            self.stock_changes = {}

            logger.info("Main monitor loop completed successfully")

        except Exception as e:
            logger.error(f"Error in main monitor loop: {str(e)}")

    def send_new_product_notifications(self, new_products):
        """
        Send notifications for newly found products

        Args:
            new_products: List of new product dictionaries
        """
        for i, product in enumerate(new_products):
            product_id = product.get('pid')
            if product_id and self._should_send_notification(product_id, "new_item"):
                logger.info(f"Sending notification for new product: {product_id}")
                success = self.send_discord_notification(product, is_new=True)
                if success:
                    logger.info(f"Successfully sent notification for new product: {product_id}")
                else:
                    logger.error(f"Failed to send notification for new product: {product_id}")

                # Add delay between notifications (except for the last one)
                if i < len(new_products) - 1:
                    time.sleep(0.5)  # Wait 500ms between notifications

    def start(self):
        """
        Start the Booksamillion monitoring loop for CLI dispatcher.
        """
        self.running = True
        self.main_monitor_loop()

    def stop(self):
        """
        Stop the monitor (used by dispatcher).
        """
        self.running = False


class NoiseFilter(logging.Filter):
    """Filter out noisy log messages"""

    def filter(self, record):
        # Filter out specific CloudflareBypass messages
        noisy_messages = [
            "Cookies need refresh",
            "Making request to",
            "Response has HTML content type",
            "Found JSON object in HTML response",
            "Cookies expired or invalid",
            "Generating fresh Cloudflare cookies",
            "Accessing https://www.booksamillion.com/",
            "No cf_clearance in first try",
            "No cf_clearance cookie found",
            "Saved cookies to file"
        ]

        return not any(msg in record.getMessage() for msg in noisy_messages)

# For standalone testing
if __name__ == "__main__":
    # Get project root for log file
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logs_dir = os.path.join(project_root, "logs")

    # Ensure logs directory exists
    os.makedirs(logs_dir, exist_ok=True)

    log_file = os.path.join(logs_dir, "booksamillion.log")

    # Configure logging with reduced verbosity
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    # Set specific logger levels to reduce noise
    logging.getLogger("CloudflareBypass").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    # Apply noise filter to CloudflareBypass logger
    cf_logger = logging.getLogger("CloudflareBypass")
    cf_logger.addFilter(NoiseFilter())

    # Keep Booksamillion logger at INFO level
    logger.setLevel(logging.INFO)

    # Create module instance
    monitor = Booksamillion()

    print(f"Starting Books-A-Million Pokemon stock monitoring (Press CTRL+C to exit)")
    print(f"Monitoring interval set to {monitor.INTERVAL} seconds")

    try:
        # Run the initial monitoring cycle immediately
        print("\n=== Starting initial monitoring cycle ===")

        # Scan for new products first
        new_products = monitor.scan_new_items()
        print(f"Found {len(new_products)} new products")

        # Send notifications for new products immediately
        if new_products:
            print(f"Sending notifications for {len(new_products)} new products...")
            monitor.send_new_product_notifications(new_products)

        # Check stock for existing products
        results = monitor.check_stock()
        monitor._save_products()
        print(f"Checked stock for {len(results)} products")

        # Display in-stock products
        in_stock_count = 0
        for product in results:
            if product.get('in_stock'):
                print(f"IN STOCK: {product.get('title')} at {len(product.get('stores', []))} stores")
                in_stock_count += 1

        if in_stock_count == 0:
            print("No products currently in stock")

        # Enter continuous monitoring loop
        while True:
            # Get the interval from configuration or use default
            interval = monitor.config.get("interval", monitor.INTERVAL)

            # Calculate next run time
            next_run = datetime.datetime.now() + datetime.timedelta(seconds=interval)
            print(f"\n=== Next monitoring cycle will start at {next_run.strftime('%Y-%m-%d %H:%M:%S')} ===")
            print(f"Sleeping for {interval} seconds...")

            # Sleep until next interval
            time.sleep(interval)

            print("\n=== Starting new monitoring cycle ===")

            try:
                # Run the full monitor loop which includes scanning for new items
                # and checking stock for existing items
                monitor.main_monitor_loop()

                # Save current state
                monitor._save_products()
                monitor._save_notified_products()
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {str(e)}")
                # Sleep for a bit before trying again to avoid rapid retries on persistent errors
                time.sleep(60)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user. Exiting...")
    except Exception as e:
        logger.critical(f"Fatal error in main loop: {str(e)}")
        print(f"\nFatal error: {str(e)}")
    finally:
        # Save state before exiting
        monitor._save_products()
        monitor._save_notified_products()
        print("Monitoring stopped. Product data saved.")