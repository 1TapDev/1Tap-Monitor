#!/usr/bin/env python3
"""
Bypass Utility Module
Provides helper functions for bypassing anti-bot protections.
"""

import random
import time
import logging
import json
from typing import Dict, Any, Optional, Tuple, List, Union

import requests

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

from utils.headers import get_default_headers

logger = logging.getLogger("BypassUtils")


def get_client_session(client_type: str = "requests",
                       browser: str = "chrome_110",
                       headers: Optional[Dict[str, str]] = None) -> Any:
    """
    Get a client session object based on the specified type.

    Args:
        client_type: Type of client to create ("requests", "cloudscraper", or "tls_client")
        browser: Browser profile for tls_client (if used)
        headers: Optional headers to set on the session

    Returns:
        Session object
    """
    client_headers = headers or get_default_headers()

    if client_type == "cloudscraper":
        if not CLOUDSCRAPER_AVAILABLE:
            logger.warning("cloudscraper not installed, falling back to requests")
            session = requests.Session()
        else:
            session = cloudscraper.create_scraper()
    elif client_type == "tls_client":
        if not TLS_CLIENT_AVAILABLE:
            logger.warning("tls_client not installed, falling back to requests")
            session = requests.Session()
        else:
            session = tls_client.Session(client_identifier=browser)
    else:
        session = requests.Session()

    # Set default headers
    session.headers.update(client_headers)

    return session


def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    Sleep for a random amount of time to avoid detection.

    Args:
        min_seconds: Minimum number of seconds to sleep
        max_seconds: Maximum number of seconds to sleep
    """
    sleep_time = random.uniform(min_seconds, max_seconds)
    time.sleep(sleep_time)


def extract_cookies_from_response(response: requests.Response) -> Dict[str, str]:
    """
    Extract cookies from a response object as a dictionary.

    Args:
        response: Response object from requests/cloudscraper

    Returns:
        Dict[str, str]: Dictionary of cookies
    """
    cookies = {}
    for name, value in response.cookies.items():
        cookies[name] = value
    return cookies


def cookies_to_string(cookies: Dict[str, str]) -> str:
    """
    Convert a dictionary of cookies to a cookie header string.

    Args:
        cookies: Dictionary of cookies

    Returns:
        str: Cookie header string
    """
    return "; ".join([f"{name}={value}" for name, value in cookies.items()])


def rotate_user_agent(session: Any) -> str:
    """
    Rotate the user agent of a session.

    Args:
        session: Session object (requests, cloudscraper, etc.)

    Returns:
        str: New user agent
    """
    from utils.headers import get_random_user_agent
    new_agent = get_random_user_agent()
    session.headers["User-Agent"] = new_agent
    return new_agent


def solve_cloudflare(url: str,
                     proxies: Optional[Dict[str, str]] = None,
                     timeout: int = 30) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    Attempt to solve Cloudflare protection and get cookies.

    Args:
        url: URL protected by Cloudflare
        proxies: Optional proxies dictionary
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, cookies)
    """
    if not CLOUDSCRAPER_AVAILABLE:
        logger.error("cloudscraper not installed, cannot solve Cloudflare")
        return False, None

    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

        # Set proxies if provided
        if proxies:
            scraper.proxies = proxies

        # Try to access the site
        response = scraper.get(url, timeout=timeout)

        if response.status_code == 200:
            cookies = extract_cookies_from_response(response)
            return True, cookies
        else:
            logger.warning(f"Failed to solve Cloudflare, status code: {response.status_code}")
            return False, None

    except Exception as e:
        logger.error(f"Error solving Cloudflare: {str(e)}")
        return False, None


def parse_json_with_fallback(content: Union[str, bytes]) -> Optional[Dict[str, Any]]:
    """
    Attempt to parse JSON with fallback options if standard parsing fails.

    Args:
        content: JSON content as string or bytes

    Returns:
        Dict if parsing successful, None otherwise
    """
    if isinstance(content, bytes):
        try:
            content = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                # Try different encoding
                content = content.decode('latin-1')
            except Exception:
                logger.error("Failed to decode response content")
                return None

    # First, try standard JSON parsing
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Second, try fixing common JSON issues
    try:
        # Fix single quotes to double quotes
        fixed_content = content.replace("'", "\"")
        return json.loads(fixed_content)
    except json.JSONDecodeError:
        pass

    # Try handling JavaScript-style JSON with extra comma
    try:
        # Remove trailing commas in objects
        import re
        fixed_content = re.sub(r',\s*}', '}', content)
        fixed_content = re.sub(r',\s*]', ']', fixed_content)
        return json.loads(fixed_content)
    except (json.JSONDecodeError, Exception):
        logger.error("Failed to parse JSON content")
        return None


def get_challenge_answer(challenge_type: str, data: Any) -> Optional[str]:
    """
    Solve common JavaScript challenges.

    Args:
        challenge_type: Type of challenge ("math", "string", etc.)
        data: Challenge data

    Returns:
        str: Challenge answer or None if unsolvable
    """
    try:
        if challenge_type == "math":
            # Example: Solve a math expression
            if isinstance(data, str):
                # Replace common JavaScript math functions
                data = data.replace("Math.floor", "int")
                data = data.replace("Math.ceil", "lambda x: int(x) + (1 if x > int(x) else 0)")
                data = data.replace("Math.round", "round")

                # Evaluate the expression
                return str(eval(data))

        elif challenge_type == "string":
            # Example: String manipulation
            if isinstance(data, list) and len(data) == 3:
                operation, string, param = data

                if operation == "substring":
                    start, end = param
                    return string[start:end]
                elif operation == "replace":
                    old, new = param
                    return string.replace(old, new)
                elif operation == "charAt":
                    return string[param]

        return None

    except Exception as e:
        logger.error(f"Error solving challenge: {str(e)}")
        return None