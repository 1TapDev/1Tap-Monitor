# Stock Checker System

A modular Python system for checking stock across multiple retail websites and sending alerts via Discord webhooks.

## Features

- **Modular Design**: Each retailer is a separate module that can be enabled/disabled independently
- **Multi-threaded**: Runs modules concurrently to check multiple sites
- **Proxy Support**: Rotates through proxies listed in `proxies.txt`
- **Cloudflare Bypass**: Handles anti-bot protections using various bypass methods
- **Discord Alerts**: Sends notifications when new items are found or stock status changes
- **Hot Reload**: Uses `importlib.reload()` to update modules without restarting
- **GUI & CLI**: Control the system via a Tkinter GUI or command line interface
- **Database Support**: Optional PostgreSQL or SQLite for persistent storage

## Module Structure

Each retailer module follows a common interface:

```
modules/
├── booksamillion.py    # Books-A-Million stock checker
├── popshelf.py         # Pop Shelf stock checker
└── ...                 # Additional retailer modules
```

## Core Components

- `main.py`: Initializes the system and provides the CLI/GUI interface
- `dispatcher.py`: Loads modules, handles threading
- `notifier.py`: Sends messages to Discord via webhook
- `proxy_manager.py`: Reads proxies and returns a rotating one
- `utils/`: Shared tools (headers, bypass tools, logging)

## Books-A-Million Module

The `booksamillion.py` module demonstrates the architecture and follows these steps:

1. **Cloudflare Bypass**: Uses browser automation or specialized libraries to handle anti-bot protections
2. **Search for Items**: Scans search pages for new product IDs
3. **Stock Checking**: Queries availability of known products across multiple stores
4. **Notifications**: Sends Discord alerts for new products and stock changes

### Key Components:

- `get_fresh_cookies()`: Obtains new Cloudflare cookies when necessary
- `check_stock(pid)`: Checks inventory for a specific product ID
- `scan_new_items()`: Searches for new products to monitor
- `main_monitor_loop()`: Runs the monitoring process continually

## Database Support

The system supports both PostgreSQL and SQLite for persistent storage:

- `database/schema.sql`: PostgreSQL database schema
- `utils/database.py`: Database abstraction layer that works with both DB types

## Utility Modules

- `utils/cloudflare_bypass.py`: Handles Cloudflare anti-bot protections
- `utils/headers_generator.py`: Creates realistic browser-like headers
- `utils/html_parser.py`: Parses retail websites to extract product info

## Configuration

Each module has its own configuration file:

```json
{
    "name": "Books-A-Million",
    "enabled": true,
    "interval": 900,
    "search_radius": 250,
    "keywords": ["exclusive", "limited edition", "pokemon"],
    "search_urls": [
        "https://www.booksamillion.com/search2?query=..."
    ]
}
```

## Usage

### CLI Mode

```bash
python main.py
```

Commands:
- `list`: Show all modules
- `start <module>`: Start a specific module
- `stop <module>`: Stop a specific module
- `status`: Show current status
- `reload <module>`: Hot reload a module

### GUI Mode

```bash
python main.py --gui
```

The GUI provides:
- Module management (start/stop/reload)
- Real-time logs
- Configuration editor

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `proxies.txt` file with your proxies (format: `ip:port:user:pass`)
4. Configure your Discord webhook URL in `config.json`
5. Run the application:
   ```bash
   python main.py
   ```

## Adding New Modules

To add a new retailer module:

1. Create a new file in the `modules/` directory
2. Implement the required interface:
   - `NAME`: Module name
   - `VERSION`: Module version
   - `INTERVAL`: Default check interval in seconds
   - `check_stock(pid, proxy=None)`: Check stock function
   - `scan_new_items(proxy=None)`: Search for new products
   - `main_monitor_loop(proxy_manager, notifier)`: Main monitoring loop

3. Create a configuration file for your module (e.g., `config_newmodule.json`)
4. The system will automatically detect and load your module

## Project Directory Structure

```
project/
│
├── modules/                  # Website-specific logic
│   ├── booksamillion.py      # Books-A-Million module
│   ├── popshelf.py           # Pop Shelf module (Add your own modules here)
│   └── ...
│
├── utils/                    # Shared tools
│   ├── cloudflare_bypass.py  # Cloudflare/anti-bot bypass methods
│   ├── database.py           # Database abstraction layer
│   ├── headers_generator.py  # Browser-like HTTP headers
│   └── html_parser.py        # HTML parsing utilities
│
├── database/                 # Database schemas
│   └── schema.sql            # PostgreSQL schema
│
├── config.json               # Global configuration
├── config_booksamillion.json # Module-specific config
├── proxies.txt               # ip:port:user:pass proxy list
│
├── main.py                   # Main application entry point
├── dispatcher.py             # Module loader and thread manager
├── notifier.py               # Discord webhook notifications
├── proxy_manager.py          # Proxy rotation system
│
└── data/                     # Data storage directory
    ├── booksamillion_cookies.json   # Cached cookies
    └── booksamillion_products.json  # Cached product data
```

## BooksMillion Module Details

### Core Functions

1. **Cloudflare Bypass**:
   - Handles anti-bot protections using three methods:
     - Selenium with undetected-chromedriver
     - CloudScraper
     - TLS Client
   - Saves cookies to avoid repeatedly solving challenges

2. **Stock Checking**:
   - Uses the store locator API to check inventory by product ID
   - Searches stores within a configurable radius
   - Tracks availability history across multiple stores

3. **Product Discovery**:
   - Scans search results pages for new items
   - Extracts product details (title, price, image, etc.)
   - Monitors specific product URLs and keywords

### Technical Details

- **HTTP Requests**:
  - Uses a specialized session with anti-bot capabilities
  - Rotates user agents and headers to avoid detection
  - Implements exponential backoff retry strategy

- **Data Storage**:
  - Supports both file-based and database storage
  - Tracks product history for trend analysis
  - Maintains cookie cache to reduce challenge solving

- **Notification System**:
  - Sends rich Discord embeds with product information
  - Includes direct links to product pages
  - Differentiates between new products and stock changes

## Advanced Features

### Proxy Management

The system rotates through a list of proxies to avoid IP-based rate limiting:

```
123.45.67.89:8080:user:password
98.76.54.32:3128:user:password
...
```

Proxies are tracked for success/failure rates and automatically disabled after repeated failures.

### Hot Module Reloading

Modules can be updated while the system is running:

```python
def reload_module(module_name):
    """Reload a module's code without restarting"""
    module_path = f'modules.{module_name}'
    if module_path in sys.modules:
        module = importlib.reload(sys.modules[module_path])
        # Reinitialize the module
        return True
    return False
```

### Task Queue System

Tasks are queued and processed based on priority:

1. High priority (8-10): New product stock checks
2. Medium priority (4-7): Regular stock checks
3. Low priority (1-3): Scanning for new products

Tasks that fail are retried with exponential backoff (1min, 2min, 4min, etc.).

## Customization

### Adding New Websites

To monitor a new website:

1. Create a new module file in `modules/`
2. Implement the required interface methods
3. Add site-specific logic for:
   - Handling anti-bot measures
   - Extracting product information
   - Checking inventory

### Custom Alert Formats

The notification system supports multiple formats:

1. **Discord**: Rich embeds with images and formatting
2. **Slack**: Uses Slack's block kit for structured messages
3. **Custom Webhooks**: Define your own payload format

## Performance Optimization

- **Concurrency Control**: Limits concurrent requests to avoid overwhelming servers
- **Caching**: Stores product data to avoid redundant checks
- **Rate Limiting**: Implements delays between requests to each domain
- **Memory Management**: Periodically cleans up cached data

## Security Considerations

- Store API keys and webhook URLs securely
- Don't share your proxy list
- Be respectful of website terms of service
- Implement reasonable rate limits

## Troubleshooting

### Common Issues

1. **Cloudflare Blocking**:
   - Try different bypass methods
   - Increase delay between requests
   - Use higher quality proxies

2. **Missing Modules**:
   - Check Python environment
   - Install required dependencies
   - Verify module file structure

3. **Discord Webhook Failures**:
   - Verify webhook URL is correct
   - Check Discord server permissions
   - Test webhook with a simple payload

### Logging

The system provides detailed logging to help diagnose issues:

```
2025-05-01 12:34:56 - BooksAMillion - INFO - Checking stock for PID: 9798400902550
2025-05-01 12:34:58 - BooksAMillion - INFO - Found 5 stores with stock available
2025-05-01 12:34:59 - Notifier - INFO - Sent alert for "Solo Leveling, Vol. 11 (Comic)"
```

Set `debug.log_level` in the configuration to control verbosity.

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch
3. Add your changes
4. Submit a pull request

Please include tests for new modules and follow the existing code style.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Be respectful of website terms of service and implement reasonable rate limits to avoid overwhelming retail websites. The authors are not responsible for misuse of this software.