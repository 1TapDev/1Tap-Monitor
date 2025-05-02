#!/usr/bin/env python3
"""
Request Logger Utility
Provides functions for logging HTTP requests and responses
"""

import os
import json
import time
import logging
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

    def ensure_log_dir(self):
        """Create log directory if it doesn't exist"""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_request(self, url: str, method: str = "GET", headers: Optional[Dict] = None,
                    data: Any = None, params: Optional[Dict] = None, timestamp: Optional[float] = None,
                    response: Any = None, response_headers: Optional[Dict] = None,
                    status_code: Optional[int] = None, response_text: Optional[str] = None,
                    error: Optional[str] = None):
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
        """
        if timestamp is None:
            timestamp = time.time()

        # Create a unique filename
        timestamp_str = time.strftime("%Y%m%d-%H%M%S", time.localtime(timestamp))
        url_part = url.split("//")[-1].replace("/", "_").replace("?", "_").replace("&", "_")[:50]
        filename = f"{timestamp_str}_{method}_{url_part}.log"
        filepath = self.log_dir / filename

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

            logger.info(f"Logged request to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to log request: {str(e)}")
            return None

    def log_from_response(self, url: str, method: str, headers: Dict,
                          params: Optional[Dict] = None, data: Any = None,
                          response=None, error: Optional[str] = None):
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
        """
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
            error=error
        )

    def save_readable_response(self, response, filepath):
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