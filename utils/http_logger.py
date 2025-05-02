#!/usr/bin/env python3
"""
HTTP Logger Utility with Decompression Support
Logs complete HTTP requests and responses in a clear text format
"""

import time
import logging
import brotli  # You'll need to install this: pip install brotli
import gzip
import zlib
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("HTTPLogger")


class HTTPLogger:
    """
    Utility class for logging complete HTTP transactions
    """

    def __init__(self, log_dir: str = "logs/http"):
        """
        Initialize the HTTP logger

        Args:
            log_dir: Directory to store HTTP logs
        """
        self.log_dir = Path(log_dir)
        self.ensure_log_dir()

    def ensure_log_dir(self):
        """Create log directory if it doesn't exist"""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def decompress_response(self, response):
        """
        Decompress response content based on Content-Encoding header

        Args:
            response: Response object

        Returns:
            Decompressed content as string
        """
        content = response.content
        encoding = response.headers.get('Content-Encoding', '').lower()

        try:
            if 'br' in encoding:
                # Brotli decompression
                content = brotli.decompress(content)
            elif 'gzip' in encoding:
                # Gzip decompression
                content = gzip.decompress(content)
            elif 'deflate' in encoding:
                # Zlib decompression
                content = zlib.decompress(content)

            # Convert bytes to string
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                # Try other encodings if UTF-8 fails
                return content.decode('latin-1')
        except Exception as e:
            logger.error(f"Failed to decompress response: {str(e)}")
            return f"[Error decompressing response: {str(e)}]"

    def log_transaction(self, request_url: str, request_method: str,
                        request_headers: Dict, response=None,
                        request_body: Any = None, pid: str = None):
        """
        Log a complete HTTP transaction in plain text format

        Args:
            request_url: The request URL
            request_method: HTTP method used
            request_headers: Request headers
            response: Response object
            request_body: Request body (optional)
            pid: Product ID (for filename)
        """
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}_{request_method}"

        if pid:
            filename += f"_{pid}.txt"
        else:
            # Clean up the URL for filename
            url_part = request_url.split('/')[-1].split('?')[0]
            if not url_part:
                url_part = 'index'
            filename += f"_{url_part}.txt"

        filepath = self.log_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                # Write request section
                f.write(f"{request_method} {request_url} HTTP/1.1\n")

                # Write request headers
                for header_name, header_value in request_headers.items():
                    f.write(f"{header_name}: {header_value}\n")

                # Add blank line after headers
                f.write("\n")

                # Write request body if present
                if request_body:
                    f.write(str(request_body))
                    f.write("\n\n")

                # Write response if available
                if response:
                    f.write("\n")
                    f.write(f"HTTP/1.1 {response.status_code} {response.reason}\n")

                    # Write response headers
                    for header_name, header_value in response.headers.items():
                        f.write(f"{header_name}: {header_value}\n")

                    # Add blank line after headers
                    f.write("\n")

                    # Write decompressed response body
                    decompressed_content = self.decompress_response(response)
                    f.write(decompressed_content)

            logger.info(f"HTTP transaction logged to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to log HTTP transaction: {str(e)}")
            return None


# Global instance
http_logger = HTTPLogger()


def get_http_logger():
    """Get the global HTTP logger instance"""
    return http_logger