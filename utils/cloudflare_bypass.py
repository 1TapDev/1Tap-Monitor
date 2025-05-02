#!/usr/bin/env python3
"""
Enhanced Cloudflare Bypass Utility
Provides methods to bypass Cloudflare anti-bot protection
"""

import time
import logging
import random
import json
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

from utils.headers_generator import generate_chrome_headers

logger = logging.getLogger("CloudflareBypass")


class CloudflareBypass:
    """
    Enhanced utility class for bypassing Cloudflare protection
    """

    def __init__(self,
                 cookie_file: str = 'data/cloudflare_cookies.json',
                 base_url: str = 'https://www.example.com',
                 target_page: str = '/'):
        """
        Initialize the Cloudflare bypass utility

        Args:
            cookie_file: Path to the cookie file
            base_url: Base URL of the site with Cloudflare
            target_page: Specific page to use for cookie generation
        """
        self.cookie_file = Path(cookie_file)
        self.base_url = base_url.rstrip('/')
        self.target_page = target_page if target_page.startswith('/') else f'/{target_page}'
        self.cookies = self._load_cookies()

        # Ensure data directory exists
        self.cookie_file.parent.mkdir(exist_ok=True)

        # Session for making requests
        self.session = self._create_session()

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

                    # Check if cookies are still valid (within 23 hours)
                    if cookie_data.get('timestamp', 0) > time.time() - 82800:
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

    def get_fresh_cookies(self) -> bool:
        """
        Get fresh Cloudflare cookies using multiple methods

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Generating fresh Cloudflare cookies...")

        # Try different methods in order of reliability
        methods = [
            self._get_cookies_with_selenium,
            self._get_cookies_with_cloudscraper,
            self._get_cookies_with_tls_client
        ]

        # Try each method until one succeeds
        for method in methods:
            success = method()
            if success:
                return True

        logger.error("All cookie generation methods failed")
        return False

    def _get_cookies_with_selenium(self) -> bool:
        """
        Get cookies using Selenium with undetected-chromedriver

        Returns:
            bool: True if successful, False otherwise
        """
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available for Cloudflare bypass")
            return False

        try:
            logger.info("Attempting to get cookies with Selenium...")

            # Configure Chrome options
            options = uc.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'--user-agent={generate_chrome_headers()["User-Agent"]}')

            # Create driver with a longer page load timeout
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(30)

            # Navigate to the site
            target_url = f"{self.base_url}{self.target_page}"
            logger.info(f"Navigating to {target_url}")
            driver.get(target_url)

            # Wait for page to load fully and Cloudflare to resolve
            logger.info("Waiting for Cloudflare challenge to resolve...")

            # Wait for a common element that would appear after Cloudflare challenge
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                # Additional wait for possible Cloudflare challenge
                time.sleep(5)
            except Exception as e:
                logger.warning(f"Timed out waiting for page elements: {e}")

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
                return False

        except Exception as e:
            logger.error(f"Error using Selenium for cookies: {str(e)}")
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
        if 'cf_clearance' not in self.cookies:
            self.get_fresh_cookies()

        # Create a new session with current cookies
        return self._create_session()

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Make a GET request with Cloudflare bypass

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.get

        Returns:
            Response object
        """
        # Ensure we have valid cookies
        if 'cf_clearance' not in self.cookies:
            self.get_fresh_cookies()

        # Make the request
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, **kwargs)

                # Check if we hit a Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()

                    # Re-create the session with new cookies
                    self.session = self._create_session()
                    continue

                return response

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                wait_time = backoff_factor * (2 ** attempt)
                time.sleep(wait_time)

        # If we get here, all retries failed
        raise Exception(f"Failed to get {url} after {max_retries} attempts")

    def post(self, url: str, **kwargs) -> requests.Response:
        """
        Make a POST request with Cloudflare bypass

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.post

        Returns:
            Response object
        """
        # Ensure we have valid cookies
        if 'cf_clearance' not in self.cookies:
            self.get_fresh_cookies()

        # Make the request
        max_retries = kwargs.pop('max_retries', 3)
        backoff_factor = kwargs.pop('backoff_factor', 1.5)

        for attempt in range(max_retries):
            try:
                response = self.session.post(url, **kwargs)

                # Check if we hit a Cloudflare challenge
                if response.status_code == 403 or "challenge" in response.text.lower():
                    logger.warning(f"Got Cloudflare challenge on attempt {attempt + 1}, refreshing cookies...")
                    self.get_fresh_cookies()

                    # Re-create the session with new cookies
                    self.session = self._create_session()
                    continue

                return response

            except Exception as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                wait_time = backoff_factor * (2 ** attempt)
                time.sleep(wait_time)

        # If we get here, all retries failed
        raise Exception(f"Failed to post to {url} after {max_retries} attempts")


def create_session(
        bypass_method: str = "auto",
        base_url: str = None,
        cookie_file: str = None
) -> requests.Session:
    """
    Create a request session with Cloudflare bypass capability

    Args:
        bypass_method: Method to use for bypass ("auto", "cloudscraper", "selenium", "tls_client")
        base_url: Base URL for the site (needed for some methods)
        cookie_file: Path to cookie file (optional)

    Returns:
        Session object for making requests
    """
    # For backwards compatibility, provide simple session creation
    if bypass_method == "cloudscraper" and CLOUDSCRAPER_AVAILABLE:
        session = cloudscraper.create_scraper()
        logger.info("Created CloudScraper session")
        return session
    elif bypass_method == "tls_client" and TLS_CLIENT_AVAILABLE:
        session = tls_client.Session(client_identifier="chrome112")
        logger.info("Created TLS Client session")
        return session
    else:
        # If no specific method requested or requested method not available,
        # return a regular session with good headers
        session = requests.Session()
        headers = generate_chrome_headers()
        session.headers.update(headers)
        logger.info("Created regular requests session with browser headers")
        return session


# Test the module if run directly
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create a Cloudflare bypass instance for a specific site
    bypass = CloudflareBypass(
        cookie_file='data/bam_cookies.json',
        base_url='https://www.booksamillion.com',
        target_page='/'
    )

    # Get fresh cookies
    bypass.get_fresh_cookies()

    # Test a get request
    response = bypass.get('https://www.booksamillion.com')
    print(f"Response status code: {response.status_code}")
    print(f"Response length: {len(response.text)}")

    # Extract page title to verify we got past Cloudflare
    import re

    title_match = re.search(r'<title>(.*?)</title>', response.text)
    if title_match:
        print(f"Page title: {title_match.group(1)}")
    else:
        print("Could not find page title")