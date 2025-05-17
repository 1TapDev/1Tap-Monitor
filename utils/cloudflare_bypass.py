#!/usr/bin/env python3
"""
CloudflareBypass with compatibility fixes for Books-A-Million
Fixes both TLS Client timeout issue and adds additional browser fingerprinting
"""

import time
import logging
import random
import json
import re
import os
from pathlib import Path

import requests

# Try to import optional dependencies
try:
    import cloudscraper

    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    print("CloudScraper not available. Some features may be limited.")

try:
    import tls_client

    TLS_CLIENT_AVAILABLE = True
except ImportError:
    TLS_CLIENT_AVAILABLE = False
    print("TLS Client not available. Some features may be limited.")

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CloudflareBypass")


class RequestLogger:
    """Simplified request logger for CloudflareBypass"""

    def __init__(self):
        self.log_dir = Path("logs/requests")
        self.enabled = True  # Default to enabled

        # Create directory
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_from_response(self, url, method, headers, params=None, response=None, log_filename=None):
        """Log request and response to file - with log_filename parameter"""
        if not self.enabled:
            return None

        timestamp = time.strftime("%Y%m%d-%H%M%S")

        # Use provided log_filename if available
        if log_filename:
            filename = f"{timestamp}_{method}_{log_filename}.log"
        else:
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
    """Utility class for bypassing Cloudflare protection with improved cookie handling"""

    def __init__(self, cookie_file='data/cloudflare_cookies.json', base_url='https://www.example.com', target_page='/',
                 cookie_max_age=3600):
        """Initialize the CloudflareBypass"""
        self.cookie_file = Path(cookie_file)
        self.base_url = base_url.rstrip('/')
        self.target_page = target_page if target_page.startswith('/') else f'/{target_page}'
        self.cookie_max_age = cookie_max_age
        self.cookies = {}
        self.last_cookie_refresh = 0
        self.failed_attempts = 0
        self.max_failed_attempts = 3

        # Ensure data directory exists
        self.cookie_file.parent.mkdir(exist_ok=True)

        # Load cookies
        self._load_cookies()

        # Create session
        self.session = self._create_session()

        # Create request logger
        self.request_logger = RequestLogger()

        # Set default logging behavior
        self.enable_logging = True

        self.aggressive_mode = False

    def _load_cookies(self):
        """Load cookies from file"""
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'r') as f:
                    cookie_data = json.load(f)

                    # Check if cookies are still valid (not too old)
                    stored_timestamp = cookie_data.get('timestamp', 0)
                    cookie_age = time.time() - stored_timestamp

                    if cookie_age < self.cookie_max_age:
                        self.cookies = cookie_data.get('cookies', {})
                        self.last_cookie_refresh = stored_timestamp

                        if 'cf_clearance' in self.cookies:
                            cookie_age_minutes = int(cookie_age / 60)
                            logger.info(f"Loaded valid cookies from file, age: {cookie_age_minutes} minutes")
                            return True
                        else:
                            logger.info("Stored cookies don't have cf_clearance, generating new ones")
                    else:
                        logger.info(
                            f"Cookies expired (age: {int(cookie_age / 60)} minutes, max: {int(self.cookie_max_age / 60)} minutes)")

            except Exception as e:
                logger.error(f"Error loading cookies: {str(e)}")

        logger.info("No valid cookies found, will generate new ones")
        self.cookies = {}
        self.last_cookie_refresh = 0
        return False

    def _save_cookies(self, cookies):
        """Save cookies to file with timestamp"""
        try:
            now = time.time()
            cookie_data = {
                'timestamp': now,
                'cookies': cookies
            }
            with open(self.cookie_file, 'w') as f:
                json.dump(cookie_data, f, indent=2)

            # Update internal state
            self.cookies = cookies
            self.last_cookie_refresh = now

            logger.info("Saved cookies to file")
            return True
        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")
            return False

    def _create_session(self):
        """Create a request session with appropriate headers and cookies"""
        if CLOUDSCRAPER_AVAILABLE:
            session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True,
                    'mobile': False
                }
            )
            logger.info("Created CloudScraper session")
        else:
            session = requests.Session()
            logger.info("Created regular requests session")

        # Add headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.118 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        session.headers.update(headers)

        # Extra spoof headers to look more like real browser
        session.headers.update({
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "Pragma": "no-cache"
        })

        # Add cookies if we have any
        for name, value in self.cookies.items():
            session.cookies.set(name, value)

        # Log cookie status
        if 'cf_clearance' in self.cookies:
            cf_value = self.cookies.get('cf_clearance', '')
            logger.info(f"Added cf_clearance cookie to session: {cf_value[:8]}...")
        else:
            logger.info("No cf_clearance cookie to add to session")

        return session

    def should_refresh_cookies(self):
        """Determine if cookies should be refreshed"""
        # No cookies or missing cf_clearance
        if not self.cookies or 'cf_clearance' not in self.cookies:
            logger.info("Cookies need refresh: No cookies or missing cf_clearance")
            return True

        # Cookies too old
        cookie_age = time.time() - self.last_cookie_refresh
        if cookie_age > self.cookie_max_age:
            logger.info(
                f"Cookies need refresh: Age {int(cookie_age / 60)} minutes exceeds max age {int(self.cookie_max_age / 60)} minutes")
            return True

        # Too many failed attempts
        if self.failed_attempts >= self.max_failed_attempts:
            logger.info(f"Cookies need refresh: Too many failed attempts ({self.failed_attempts})")
            return True

        # Cookies are valid and not expired
        logger.info(f"Cookies are valid - age: {int(cookie_age / 60)} minutes")
        return False

    def get_fresh_cookies(self):
        """Get fresh Cloudflare cookies using multiple methods"""
        logger.info("Generating fresh Cloudflare cookies...")

        # Try cloudscraper first
        if CLOUDSCRAPER_AVAILABLE:
            success = self._get_cookies_with_cloudscraper()
            if success or self.cookies:
                self.failed_attempts = 0
                return True

        # Only use TLS Client if cookies are still empty
        if TLS_CLIENT_AVAILABLE and not self.cookies:
            success = self._get_cookies_with_tls_client()
            if success:
                self.failed_attempts = 0
                return True

        # If we can't get cf_clearance, just continue with session
        logger.warning("Could not get cf_clearance cookie, continuing with regular session")

        # Create a new session anyway
        self.session = self._create_session()
        # We'll keep trying on each request
        return False

    def _get_cookies_with_cloudscraper(self):
        """Get cookies using CloudScraper with enhanced browser fingerprinting"""
        if not CLOUDSCRAPER_AVAILABLE:
            return False

        try:
            logger.info("Attempting to get cookies with CloudScraper...")

            # More advanced browser fingerprinting
            browser_details = {
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
                'mobile': False,
                'renderer': 'webkit'
            }

            # Create a new cloudscraper instance
            scraper = cloudscraper.create_scraper(
                browser=browser_details,
                delay=3,  # Add a delay between requests
                interpreter='nodejs'  # Try using nodejs interpreter
            )

            # Set more detailed headers to make it look more like a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'Upgrade-Insecure-Requests': '1',
                'Content-Type': 'application/x-www-form-urlencoded',
                'DNT': '1',
                'Pragma': 'no-cache'
            }
            scraper.headers.update(headers)

            # Try direct connection
            target_url = f"{self.base_url}/"
            logger.info(f"Accessing {target_url} to get cookies...")

            # First try with direct URL
            response = scraper.get(target_url)

            # Extract and save all cookies regardless of cf_clearance
            cookies = scraper.cookies.get_dict()

            # Try to find cf_clearance specifically
            if 'cf_clearance' in cookies:
                logger.info(f"Found cf_clearance: {cookies['cf_clearance'][:8]}...")
                self._save_cookies(cookies)

                # Replace the current session with this new one
                self.session = scraper
                return True
            else:
                # Try a different page to get cookies
                logger.info("No cf_clearance in first try, attempting a different page...")
                search_url = f"{self.base_url}/search?query=pokemon"
                response = scraper.get(search_url)

                # Check cookies again
                cookies = scraper.cookies.get_dict()
                if 'cf_clearance' in cookies:
                    logger.info(f"Found cf_clearance on second try: {cookies['cf_clearance'][:8]}...")
                    self._save_cookies(cookies)
                    self.session = scraper
                    return True

                logger.warning("No cf_clearance cookie found in response")

                # Save whatever cookies we got anyway
                if cookies:
                    self._save_cookies(cookies)
                    self.session = scraper

                return False

        except Exception as e:
            logger.error(f"Error using CloudScraper for cookies: {str(e)}")
            return False

    def _get_cookies_with_tls_client(self):
        """Get cookies using TLS Client with fixed timeout handling"""
        if not TLS_CLIENT_AVAILABLE:
            return False

        try:
            logger.info("Attempting to get cookies with TLS Client...")

            # Create TLS client instance with more specific browser profile
            client = tls_client.Session(client_identifier="chrome112")

            # Set headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "sec-ch-ua": '"Google Chrome";v="112", "Chromium";v="112", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1"
            }
            client.headers.update(headers)

            # Access the site (remove timeout parameter which was causing the error)
            target_url = f"{self.base_url}{self.target_page}"
            logger.info(f"Accessing {target_url} with TLS Client...")
            response = client.get(target_url)  # No timeout parameter

            if response.status_code == 200:
                # Extract and save cookies
                cookies = client.cookies.get_dict()

                # Check if cf_clearance is present
                if 'cf_clearance' in cookies:
                    logger.info(f"Found cf_clearance: {cookies['cf_clearance'][:8]}...")
                    self._save_cookies(cookies)

                    # Create a new session with these cookies
                    self.session = requests.Session()
                    self.session.headers.update(headers)
                    for name, value in cookies.items():
                        self.session.cookies.set(name, value)

                    return True
                else:
                    logger.warning("No cf_clearance cookie found in TLS Client response")

                    # Save whatever cookies we got anyway
                    if cookies:
                        self._save_cookies(cookies)

                        # Use regular session with these cookies
                        self.session = requests.Session()
                        self.session.headers.update(headers)
                        for name, value in cookies.items():
                            self.session.cookies.set(name, value)

                    return False
            elif response.status_code == 403:
                logger.warning("TLS Client bypass failed permanently with 403, skipping to fallback.")
                return False
            else:
                logger.warning(f"Failed to get cookies with TLS Client: {response.status_code}")
                return False


        except Exception as e:
            logger.error(f"Error using TLS Client for cookies: {str(e)}")
            return False

    def create_session(self):
        """Create and return a session with valid Cloudflare cookies"""
        # Check if we need to refresh cookies
        if self.should_refresh_cookies():
            self.get_fresh_cookies()

        if getattr(self, "aggressive_mode", False):
            logger.info("Aggressive mode enabled — skipping cookie refresh")
            return False

        # Return the session (which was updated if needed)
        return self.session

    def get(self, url, **kwargs):
        """Make a GET request with Cloudflare bypass"""
        # Extract special parameters
        enable_logging = kwargs.pop('enable_logging', self.enable_logging)
        log_filename = kwargs.pop('log_filename', None)

        # Refresh only once per session start or after 403
        if self.should_refresh_cookies() and not self.cookies:
            logger.info("No valid cookies at startup, refreshing...")
            self.get_fresh_cookies()

        # Make the request with retry logic
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                logger.info(f"Making request to {url} (attempt {attempt + 1}/{max_retries})")

                # Make the actual request
                response = self.session.get(url, **kwargs)

                # Check for JSON in HTML response
                if ('application/json' in kwargs.get('headers', {}).get('Accept', '') and
                        'text/html' in response.headers.get('Content-Type', '')):
                    logger.info("Response has HTML content type but we requested JSON, checking for JSON...")
                    json_match = re.search(r'({"userinfo":.*})', response.text)
                    if json_match:
                        logger.info("Found JSON object in HTML response")

                # Log the request if enabled
                if enable_logging:
                    log_path = self.request_logger.log_from_response(
                        url=url,
                        method="GET",
                        headers=dict(self.session.headers),
                        params=kwargs.get('params'),
                        response=response,
                        log_filename=log_filename
                    )

                # Check for Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()
                    continue

                # Handle success or failure
                if response.status_code == 200:
                    self.failed_attempts = 0
                else:
                    self.failed_attempts += 1

                return response

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                self.failed_attempts += 1

                # Calculate backoff with jitter
                wait_time = min(30, backoff_factor * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                time.sleep(wait_time)

                # Refresh session for next attempt
                if attempt < max_retries - 1:
                    self.refresh_session()

        # If we get here, all retries failed
        raise Exception(f"Failed to get {url} after {max_retries} attempts")

    def post(self, url, **kwargs):
        """Make a POST request with Cloudflare bypass"""
        # Extract special parameters
        enable_logging = kwargs.pop('enable_logging', self.enable_logging)
        log_filename = kwargs.pop('log_filename', None)

        # Check if cookies need refreshing
        if self.should_refresh_cookies():
            logger.info("Cookies expired or invalid, refreshing...")
            self.get_fresh_cookies()

        # Make the request with retry logic
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                logger.info(f"Making POST request to {url} (attempt {attempt + 1}/{max_retries})")

                # Make the actual request
                response = self.session.post(url, **kwargs)

                # Log the request if enabled
                if enable_logging:
                    log_path = self.request_logger.log_from_response(
                        url=url,
                        method="POST",
                        headers=dict(self.session.headers),
                        params=kwargs.get('params'),
                        response=response,
                        log_filename=log_filename
                    )

                # Check for Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()
                    continue

                # Handle success or failure
                if response.status_code == 200:
                    self.failed_attempts = 0
                else:
                    self.failed_attempts += 1

                return response

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                self.failed_attempts += 1

                # Calculate backoff with jitter
                wait_time = min(30, backoff_factor * (2 ** attempt) * (0.8 + 0.4 * random.random()))
                time.sleep(wait_time)

                # Refresh session for next attempt
                if attempt < max_retries - 1:
                    self.refresh_session()

        # If we get here, all retries failed
        raise Exception(f"Failed to post to {url} after {max_retries} attempts")

    def refresh_session(self):
        """Refresh the session with new cookies"""
        self.get_fresh_cookies()
        logger.info("Refreshed session with new cookies")

    def set_logging(self, enable_logging=True, save_readable=False):
        """Configure logging behavior"""
        self.enable_logging = enable_logging
        self.request_logger.enabled = enable_logging


def get_cloudflare_bypass(base_url, cookie_file=None, cookie_max_age=3600):
    """Get a CloudflareBypass instance for a specific site"""
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
    print("Testing CloudflareBypass functionality...")

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Test cookie file
    test_cookie_file = "data/test_cookies.json"

    # Create Cloudflare bypass instance
    bypass = get_cloudflare_bypass(
        base_url="https://www.booksamillion.com",
        cookie_file=test_cookie_file
    )

    # Make three consecutive requests to test session handling
    try:
        print("\nTest 1: Making first request")
        resp1 = bypass.get("https://www.booksamillion.com", timeout=30)
        print(f"First request status: {resp1.status_code}")

        time.sleep(2)

        print("\nTest 2: Making second request")
        resp2 = bypass.get("https://www.booksamillion.com/search?query=pokemon", timeout=30)
        print(f"Second request status: {resp2.status_code}")

        time.sleep(2)

        print("\nTest 3: Making third request")
        resp3 = bypass.get("https://www.booksamillion.com/search?query=manga", timeout=30)
        print(f"Third request status: {resp3.status_code}")

        if resp1.status_code == 200 and resp2.status_code == 200 and resp3.status_code == 200:
            print("\n✅ SUCCESS: All requests completed successfully!")
            print("The CloudflareBypass is working correctly.")
        else:
            print("\n❌ FAILURE: Not all requests were successful.")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")