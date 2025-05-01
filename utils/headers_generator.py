#!/usr/bin/env python3
"""
Headers Generator
Utility functions for generating browser-like HTTP headers.
"""

import random
import platform
from typing import Dict, List, Optional

# List of common user agents
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",

    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0",

    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",

    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",

    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36 Edg/92.0.902.55"
]


def get_random_user_agent() -> str:
    """
    Get a random user agent string

    Returns:
        str: User agent string
    """
    return random.choice(USER_AGENTS)


def generate_headers(referer: Optional[str] = None,
                     accept_language: str = "en-US,en;q=0.9",
                     custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Generate a set of browser-like headers

    Args:
        referer: Optional referer URL
        accept_language: Accept-Language header value
        custom_headers: Additional headers to include

    Returns:
        Dict of HTTP headers
    """
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }

    # Add referer if provided
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"

    # Add custom headers if provided
    if custom_headers:
        headers.update(custom_headers)

    return headers


def generate_mobile_headers(referer: Optional[str] = None,
                            accept_language: str = "en-US,en;q=0.9",
                            custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Generate a set of mobile browser-like headers

    Args:
        referer: Optional referer URL
        accept_language: Accept-Language header value
        custom_headers: Additional headers to include

    Returns:
        Dict of HTTP headers
    """
    mobile_user_agents = [
        # iOS Safari
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",

        # Android Chrome
        "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.210 Mobile Safari/537.36"
    ]

    headers = {
        "User-Agent": random.choice(mobile_user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    # Add referer if provided
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"

    # Add custom headers if provided
    if custom_headers:
        headers.update(custom_headers)

    return headers


def generate_chrome_headers(version: Optional[str] = None,
                            os_type: Optional[str] = None,
                            referer: Optional[str] = None) -> Dict[str, str]:
    """
    Generate headers specifically for Chrome browser

    Args:
        version: Chrome version (e.g., '91.0.4472.124')
        os_type: Operating system ('windows', 'macos', 'linux')
        referer: Optional referer URL

    Returns:
        Dict of HTTP headers
    """
    # Determine OS string
    if not os_type:
        system = platform.system().lower()
        if system == 'windows':
            os_type = 'windows'
        elif system == 'darwin':
            os_type = 'macos'
        else:
            os_type = 'linux'

    # Generate OS part of user agent
    if os_type == 'windows':
        os_string = "Windows NT 10.0; Win64; x64"
    elif os_type == 'macos':
        os_string = "Macintosh; Intel Mac OS X 10_15_7"
    else:  # linux
        os_string = "X11; Linux x86_64"

    # Use provided version or a default
    chrome_version = version or "92.0.4515.107"

    user_agent = f"Mozilla/5.0 ({os_string}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Ch-Ua": f'"Chromium";v="{chrome_version.split(".")[0]}", "Google Chrome";v="{chrome_version.split(".")[0]}"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": f'"{os_type.capitalize()}"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }

    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"

    return headers


if __name__ == "__main__":
    # Demo usage
    print("Random User Agent:", get_random_user_agent())
    print("\nGeneric Headers:")
    for k, v in generate_headers().items():
        print(f"  {k}: {v}")

    print("\nChrome Headers:")
    for k, v in generate_chrome_headers().items():
        print(f"  {k}: {v}")