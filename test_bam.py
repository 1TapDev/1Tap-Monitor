#!/usr/bin/env python3
"""
Test script for Booksamillion with debugging
"""

import logging
import json
from pathlib import Path
from modules.booksamillion import Booksamillion

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)
Path("logs/requests").mkdir(exist_ok=True)
Path("logs/responses").mkdir(exist_ok=True)

# Initialize the module
bam = Booksamillion()

# Test cookie generation
bam.refresh_session()

# Test stock check with a known PID
test_pid = "9798400902550"  # Solo Leveling Vol. 11

result = bam.check_stock(test_pid)
print(f"Stock check result for {test_pid}:")
print(json.dumps(result, indent=2))

# Print log locations
print("\nPlease check these locations for detailed logs:")
print("- Request logs: logs/requests/")
print("- Response logs: logs/responses/")