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
from utils.config_loader import load_global_config

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
            # In auto-refresh mode, we use a timeout to allow regular updates
            if auto_refresh:
                # Check if it's time to refresh
                if time.time() - last_refresh >= refresh_interval:
                    # Status is already being updated by the status thread
                    last_refresh = time.time()

                # Use short timeout to catch commands while still allowing refreshes
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)

                if not ready:
                    continue

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
                # Status is already being updated by the status thread
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

    # Load configuration
    load_config()

    # Override config with command line args
    if args.no_proxies:
        config['use_proxies'] = False

    # Run in appropriate mode
    if args.daemon:
        daemon_mode()
    else:
        # For interactive mode, we need the select module for input handling
        import select
        interactive_mode()


if __name__ == "__main__":
    main()