#!/usr/bin/env python3
"""
Request Logger Utility
Provides functions for logging HTTP requests and responses with rotation support
"""

import os
import json
import time
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional
import pprint

logger = logging.getLogger("RequestLogger")


class RequestLogger:
    """
    Utility class for logging HTTP requests and responses
    """

    def __init__(self, log_dir: str = "logs/requests"):
        """
        Initialize the request logger

        Args:
            log_dir: Directory to store request logs
        """
        self.log_dir = Path(log_dir)
        self.ensure_log_dir()
        self.rotator = None
        self.max_bytes = 0
        self.backup_count = 0
        self.enabled = True
        self.save_readable = False

    def ensure_log_dir(self):
        """Create log directory if it doesn't exist"""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def enable_log_rotation(self, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3):
        """
        Enable log file rotation

        Args:
            max_bytes: Maximum bytes per file before rotation
            backup_count: Number of backup files to keep
        """
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        logger.info(f"Enabled log rotation: max_bytes={max_bytes}, backup_count={backup_count}")

    def _should_rotate_log(self, filepath: Path) -> bool:
        """
        Check if a log file should be rotated

        Args:
            filepath: Path to the log file

        Returns:
            bool: True if file should be rotated
        """
        if not self.max_bytes:
            return False

        if not filepath.exists():
            return False

        return filepath.stat().st_size >= self.max_bytes

    def _rotate_log(self, filepath: Path):
        """
        Rotate a log file

        Args:
            filepath: Path to the log file
        """
        if not self.backup_count:
            return

        # Check for existing backups and remove oldest if needed
        backups = sorted([
            p for p in filepath.parent.glob(f"{filepath.name}.?")
            if p.name.startswith(filepath.name + ".")
        ], reverse=True)

        # Remove oldest backup if we have too many
        if len(backups) >= self.backup_count:
            try:
                max_backup = filepath.with_suffix(f".{self.backup_count}")
                if max_backup.exists():
                    max_backup.unlink()
            except Exception as e:
                logger.error(f"Error removing old backup: {str(e)}")

        # Rotate existing backups
        for i in range(self.backup_count - 1, 0, -1):
            src = filepath.with_suffix(f".{i}")
            dst = filepath.with_suffix(f".{i + 1}")
            if src.exists():
                try:
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
                except Exception as e:
                    logger.error(f"Error rotating backup {i} to {i + 1}: {str(e)}")

        # Rename current file to .1
        try:
            backup1 = filepath.with_suffix(".1")
            if backup1.exists():
                backup1.unlink()
            filepath.rename(backup1)
        except Exception as e:
            logger.error(f"Error rotating current file to .1: {str(e)}")

    def log_request(self, url: str, method: str = "GET", headers: Optional[Dict] = None,
                    data: Any = None, params: Optional[Dict] = None, timestamp: Optional[float] = None,
                    response: Any = None, response_headers: Optional[Dict] = None,
                    status_code: Optional[int] = None, response_text: Optional[str] = None,
                    error: Optional[str] = None, log_filename: Optional[str] = None):
        """
        Log a request and its response

        Args:
            url: Request URL
            method: HTTP method
            headers: Request headers
            data: Request body
            params: Request parameters
            timestamp: Request timestamp
            response: Response object (optional)
            response_headers: Response headers (optional)
            status_code: Response status code (optional)
            response_text: Response text (optional)
            error: Error message if request failed (optional)
            log_filename: Optional custom filename for the log (instead of URL-based)
        """
        if not self.enabled:
            return None

        if timestamp is None:
            timestamp = time.time()

        # Create a unique filename
        timestamp_str = time.strftime("%Y%m%d-%H%M%S", time.localtime(timestamp))

        if log_filename:
            # Use custom filename if provided (useful for PID-based logs)
            filename = f"{timestamp_str}_{method}_{log_filename}"
        else:
            # Create URL-based filename
            url_part = url.split("//")[-1].replace("/", "_").replace("?", "_").replace("&", "_")[:50]
            filename = f"{timestamp_str}_{method}_{url_part}.log"

        filepath = self.log_dir / filename

        # Check if we need to rotate the log
        if self._should_rotate_log(filepath):
            self._rotate_log(filepath)

        # Build log content
        log_content = {
            "request": {
                "url": url,
                "method": method,
                "headers": headers,
                "data": data,
                "params": params,
                "timestamp": timestamp,
                "timestamp_readable": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
            },
            "response": {
                "status_code": status_code,
                "headers": response_headers,
                "error": error
            }
        }

        # Write log file
        try:
            with open(filepath, "w") as f:
                f.write(f"===== REQUEST: {url} =====\n")
                f.write(f"Method: {method}\n")
                f.write(f"Timestamp: {log_content['request']['timestamp_readable']}\n")
                f.write("\n----- Request Headers -----\n")
                if headers:
                    f.write(pprint.pformat(headers, indent=2))
                f.write("\n\n----- Request Parameters -----\n")
                if params:
                    f.write(pprint.pformat(params, indent=2))
                f.write("\n\n----- Request Data -----\n")
                if data:
                    if isinstance(data, (dict, list)):
                        f.write(pprint.pformat(data, indent=2))
                    else:
                        f.write(str(data))

                f.write("\n\n===== RESPONSE =====\n")
                f.write(f"Status Code: {status_code}\n")
                f.write("\n----- Response Headers -----\n")
                if response_headers:
                    f.write(pprint.pformat(response_headers, indent=2))

                f.write("\n\n----- Response Body -----\n")
                if response_text:
                    # Check if response is valid JSON
                    try:
                        json_data = json.loads(response_text)
                        f.write(json.dumps(json_data, indent=2))
                    except:
                        # Just write the raw text
                        f.write(response_text[:10000])  # Limit to 10K chars
                        if len(response_text) > 10000:
                            f.write("\n... (truncated)")
                elif error:
                    f.write(f"ERROR: {error}")

            logger.debug(f"Logged request to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to log request: {str(e)}")
            return None

    def log_from_response(self, url: str, method: str, headers: Dict,
                          params: Optional[Dict] = None, data: Any = None,
                          response=None, error: Optional[str] = None,
                          log_filename: Optional[str] = None):
        """
        Log a request and response from a requests.Response object

        Args:
            url: Request URL
            method: HTTP method
            headers: Request headers
            params: Request parameters
            data: Request body
            response: Response object
            error: Error message if request failed
            log_filename: Optional custom filename for the log
        """
        if not self.enabled:
            return None

        response_headers = None
        status_code = None
        response_text = None

        if response:
            try:
                response_headers = dict(response.headers)
                status_code = response.status_code
                response_text = response.text
            except Exception as e:
                logger.error(f"Error extracting response data: {str(e)}")

        return self.log_request(
            url=url,
            method=method,
            headers=headers,
            params=params,
            data=data,
            response_headers=response_headers,
            status_code=status_code,
            response_text=response_text,
            error=error,
            log_filename=log_filename
        )

    def save_readable_response(self, response, filepath):
        """Save response in a human-readable format"""
        if not self.enabled or not self.save_readable:
            return False

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Status: {response.status_code}\n\n")
                f.write("Headers:\n")
                for key, value in response.headers.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n\nBody:\n")

                # Try to prettify JSON
                try:
                    json_data = response.json()
                    f.write(json.dumps(json_data, indent=2))
                except:
                    # Not JSON, just write the text
                    f.write(response.text)

            return True
        except Exception as e:
            logger.error(f"Failed to save readable response: {str(e)}")
            return False


def save_readable_response(response, filepath):
    """Save response in a human-readable format"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Status: {response.status_code}\n\n")
            f.write("Headers:\n")
            for key, value in response.headers.items():
                f.write(f"{key}: {value}\n")
            f.write("\n\nBody:\n")

            # Try to prettify JSON
            try:
                json_data = response.json()
                f.write(json.dumps(json_data, indent=2))
            except:
                # Not JSON, just write the text
                f.write(response.text)

        return True
    except Exception as e:
        logger.error(f"Failed to save readable response: {str(e)}")
        return False


# Global instance for easy import
request_logger = RequestLogger()


# Function to get the logger instance
def get_request_logger():
    return request_logger