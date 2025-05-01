#!/usr/bin/env python3
"""
Logger Utility Module
Provides consistent logging functionality for all modules.
"""

import os
import logging
import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Define log levels
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def setup_logger(name: str,
                 log_level: str = 'INFO',
                 log_file: Optional[str] = None,
                 module_specific: bool = False) -> logging.Logger:
    """
    Set up a logger with consistent formatting.

    Args:
        name: Name of the logger
        log_level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_file: Optional log file path
        module_specific: Whether this is a module-specific logger

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist and log_file is specified
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

    # Create logger
    logger = logging.getLogger(name)

    # Check if logger already has handlers to avoid duplicate logs
    if logger.handlers:
        return logger

    # Set log level
    level = LOG_LEVELS.get(log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Create formatters
    console_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    if module_specific:
        console_format = '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
        file_format = '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'

    console_formatter = logging.Formatter(console_format)
    file_formatter = logging.Formatter(file_format)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Create file handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_module_logger(module_name: str) -> logging.Logger:
    """
    Get a logger specifically for a website module.

    Args:
        module_name: Name of the module

    Returns:
        logging.Logger: Module logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    if not logs_dir.exists():
        logs_dir.mkdir()

    # Create module-specific log file
    log_file = logs_dir / f"{module_name}.log"

    return setup_logger(
        name=f"Module.{module_name}",
        log_level='INFO',
        log_file=str(log_file),
        module_specific=True
    )


def log_request(logger: logging.Logger,
                method: str,
                url: str,
                status_code: Optional[int] = None,
                elapsed: Optional[float] = None,
                error: Optional[str] = None) -> None:
    """
    Log HTTP request details.

    Args:
        logger: Logger instance
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        status_code: Optional response status code
        elapsed: Optional request elapsed time in seconds
        error: Optional error message
    """
    if error:
        logger.error(f"{method} {url} - Error: {error}")
    elif status_code:
        elapsed_str = f" ({elapsed:.2f}s)" if elapsed is not None else ""

        if 200 <= status_code < 300:
            logger.info(f"{method} {url} - {status_code}{elapsed_str}")
        elif 300 <= status_code < 400:
            logger.info(f"{method} {url} - {status_code} (Redirect){elapsed_str}")
        elif 400 <= status_code < 500:
            logger.warning(f"{method} {url} - {status_code} (Client Error){elapsed_str}")
        elif 500 <= status_code < 600:
            logger.error(f"{method} {url} - {status_code} (Server Error){elapsed_str}")
        else:
            logger.warning(f"{method} {url} - {status_code} (Unknown Status){elapsed_str}")
    else:
        logger.debug(f"{method} {url} - Request sent")


class RequestLogger:
    """Helper class to log requests and responses."""

    def __init__(self, logger: logging.Logger):
        """
        Initialize the request logger.

        Args:
            logger: Logger instance to use
        """
        self.logger = logger

    def log_request_start(self, method: str, url: str, headers: Optional[Dict[str, str]] = None) -> None:
        """
        Log request start.

        Args:
            method: HTTP method
            url: Request URL
            headers: Optional request headers
        """
        self.logger.debug(f">> {method} {url}")
        if headers and self.logger.level <= logging.DEBUG:
            for key, value in headers.items():
                if key.lower() in ('authorization', 'cookie'):
                    # Redact sensitive header values
                    self.logger.debug(f">> {key}: [REDACTED]")
                else:
                    self.logger.debug(f">> {key}: {value}")

    def log_request_complete(self, method: str, url: str, status_code: int, elapsed: float) -> None:
        """
        Log request completion.

        Args:
            method: HTTP method
            url: Request URL
            status_code: Response status code
            elapsed: Request elapsed time in seconds
        """
        log_request(self.logger, method, url, status_code=status_code, elapsed=elapsed)

    def log_request_error(self, method: str, url: str, error: str) -> None:
        """
        Log request error.

        Args:
            method: HTTP method
            url: Request URL
            error: Error message
        """
        log_request(self.logger, method, url, error=error)