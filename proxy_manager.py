#!/usr/bin/env python3
"""
Proxy Manager Module
Handles loading and rotating proxies for web requests.
"""

import os
import random
import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("ProxyManager")


class ProxyManager:
    """
    Loads and manages HTTP proxies for web scraping.
    Supports ip:port:user:pass format from a text file.
    """

    def __init__(self, proxy_file: str = 'proxies.txt'):
        """
        Initialize the proxy manager

        Args:
            proxy_file: Path to the file containing proxies
        """
        self.proxy_file = proxy_file
        self.proxies = []  # List of all proxies
        self.working_proxies = []  # List of currently working proxies
        self.failed_proxies = {}  # Dict mapping failed proxies to timestamps
        self.current_index = 0
        self.retry_interval = 600  # Retry failed proxies after 10 minutes

        # Load proxies on initialization
        self.reload_proxies()

    def reload_proxies(self) -> int:
        """
        Reload proxies from the proxy file

        Returns:
            int: Number of proxies loaded
        """
        self.proxies = []

        try:
            if not os.path.exists(self.proxy_file):
                logger.warning(f"Proxy file not found: {self.proxy_file}")
                return 0

            with open(self.proxy_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.proxies.append(line)

            # Reset the working proxies list
            self.working_proxies = self.proxies.copy()
            logger.info(f"Loaded {len(self.proxies)} proxies from {self.proxy_file}")
            return len(self.proxies)

        except Exception as e:
            logger.error(f"Error loading proxies: {str(e)}")
            return 0

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        Get the next proxy in rotation format required by requests library

        Returns:
            Dict with 'http' and 'https' keys, or None if no proxies available
        """
        if not self.working_proxies:
            # Try to restore failed proxies that have waited long enough
            self._restore_failed_proxies()

            if not self.working_proxies:
                logger.warning("No working proxies available")
                return None

        # Get the next proxy in rotation
        proxy_str = self.working_proxies[self.current_index]

        # Update the index for next time
        self.current_index = (self.current_index + 1) % len(self.working_proxies)

        # Convert the proxy string to the format expected by requests
        return self._format_proxy(proxy_str)

    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """
        Get a random proxy from the working proxies

        Returns:
            Dict with 'http' and 'https' keys, or None if no proxies available
        """
        if not self.working_proxies:
            # Try to restore failed proxies that have waited long enough
            self._restore_failed_proxies()

            if not self.working_proxies:
                logger.warning("No working proxies available")
                return None

        # Get a random proxy
        proxy_str = random.choice(self.working_proxies)

        # Convert the proxy string to the format expected by requests
        return self._format_proxy(proxy_str)

    def report_proxy_failure(self, proxy_dict: Dict[str, str]) -> None:
        """
        Report a proxy as failed so it won't be used for a while

        Args:
            proxy_dict: The proxy dict that failed
        """
        # Convert the proxy dict back to string representation
        proxy_url = proxy_dict.get('http', '').replace('http://', '')

        # Find and remove the proxy from working list
        for proxy in list(self.working_proxies):
            if proxy_url in proxy:
                self.working_proxies.remove(proxy)
                self.failed_proxies[proxy] = time.time()
                logger.info(f"Marked proxy as failed: {proxy}")
                break

    def _restore_failed_proxies(self) -> int:
        """
        Restore failed proxies that have waited long enough

        Returns:
            int: Number of proxies restored
        """
        current_time = time.time()
        restored = 0

        for proxy, failed_time in list(self.failed_proxies.items()):
            if current_time - failed_time > self.retry_interval:
                self.working_proxies.append(proxy)
                del self.failed_proxies[proxy]
                restored += 1

        if restored > 0:
            logger.info(f"Restored {restored} proxies back to working pool")

        return restored

    def _format_proxy(self, proxy_str: str) -> Dict[str, str]:
        """
        Format a proxy string into a dictionary format for requests

        Args:
            proxy_str: Proxy string in format ip:port:user:pass or ip:port

        Returns:
            Dict with 'http' and 'https' keys
        """
        parts = proxy_str.split(':')

        if len(parts) == 2:
            # Format: ip:port
            host, port = parts
            proxy_url = f"http://{host}:{port}"
        elif len(parts) == 4:
            # Format: ip:port:user:pass
            host, port, user, password = parts
            proxy_url = f"http://{user}:{password}@{host}:{port}"
        else:
            logger.warning(f"Invalid proxy format: {proxy_str}")
            return {}

        return {
            'http': proxy_url,
            'https': proxy_url
        }

    def get_stats(self) -> Tuple[int, int, int]:
        """
        Get statistics about the proxy pool

        Returns:
            Tuple of (total proxies, working proxies, failed proxies)
        """
        return len(self.proxies), len(self.working_proxies), len(self.failed_proxies)