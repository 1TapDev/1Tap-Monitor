#!/usr/bin/env python3
"""
Fixed CloudflareBypass Utility
Provides methods to bypass Cloudflare anti-bot protection with efficient cookie handling
"""

import time
import logging
import random
import json
import re
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import requests

# Try to import optional dependencies
try:
    import cloudscraper

    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

try:
    import tls_client

    TLS_CLIENT_AVAILABLE = True
except ImportError:
    TLS_CLIENT_AVAILABLE = False

try:
    from utils.headers_generator import generate_chrome_headers
except ImportError:
    # Fallback headers generator if the import fails
    def generate_chrome_headers():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1"
        }

# Configure logger
logger = logging.getLogger("CloudflareBypass")


class RequestLogger:
    """Simplified request logger for CloudflareBypass"""

    def __init__(self):
        self.log_dir = Path("logs/requests")
        self.readable_dir = Path("logs/readable")
        self.enabled = True  # Default to enabled
        self.save_readable = False  # Default to disable readable logs

        # Create directories
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.readable_dir.mkdir(parents=True, exist_ok=True)

    def log_from_response(self, url, method, headers, params=None, response=None):
        """Log request and response to file"""
        if not self.enabled:
            return None

        timestamp = time.strftime("%Y%m%d-%H%M%S")

        # Create a safe filename from the URL
        url_part = self._safe_filename(url)
        filename = f"{timestamp}_{method}_{url_part}.log"
        filepath = self.log_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"===== REQUEST: {url} =====\n")
                f.write(f"Method: {method}\n")
                f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("\n----- Request Headers -----\n")
                f.write(f"{headers}\n")

                if params:
                    f.write("\n----- Request Parameters -----\n")
                    f.write(f"{params}\n")

                f.write("\n----- Request Data -----\n")
                f.write("\n")

                if response:
                    f.write("\n===== RESPONSE =====\n")
                    f.write(f"Status Code: {response.status_code}\n")
                    f.write("\n----- Response Headers -----\n")
                    f.write(f"{dict(response.headers)}\n")
                    f.write("\n----- Response Body -----\n")
                    f.write(response.text[:10000])  # Limit to first 10K chars
                    if len(response.text) > 10000:
                        f.write("\n... (truncated)")

            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to log request: {str(e)}")
            return None

    def save_readable_response(self, response, output_path=None):
        """Save response content in readable format"""
        if not self.enabled or not self.save_readable:
            return False

        if output_path is None:
            timestamp = int(time.time())

            # Create a safe filename from the URL
            url_part = self._safe_filename(response.url)
            filename = f"{timestamp}_{url_part}.txt"
            output_path = self.readable_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"Status: {response.status_code}\n\n")
                f.write("Headers:\n")
                for key, value in response.headers.items():
                    f.write(f"{key}: {value}\n")

                f.write("\n\nBody:\n")
                f.write(response.text)

            return True
        except Exception as e:
            logger.error(f"Failed to save readable response: {str(e)}")
            return False

    def _safe_filename(self, url):
        """Convert URL to safe filename"""
        # Extract domain and path
        if isinstance(url, str):
            # Remove protocol
            url = re.sub(r'^https?://', '', url)

            # Get domain and first part of path
            parts = url.split('/')
            domain = parts[0]

            # Get the first path segment if it exists
            path = parts[1] if len(parts) > 1 else ""

            # Remove query parameters and fragments
            path = path.split('?')[0].split('#')[0]

            # Combine with max length limit
            result = f"{domain}_{path}"

            # Replace invalid characters
            result = re.sub(r'[\\/*?:"<>|]', '_', result)

            # Limit length
            if len(result) > 50:
                result = result[:50]

            return result
        else:
            return "unknown_url"


class CloudflareBypass:
    """
    Utility class for bypassing Cloudflare protection
    """

    def __init__(self,
                 cookie_file: str = 'data/cloudflare_cookies.json',
                 base_url: str = 'https://www.example.com',
                 target_page: str = '/',
                 cookie_max_age: int = 3600):  # Default to 1 hour cookie lifetime
        """
        Initialize the Cloudflare bypass utility

        Args:
            cookie_file: Path to the cookie file
            base_url: Base URL of the site with Cloudflare
            target_page: Specific page to use for cookie generation
            cookie_max_age: Maximum age of cookies in seconds before refreshing
        """
        self.cookie_file = Path(cookie_file)
        self.base_url = base_url.rstrip('/')
        self.target_page = target_page if target_page.startswith('/') else f'/{target_page}'
        self.cookie_max_age = cookie_max_age
        self.cookies = self._load_cookies()
        self.last_cookie_refresh = time.time() if self.cookies else 0
        self.failed_attempts = 0
        self.max_failed_attempts = 3  # Max failures before refreshing cookies

        # Ensure data directory exists
        self.cookie_file.parent.mkdir(exist_ok=True)

        # Session for making requests
        self.session = self._create_session()

        # Create request logger
        self.request_logger = RequestLogger()

        # Set default logging behavior
        self.enable_logging = True
        self.save_readable = False

    def _load_cookies(self) -> Dict[str, str]:
        """
        Load cookies from file or return empty dict

        Returns:
            Dict of cookies
        """
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'r') as f:
                    cookie_data = json.load(f)

                    # Check if cookies are still valid
                    if cookie_data.get('timestamp', 0) > time.time() - self.cookie_max_age:
                        logger.info("Loaded valid cookies from file")
                        return cookie_data.get('cookies', {})
            except Exception as e:
                logger.error(f"Error loading cookies: {str(e)}")

        # If we get here, either no cookies or expired cookies
        logger.info("No valid cookies found, will generate new ones")
        return {}

    def _save_cookies(self, cookies: Dict[str, str]):
        """
        Save cookies to file with timestamp

        Args:
            cookies: Dict of cookies to save
        """
        try:
            cookie_data = {
                'timestamp': time.time(),
                'cookies': cookies
            }
            with open(self.cookie_file, 'w') as f:
                json.dump(cookie_data, f, indent=2)
            logger.info("Saved cookies to file")
        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")

    def _create_session(self):
        """
        Create a request session with appropriate headers and cookies

        Returns:
            Session object for making requests
        """
        if CLOUDSCRAPER_AVAILABLE:
            session = cloudscraper.create_scraper()
            logger.info("Created CloudScraper session")
        else:
            session = requests.Session()
            logger.info("Created regular requests session")

        # Add headers and cookies
        headers = generate_chrome_headers()
        session.headers.update(headers)

        for name, value in self.cookies.items():
            session.cookies.set(name, value)

        return session

    def should_refresh_cookies(self):
        """
        Determine if cookies should be refreshed

        Returns:
            bool: True if cookies should be refreshed
        """
        # No cookies or expired cookies
        if not self.cookies or 'cf_clearance' not in self.cookies:
            return True

        # Cookies too old
        if time.time() - self.last_cookie_refresh > self.cookie_max_age:
            return True

        # Too many failed attempts
        if self.failed_attempts >= self.max_failed_attempts:
            return True

        return False

    def get_fresh_cookies(self) -> bool:
        """
        Get fresh Cloudflare cookies using multiple methods

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Generating fresh Cloudflare cookies...")

        # Try different methods in order of reliability
        methods = [
            self._get_cookies_with_cloudscraper,
            self._get_cookies_with_tls_client
        ]

        # Try each method until one succeeds
        for method in methods:
            success = method()
            if success:
                self.last_cookie_refresh = time.time()
                self.failed_attempts = 0
                return True

        logger.error("All cookie generation methods failed")
        return False

    def _get_cookies_with_cloudscraper(self) -> bool:
        """
        Get cookies using CloudScraper

        Returns:
            bool: True if successful, False otherwise
        """
        if not CLOUDSCRAPER_AVAILABLE:
            logger.warning("CloudScraper not available for Cloudflare bypass")
            return False

        try:
            logger.info("Attempting to get cookies with CloudScraper...")

            # Create scraper with more browser-like settings
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True,
                    'mobile': False
                }
            )

            # Add additional headers to appear more like a real browser
            additional_headers = {
                'Accept-Language': 'en-US,en;q=0.9',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-ch-ua-bitness': '64',
                'sec-ch-ua-arch': 'x86',
                'sec-ch-ua-full-version': '135.0.7049.115',
                'sec-ch-ua-platform-version': '19.0.0',
                'sec-ch-ua-full-version-list': '"Google Chrome";v="135.0.7049.115", "Not-A.Brand";v="8.0.0.0", "Chromium";v="135.0.7049.115"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1'
            }
            scraper.headers.update(additional_headers)

            # Try to access the site
            target_url = f"{self.base_url}{self.target_page}"
            response = scraper.get(target_url, timeout=20)

            if response.status_code == 200:
                # Extract cookies
                cookies = scraper.cookies.get_dict()

                # Save cookies
                self.cookies = cookies
                self._save_cookies(cookies)
                logger.info("Successfully obtained cookies with CloudScraper")
                return True
            else:
                logger.warning(f"Failed to get cookies with CloudScraper: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error using CloudScraper for cookies: {str(e)}")
            return False

    def _get_cookies_with_tls_client(self) -> bool:
        """
        Get cookies using TLS Client

        Returns:
            bool: True if successful, False otherwise
        """
        if not TLS_CLIENT_AVAILABLE:
            logger.warning("TLS Client not available for Cloudflare bypass")
            return False

        try:
            logger.info("Attempting to get cookies with TLS Client...")

            # Create client with specific browser fingerprint
            client = tls_client.Session(
                client_identifier="chrome112",
                random_tls_extension_order=True
            )

            # Set headers to mimic a real browser
            headers = generate_chrome_headers()
            headers.update({
                'Accept-Language': 'en-US,en;q=0.9',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-ch-ua-bitness': '64',
                'sec-ch-ua-arch': 'x86',
                'sec-ch-ua-full-version': '135.0.7049.115',
                'sec-ch-ua-platform-version': '19.0.0',
                'sec-ch-ua-full-version-list': '"Google Chrome";v="135.0.7049.115", "Not-A.Brand";v="8.0.0.0", "Chromium";v="135.0.7049.115"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1'
            })
            client.headers.update(headers)

            # Try to access the site
            target_url = f"{self.base_url}{self.target_page}"
            response = client.get(target_url, timeout=20)

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
                return False

        except Exception as e:
            logger.error(f"Error using TLS Client for cookies: {str(e)}")
            return False

    def create_session(self) -> requests.Session:
        """
        Create and return a session with valid Cloudflare cookies

        Returns:
            Session object for making requests
        """
        # Check if we need to refresh cookies
        if self.should_refresh_cookies():
            self.get_fresh_cookies()

        # Create a new session with current cookies
        return self._create_session()

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Make a GET request with Cloudflare bypass and log details

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.get

        Returns:
            Response object
        """
        # Get request parameters
        enable_logging = kwargs.pop('enable_logging', self.enable_logging)
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', None)
        timeout = kwargs.get('timeout', 30)

        # Ensure we have valid cookies
        if self.should_refresh_cookies():
            self.get_fresh_cookies()

        # Make the request
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                logger.info(f"Making request to {url} (attempt {attempt + 1}/{max_retries})")

                # Make the actual request
                response = self.session.get(url, **kwargs)

                # Check if the response is valid JSON even if content-type is HTML
                if 'application/json' in kwargs.get('headers', {}).get('Accept',
                                                                       '') and 'text/html' in response.headers.get(
                    'Content-Type', ''):
                    logger.info("Response has HTML content type but we requested JSON, attempting to extract JSON")

                    # Try to extract JSON from the HTML
                    json_match = re.search(r'({"userinfo":.*})', response.text)
                    if json_match:
                        logger.info("Found JSON object in HTML response")

                # Log the request and response
                if enable_logging:
                    log_path = self.request_logger.log_from_response(
                        url=url,
                        method="GET",
                        headers=dict(self.session.headers) if headers is None else headers,
                        params=params,
                        response=response
                    )
                    if log_path:
                        logger.info(f"Request log saved to {log_path}")

                # Save readable response if enabled
                if self.save_readable:
                    timestamp = int(time.time())
                    readable_filename = self.request_logger._safe_filename(url)
                    readable_path = Path("logs/readable") / f"{timestamp}_{readable_filename}.txt"

                    if self.request_logger.save_readable_response(response, readable_path):
                        logger.info(f"Readable response saved to {readable_path}")

                # Check if we hit a Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()

                    # Re-create the session with new cookies
                    self.session = self._create_session()
                    continue

                # Successful request
                if response.status_code == 200:
                    self.failed_attempts = 0
                else:
                    # Track failed attempts
                    self.failed_attempts += 1

                return response

            except Exception as e:
                error_msg = f"Request error on attempt {attempt + 1}: {str(e)}"
                logger.error(error_msg)

                # Track failed attempts
                self.failed_attempts += 1

                # Calculate backoff time with jitter, capped at 30 seconds
                wait_time = min(30, backoff_factor * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                time.sleep(wait_time)

                # Refresh session for next attempt if this isn't the last try
                if attempt < max_retries - 1:
                    self.refresh_session()

        # If we get here, all retries failed
        raise Exception(f"Failed to get {url} after {max_retries} attempts")

    def post(self, url: str, **kwargs) -> requests.Response:
        """
        Make a POST request with Cloudflare bypass and log details

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.post

        Returns:
            Response object
        """
        # Get request parameters
        enable_logging = kwargs.pop('enable_logging', self.enable_logging)
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', None)
        data = kwargs.get('data', None)
        json_data = kwargs.get('json', None)

        # Ensure we have valid cookies
        if self.should_refresh_cookies():
            self.get_fresh_cookies()

        # Make the request
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                logger.info(f"Making POST request to {url} (attempt {attempt + 1}/{max_retries})")

                # Make the actual request
                response = self.session.post(url, **kwargs)

                # Log the request and response
                if enable_logging:
                    log_path = self.request_logger.log_from_response(
                        url=url,
                        method="POST",
                        headers=dict(self.session.headers) if headers is None else headers,
                        params=params,
                        response=response
                    )
                    if log_path:
                        logger.info(f"Request log saved to {log_path}")

                # Check if we hit a Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()

                    # Re-create the session with new cookies
                    self.session = self._create_session()
                    continue

                # Successful request
                if response.status_code == 200:
                    self.failed_attempts = 0
                else:
                    # Track failed attempts
                    self.failed_attempts += 1

                return response

            except Exception as e:
                error_msg = f"Request error on attempt {attempt + 1}: {str(e)}"
                logger.error(error_msg)

                # Track failed attempts
                self.failed_attempts += 1

                # Calculate backoff time with jitter, capped at 30 seconds
                wait_time = min(30, backoff_factor * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                time.sleep(wait_time)

                # Refresh session for next attempt if this isn't the last try
                if attempt < max_retries - 1:
                    self.refresh_session()

        # If we get here, all retries failed
        raise Exception(f"Failed to post to {url} after {max_retries} attempts")

    def refresh_session(self):
        """Refresh the session with new cookies"""
        self.get_fresh_cookies()
        self.session = self._create_session()
        logger.info("Refreshed session with new cookies")

    def set_logging(self, enable_logging=True, save_readable=False):
        """Configure logging behavior"""
        self.enable_logging = enable_logging
        self.save_readable = save_readable
        self.request_logger.enabled = enable_logging
        self.request_logger.save_readable = save_readable


# Create a function to get cloudflare bypass instance
def get_cloudflare_bypass(base_url, cookie_file=None, cookie_max_age=3600):
    """
    Get a CloudflareBypass instance for a specific site

    Args:
        base_url: Base URL for the site
        cookie_file: Optional custom cookie file path
        cookie_max_age: Maximum age of cookies in seconds

    Returns:
        CloudflareBypass instance
    """
    if not cookie_file:
        # Generate a filename based on the domain
        domain = re.sub(r'^https?://', '', base_url).split('/')[0]
        cookie_file = f"data/{domain}_cookies.json"

    return CloudflareBypass(
        cookie_file=cookie_file,
        base_url=base_url,
        target_page="/",
        cookie_max_age=cookie_max_age
    )


# Test the module if run directly
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create a Cloudflare bypass instance for Books-A-Million
    bypass = get_cloudflare_bypass(
        base_url='https://www.booksamillion.com',
        cookie_file='data/booksamillion_cookies.json'
    )

    # Configure logging behavior
    bypass.set_logging(enable_logging=True, save_readable=False)

    # Get fresh cookies
    bypass.get_fresh_cookies()

    # Test a get request
    response = bypass.get('https://www.booksamillion.com')
    print(f"Response status code: {response.status_code}")
    print(f"Response length: {len(response.text)}")

    # Extract page title to verify we got past Cloudflare
    title_match = re.search(r'<title>(.*?)</title>', response.text)
    if title_match:
        print(f"Page title: {title_match.group(1)}")
    else:
        print("Could not find page title")