#!/usr/bin/env python3
"""
Cloudflare Bypass Utilities
Functions to help bypass Cloudflare and other anti-bot protections.
"""

import logging
import time
import json
from pathlib import Path
from typing import Dict, Optional, Union, Tuple, List, Any

import requests

logger = logging.getLogger("CloudflareBypass")

# Try to import bypass libraries
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


def create_session(method: str = "cloudscraper",
                  browser: str = "chrome",
                  headers: Optional[Dict[str, str]] = None,
                  cookies: Optional[Dict[str, str]] = None) -> Union[requests.Session, object]:
    """
    Create a session with the specified bypass method

    Args:
        method: Bypass method ('cloudscraper', 'tls_client', 'selenium', 'requests')
        browser: Browser to emulate ('chrome', 'firefox', 'safari')
        headers: Optional headers to set
        cookies: Optional cookies to set

    Returns:
        A session object compatible with requests API
    """
    session = None

    # Set up the requested bypass method
    if method == "cloudscraper" and CLOUDSCRAPER_AVAILABLE:
        session = cloudscraper.create_scraper(
            browser={
                'browser': browser,
                'platform': 'windows',
                'mobile': False
            }
        )
        logger.info("Created CloudScraper session")

    elif method == "tls_client" and TLS_CLIENT_AVAILABLE:
        # Map browser to tls_client browser ID
        browser_map = {
            'chrome': 'chrome112',
            'firefox': 'firefox_102',
            'safari': 'safari_ios_16_0'
        }
        browser_id = browser_map.get(browser.lower(), 'chrome112')

        session = tls_client.Session(client_identifier=browser_id)
        logger.info(f"Created TLS Client session with {browser_id}")

    else:
        # Fallback to regular requests
        session = requests.Session()
        logger.info("Created regular requests session")

    # Set headers if provided
    if headers:
        session.headers.update(headers)

    # Set cookies if provided
    if cookies:
        for name, value in cookies.items():
            session.cookies.set(name, value)

    return session


def get_cf_cookies(url: str, method: str = "auto",
                  timeout: int = 30,
                  headless: bool = True) -> Dict[str, str]:
    """
    Get Cloudflare cookies using the best available method

    Args:
        url: URL to visit to get cookies
        method: Method to use ('auto', 'selenium', 'cloudscraper', 'tls_client')
        timeout: Maximum time to wait in seconds
        headless: Whether to run browser in headless mode

    Returns:
        Dictionary of cookies
    """
    cookies = {}

    # Determine methods available
    available_methods = []
    if SELENIUM_AVAILABLE:
        available_methods.append("selenium")
    if CLOUDSCRAPER_AVAILABLE:
        available_methods.append("cloudscraper")
    if TLS_CLIENT_AVAILABLE:
        available_methods.append("tls_client")

    # If auto, use the best available method
    if method == "auto":
        if not available_methods:
            logger.error("No bypass methods available. Install cloudscraper, undetected_chromedriver, or tls_client.")
            return cookies

        method = available_methods[0]  # Use first available method

    # Selenium method
    if method == "selenium" and SELENIUM_AVAILABLE:
        try:
            logger.info("Getting Cloudflare cookies with Selenium...")

            # Configure Chrome options
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-dev-shm-usage')

            # Create driver
            driver = uc.Chrome(options=options)

            # Set page load timeout
            driver.set_page_load_timeout(timeout)

            # Navigate to URL
            driver.get(url)

            # Wait for page to load fully and Cloudflare to resolve
            logger.info("Waiting for page to load and Cloudflare to resolve...")

            # Wait for a common element that would appear after Cloudflare challenge
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                # Additional wait for possible Cloudflare challenge
                time.sleep(5)
            except Exception as e:
                logger.warning(f"Timed out waiting for page elements: {e}")

            # Extract cookies
            for cookie in driver.get_cookies():
                cookies[cookie['name']] = cookie['value']

            # Check for Cloudflare cookies
            if 'cf_clearance' in cookies:
                logger.info("Successfully obtained Cloudflare cookies with Selenium")
            else:
                logger.warning("Cloudflare cookies not found in Selenium session")

            # Close browser
            driver.quit()

        except Exception as e:
            logger.error(f"Error using Selenium for Cloudflare bypass: {str(e)}")

    # CloudScraper method
    elif method == "cloudscraper" and CLOUDSCRAPER_AVAILABLE:
        try:
            logger.info("Getting Cloudflare cookies with CloudScraper...")

            # Create scraper
            scraper = cloudscraper.create_scraper()

            # Make request
            response = scraper.get(url, timeout=timeout)

            # Check response
            if response.status_code == 200:
                # Extract cookies
                for name, value in scraper.cookies.get_dict().items():
                    cookies[name] = value

                # Check for Cloudflare cookies
                if 'cf_clearance' in cookies:
                    logger.info("Successfully obtained Cloudflare cookies with CloudScraper")
                else:
                    logger.warning("Cloudflare cookies not found in CloudScraper session")
            else:
                logger.error(f"CloudScraper received HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"Error using CloudScraper for Cloudflare bypass: {str(e)}")

    # TLS Client method
    elif method == "tls_client" and TLS_CLIENT_AVAILABLE:
        try:
            logger.info("Getting Cloudflare cookies with TLS Client...")

            # Create client
            client = tls_client.Session(client_identifier="chrome112")

            # Make request
            response = client.get(url, timeout=timeout)

            # Check response
            if response.status_code == 200:
                # Extract cookies
                cookies = client.cookies.get_dict()

                # Check for Cloudflare cookies
                if 'cf_clearance' in cookies:
                    logger.info("Successfully obtained Cloudflare cookies with TLS Client")
                else:
                    logger.warning("Cloudflare cookies not found in TLS Client session")
            else:
                logger.error(f"TLS Client received HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"Error using TLS Client for Cloudflare bypass: {str(e)}")

    else:
        logger.error(f"Requested method '{method}' is not available or not recognized")

    return cookies


def save_cookies(cookies: Dict[str, str], file_path: str) -> bool:
    """
    Save cookies to a JSON file with timestamp

    Args:
        cookies: Dictionary of cookies to save
        file_path: Path to save cookies to

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cookie_data = {
            'timestamp': time.time(),
            'cookies': cookies
        }

        with open(file_path, 'w') as f:
            json.dump(cookie_data, f, indent=2)

        logger.info(f"Saved {len(cookies)} cookies to {file_path}")
        return True

    except Exception as e:
        logger.error(f"Error saving cookies to {file_path}: {str(e)}")
        return False


def load_cookies(file_path: str, max_age_hours: float = 23.0) -> Dict[str, str]:
    """
    Load cookies from a JSON file, checking if they're still valid based on age

    Args:
        file_path: Path to load cookies from
        max_age_hours: Maximum age of cookies in hours

    Returns:
        Dictionary of cookies if valid, empty dict otherwise
    """
    try:
        # Check if file exists
        cookie_file = Path(file_path)
        if not cookie_file.exists():
            logger.info(f"Cookie file {file_path} does not exist")
            return {}

        # Load cookies
        with open(file_path, 'r') as f:
            cookie_data = json.load(f)

        # Check if cookies are still valid (within max_age_hours)
        timestamp = cookie_data.get('timestamp', 0)
        max_age_seconds = max_age_hours * 3600

        if time.time() - timestamp > max_age_seconds:
            logger.info(f"Cookies in {file_path} are expired (older than {max_age_hours} hours)")
            return {}

        cookies = cookie_data.get('cookies', {})
        logger.info(f"Loaded {len(cookies)} valid cookies from {file_path}")
        return cookies

    except Exception as e:
        logger.error(f"Error loading cookies from {file_path}: {str(e)}")
        return {}


def detect_cloudflare(response: requests.Response) -> bool:
    """
    Detect if a response indicates a Cloudflare challenge

    Args:
        response: Response object to check

    Returns:
        bool: True if Cloudflare challenge detected, False otherwise
    """
    # Check status code
    if response.status_code in (403, 503):
        # Check for Cloudflare keywords in response
        text = response.text.lower()
        if any(keyword in text for keyword in (
            'cloudflare',
            'cf-ray',
            'challenge',
            'jschl',
            'captcha',
            'checking your browser'
        )):
            return True

    # Check for Cloudflare headers
    headers = response.headers
    if 'cf-ray' in headers or 'cf-cache-status' in headers:
        return True

    return False


def get_bypass_session(site_url: str,
                      cookie_file: str = "cf_cookies.json",
                      method: str = "auto",
                      force_refresh: bool = False) -> requests.Session:
    """
    Get a session with valid Cloudflare bypass cookies, refreshing if needed

    Args:
        site_url: URL of the site to bypass
        cookie_file: Path to cookie file
        method: Method to use for obtaining cookies
        force_refresh: Whether to force refreshing cookies regardless of age

    Returns:
        Session with Cloudflare bypass cookies
    """
    # Try to load existing cookies
    cookies = {} if force_refresh else load_cookies(cookie_file)

    # If no cookies or forcing refresh, get fresh cookies
    if not cookies or force_refresh:
        cookies = get_cf_cookies(site_url, method=method)
        if cookies:
            save_cookies(cookies, cookie_file)

    # Create a session with the cookies
    session = create_session(
        method="cloudscraper" if CLOUDSCRAPER_AVAILABLE else "requests",
        cookies=cookies
    )

    # Test the session to ensure it works
    try:
        response = session.get(site_url, timeout=10)
        if detect_cloudflare(response):
            logger.warning("Cookies didn't bypass Cloudflare. Getting fresh cookies...")
            cookies = get_cf_cookies(site_url, method=method)
            if cookies:
                save_cookies(cookies, cookie_file)
                # Recreate session with new cookies
                session = create_session(
                    method="cloudscraper" if CLOUDSCRAPER_AVAILABLE else "requests",
                    cookies=cookies
                )
    except Exception as e:
        logger.error(f"Error testing session: {str(e)}")

    return session


if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test cookie generation
    print("Testing Cloudflare bypass...")

    # Test URL (Books-A-Million)
    test_url = "https://www.booksamillion.com"

    # Try to get cookies
    cookies = get_cf_cookies(test_url)

    # Print results
    if cookies:
        print(f"Successfully obtained {len(cookies)} cookies:")
        for name, value in cookies.items():
            print(f"  {name}: {value[:10]}..." if len(value) > 10 else f"  {name}: {value}")
    else:
        print("Failed to obtain cookies")

    # Test session creation
    session = get_bypass_session(test_url)

    # Test the session
    try:
        response = session.get(test_url)
        print(f"Test request status code: {response.status_code}")
        if detect_cloudflare(response):
            print("WARNING: Cloudflare still detected")
        else:
            print("Success: Cloudflare bypassed!")
    except Exception as e:
        print(f"Error testing session: {e}")