#!/usr/bin/env python3
"""
Enhanced CLI for Stock Checker System
Provides a more robust command-line interface for 24/7 monitoring.
"""

import os
import sys
import time
import json
import signal
import argparse
import threading
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Add color support for terminal output
try:
    from colorama import init, Fore, Back, Style

    COLORS_AVAILABLE = True
    init()  # Initialize colorama
except ImportError:
    COLORS_AVAILABLE = False


    # Create dummy color classes
    class DummyColor:
        def __getattr__(self, name):
            return ""


    Fore = DummyColor()
    Back = DummyColor()
    Style = DummyColor()

# Import project modules
from dispatcher import ModuleDispatcher
from proxy_manager import ProxyManager
from notifier import DiscordNotifier


# Create __init__.py files if they don't exist to make proper Python packages
def ensure_package_files():
    """Ensure __init__.py files exist for proper Python package structure"""
    package_dirs = [
        '',  # Root directory
        'utils',
        'modules'
    ]

    for directory in package_dirs:
        init_file = Path(directory) / '__init__.py'
        if not init_file.exists():
            try:
                init_file.parent.mkdir(exist_ok=True)
                with open(init_file, 'w') as f:
                    f.write("# This file makes the directory a Python package\n")
                print(f"Created {init_file}")
            except Exception as e:
                print(f"Warning: Could not create {init_file}: {e}")


# Call this at startup
ensure_package_files()

try:
    from utils.config_loader import load_global_config
except ImportError:
    print(f"{Fore.RED}Error: Could not import utils.config_loader.{Style.RESET_ALL}")
    print(
        f"{Fore.YELLOW}Make sure you have utils/__init__.py file (run this script once to create it).{Style.RESET_ALL}")
    sys.exit(1)

# Global variables
running = True
status_thread = None
dispatcher = None
config = None


def load_config():
    """Load configuration from config.json"""
    try:
        global config
        config = load_global_config()

        # Ensure config has required structures
        if 'modules' not in config:
            config['modules'] = {}

        if 'booksamillion' not in config['modules']:
            config['modules']['booksamillion'] = {
                "enabled": True,
                "interval": 300  # 5 minutes
            }

        # Ensure directories exist
        for directory in ['config', 'config/modules', 'data', 'logs', 'logs/requests', 'logs/readable']:
            os.makedirs(directory, exist_ok=True)

        return config
    except Exception as e:
        print(f"{Fore.RED}Error loading configuration: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


def signal_handler(sig, frame):
    """Handle Ctrl+C and other termination signals"""
    global running
    print(f"\n{Fore.YELLOW}Shutdown signal received. Stopping all modules...{Style.RESET_ALL}")
    running = False

    if dispatcher:
        dispatcher.stop_all()

    print(f"{Fore.GREEN}Shutdown complete. Goodbye!{Style.RESET_ALL}")
    sys.exit(0)


def format_time_delta(seconds):
    """Format seconds into a readable time string"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def get_module_status_color(status):
    """Get color code for module status"""
    if not COLORS_AVAILABLE:
        return ""

    if status == "Running":
        return Fore.GREEN
    elif status == "Stopped":
        return Fore.RED
    else:
        return Fore.YELLOW


def status_display_thread():
    """Thread to continuously update status display"""
    global running
    global dispatcher

    if not dispatcher:
        return

    last_update = time.time()

    while running:
        # Clear screen and print header
        if os.name == 'nt':  # For Windows
            os.system('cls')
        else:  # For Unix/Linux/MacOS
            os.system('clear')

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = time.time() - last_update

        print(f"{Fore.CYAN}========== STOCK CHECKER STATUS - {now} =========={Style.RESET_ALL}")
        print(f"Uptime: {format_time_delta(uptime)}")
        print(f"Discord Webhook: {'Configured' if config.get('discord_webhook') else 'Not Configured'}")
        print(f"Proxy Support: {'Enabled' if config.get('use_proxies', False) else 'Disabled'}")
        print()

        # Get and display module status
        status = dispatcher.get_status()

        print(f"{Fore.CYAN}MODULE STATUS:{Style.RESET_ALL}")
        print(f"{'MODULE':<20} {'STATUS':<10} {'LAST RUN':<20} {'NEXT RUN':<20}")
        print("-" * 70)

        for module_name, details in status.items():
            module_status = details.get('status', 'Unknown')
            status_color = get_module_status_color(module_status)

            last_run = details.get('last_run', 'Never')
            next_run = details.get('next_run', 'N/A')

            print(f"{Fore.WHITE}{module_name:<20}{Style.RESET_ALL} "
                  f"{status_color}{module_status:<10}{Style.RESET_ALL} "
                  f"{last_run:<20} {next_run:<20}")

        print()
        print(f"{Fore.CYAN}COMMANDS:{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}start <module>{Style.RESET_ALL} - Start a module")
        print(f"  {Fore.WHITE}stop <module>{Style.RESET_ALL} - Stop a module")
        print(f"  {Fore.WHITE}restart <module>{Style.RESET_ALL} - Restart a module")
        print(f"  {Fore.WHITE}reload <module>{Style.RESET_ALL} - Reload module code")
        print(f"  {Fore.WHITE}status{Style.RESET_ALL} - Refresh status display")
        print(f"  {Fore.WHITE}watch{Style.RESET_ALL} - Toggle auto-refresh mode")
        print(f"  {Fore.WHITE}exit{Style.RESET_ALL} - Exit the program")
        print()

        # Brief delay before next update or exit
        time.sleep(1)


def daemon_mode():
    """Run in daemon mode without interactive input"""
    global dispatcher
    global config

    print("Starting in daemon mode...")

    # Initialize components
    proxy_manager = ProxyManager('proxies.txt') if config['use_proxies'] else None
    notifier = DiscordNotifier(config.get('discord_webhook', ''))

    # Create dispatcher
    dispatcher = ModuleDispatcher(
        notifier=notifier,
        proxy_manager=proxy_manager,
        config=config
    )

    # Discover available modules
    dispatcher.discover_modules()

    # Start enabled modules
    for module_name, module_config in config.get('modules', {}).items():
        if module_config.get('enabled', False):
            result = dispatcher.start_module(module_name)
            print(f"Module {module_name}: {result}")

    print("Daemon mode active. Press Ctrl+C to exit.")

    # Keep running until interrupted
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        dispatcher.stop_all()
        print("Daemon mode stopped.")


def interactive_mode():
    """Run in interactive mode with command input"""
    global dispatcher
    global config
    global status_thread

    print(f"{Fore.CYAN}========== STOCK CHECKER INTERACTIVE MODE =========={Style.RESET_ALL}")
    print("Initializing components...")

    # Initialize components
    proxy_manager = ProxyManager('proxies.txt') if config['use_proxies'] else None
    notifier = DiscordNotifier(config.get('discord_webhook', ''))

    # Create dispatcher
    dispatcher = ModuleDispatcher(
        notifier=notifier,
        proxy_manager=proxy_manager,
        config=config
    )

    # Discover available modules
    print("Discovering modules...")
    module_names = dispatcher.discover_modules()
    print(f"Found {len(module_names)} modules: {', '.join(module_names)}")

    # Start enabled modules
    print("Starting enabled modules...")
    for module_name, module_config in config.get('modules', {}).items():
        if module_config.get('enabled', False):
            result = dispatcher.start_module(module_name)
            print(f"  {module_name}: {result}")

    # Start status display thread
    status_thread = threading.Thread(target=status_display_thread, daemon=True)
    status_thread.start()

    # Command processing loop
    auto_refresh = False
    last_refresh = time.time()
    refresh_interval = 5  # seconds

    while running:
        try:
            # Get command from input
            command = input("\nCommand > ").strip().lower()

            if not command:
                continue

            parts = command.split()
            action = parts[0]

            if action == "exit":
                print("Shutting down...")
                dispatcher.stop_all()
                break

            elif action == "start":
                if len(parts) < 2:
                    print("Usage: start <module_name>")
                    continue

                module_name = parts[1]
                result = dispatcher.start_module(module_name)
                print(f"Module {module_name}: {result}")

            elif action == "stop":
                if len(parts) < 2:
                    print("Usage: stop <module_name>")
                    continue

                module_name = parts[1]
                result = dispatcher.stop_module(module_name)
                print(f"Module {module_name}: {result}")

            elif action == "restart":
                if len(parts) < 2:
                    print("Usage: restart <module_name>")
                    continue

                module_name = parts[1]
                dispatcher.stop_module(module_name)
                result = dispatcher.start_module(module_name)
                print(f"Module {module_name}: {result}")

            elif action == "reload":
                if len(parts) < 2:
                    print("Usage: reload <module_name>")
                    continue

                module_name = parts[1]
                result = dispatcher.reload_module(module_name)
                print(f"Module {module_name}: {result}")

            elif action == "status":
                # Manually update status display
                pass

            elif action == "watch":
                auto_refresh = not auto_refresh
                if auto_refresh:
                    print(f"{Fore.GREEN}Auto-refresh enabled. Press Enter to enter commands.{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}Auto-refresh disabled.{Style.RESET_ALL}")

            else:
                print(f"Unknown command: {action}")
                print("Available commands: start, stop, restart, reload, status, watch, exit")

        except Exception as e:
            print(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")


def create_default_configs():
    """Create default configuration files if they don't exist"""
    # Create global config
    global_config_path = Path("config/global.json")
    if not global_config_path.exists():
        global_config = {
            "discord_webhook": "https://discord.com/api/webhooks/1367540658767663274/bd5oxBHoOLun7w08zi_rQ4bkDk1ZZtocRnrU_rTmztwE2t4ilnBMs3bn3ViNkn5UTKfq",
            "check_interval": 60,
            "use_proxies": True,
            "gui_enabled": False,
            "modules": {
                "booksamillion": {
                    "enabled": True,
                    "interval": 300  # 5 minutes
                }
            }
        }

        try:
            with open(global_config_path, "w") as f:
                json.dump(global_config, f, indent=2)
            print(f"Created default global config at {global_config_path}")
        except Exception as e:
            print(f"Error creating global config: {e}")

    # Create Books-A-Million module config
    bam_config_path = Path("config/modules/booksamillion.json")
    if not bam_config_path.exists():
        bam_config = {
            "name": "Books-A-Million",
            "enabled": True,
            "interval": 300,  # 5 minutes
            "timeout": 30,
            "retry_attempts": 5,
            "search_radius": 250,
            "target_zipcode": "30135",  # Douglasville, GA
            "bypass_method": "cloudscraper",
            "cookie_file": "data/booksamillion_cookies.json",
            "product_db_file": "data/booksamillion_products.json",

            "search_urls": [
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date",
                "https://www.booksamillion.com/search2?query=The%20Pokemon%20Company%20International&filters%5Bbrand%5D=The%20Pokemon%20Company%20International&sort_by=release_date&page=2",
                "https://www.booksamillion.com/search2?query=pokemon%20cards&filters%5Bcategory%5D=Toys&sort_by=release_date"
            ],

            "pids": [
                "F820650412493",
                "F820650413315",
                "F820650859007"
            ],

            "keywords": [
                "exclusive",
                "limited edition",
                "signed",
                "pokemon",
                "special edition",
                "collector's edition"
            ],

            "webhook": {
                "enabled": True,
                "url": "https://discord.com/api/webhooks/1367540658767663274/bd5oxBHoOLun7w08zi_rQ4bkDk1ZZtocRnrU_rTmztwE2t4ilnBMs3bn3ViNkn5UTKfq",
                "format": "discord",
                "mentions": [],
                "avatar_url": "https://www.booksamillion.com/favicon.ico",
                "username": "FastBreakCards Monitors"
            }
        }

        try:
            bam_config_path.parent.mkdir(exist_ok=True, parents=True)
            with open(bam_config_path, "w") as f:
                json.dump(bam_config, f, indent=2)
            print(f"Created default Books-A-Million config at {bam_config_path}")
        except Exception as e:
            print(f"Error creating Books-A-Million config: {e}")


def main():
    """Main entry point for the enhanced CLI"""
    parser = argparse.ArgumentParser(description='Stock Checker Enhanced CLI')
    parser.add_argument('--daemon', action='store_true', help='Run in daemon mode (non-interactive)')
    parser.add_argument('--no-proxies', action='store_true', help='Disable proxy usage')
    parser.add_argument('--config', help='Path to config file')
    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create default config files if needed
    create_default_configs()

    # Load configuration
    load_config()

    # Override config with command line args
    if args.no_proxies:
        config['use_proxies'] = False

    # Run in appropriate mode
    if args.daemon:
        daemon_mode()
    else:
        interactive_mode()


if __name__ == "__main__":
    main()