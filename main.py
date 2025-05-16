#!/usr/bin/env python3
"""
Stock Checker - Main Runner
Initializes and runs the stock checker system either in CLI or GUI mode.
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path

from dispatcher import ModuleDispatcher
from proxy_manager import ProxyManager
from notifier import DiscordNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("stock_checker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("StockChecker")


def load_config():
    """Load configuration from config.json"""
    try:
        with open('config/global.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Config file not found. Creating a default one.")
        default_config = {
            "discord_webhook": "",
            "check_interval": 60,  # Default check interval in seconds
            "keywords": ["exclusive", "limited edition"],
            "modules": {
                "booksamillion": {"enabled": True, "interval": 120},
                "popshelf": {"enabled": False, "interval": 300}
            },
            "use_proxies": True,
            "gui_enabled": False
        }
        with open('config/config.json', 'w') as f:
            json.dump(default_config, f, indent=4)
        return default_config
    except json.JSONDecodeError:
        logger.error("Invalid JSON in config file.")
        sys.exit(1)


def run_cli(config, dispatcher):
    """Run the application in CLI mode"""
    print("\n==== Stock Checker CLI ====")
    print("Commands: list, start <module>, stop <module>, status, reload <module>, exit")

    while True:
        command = input("\nCommand > ").strip().lower()
        parts = command.split()

        if not parts:
            continue

        if parts[0] == "exit":
            print("Shutting down...")
            dispatcher.stop_all()
            break

        elif parts[0] == "list":
            modules = dispatcher.list_modules()
            print("\nAvailable modules:")
            for mod in modules:
                status = "Running" if dispatcher.is_module_running(mod) else "Stopped"
                print(f"  - {mod} [{status}]")

        elif parts[0] == "start":
            if len(parts) < 2:
                print("Usage: start <module_name>")
                continue

            module_name = parts[1]
            result = dispatcher.start_module(module_name)
            print(f"Module {module_name}: {result}")

        elif parts[0] == "stop":
            if len(parts) < 2:
                print("Usage: stop <module_name>")
                continue

            module_name = parts[1]
            result = dispatcher.stop_module(module_name)
            print(f"Module {module_name}: {result}")

        elif parts[0] == "status":
            status = dispatcher.get_status()
            print("\nModule status:")
            for mod, details in status.items():
                print(f"  - {mod}: {details['status']}")
                if details['status'] == 'Running':
                    print(f"    Last run: {details.get('last_run', 'N/A')}")
                    print(f"    Next run: {details.get('next_run', 'N/A')}")

        elif parts[0] == "reload":
            if len(parts) < 2:
                print("Usage: reload <module_name>")
                continue

            module_name = parts[1]
            result = dispatcher.reload_module(module_name)
            print(f"Module {module_name}: {result}")

        else:
            print("Unknown command. Available commands: list, start, stop, status, reload, exit")


def setup_gui(config, dispatcher):
    """Setup and run the GUI interface using Tkinter"""
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    class StockCheckerGUI:
        def __init__(self, root, dispatcher):
            self.root = root
            self.dispatcher = dispatcher
            self.root.title("Stock Checker")
            self.root.geometry("800x600")

            # Create tabs
            self.tab_control = ttk.Notebook(root)

            # Modules tab
            self.modules_tab = ttk.Frame(self.tab_control)
            self.tab_control.add(self.modules_tab, text='Modules')

            # Logs tab
            self.logs_tab = ttk.Frame(self.tab_control)
            self.tab_control.add(self.logs_tab, text='Logs')

            # Settings tab
            self.settings_tab = ttk.Frame(self.tab_control)
            self.tab_control.add(self.settings_tab, text='Settings')

            self.tab_control.pack(expand=1, fill="both")

            # Set up modules tab
            self.setup_modules_tab()

            # Set up logs tab
            self.setup_logs_tab()

            # Set up settings tab
            self.setup_settings_tab()

            # Schedule status updates
            self.root.after(1000, self.update_status)

        def setup_modules_tab(self):
            # Module list frame
            list_frame = ttk.LabelFrame(self.modules_tab, text="Available Modules")
            list_frame.pack(fill="both", expand=True, padx=10, pady=10)

            # Create treeview for modules
            columns = ('Module', 'Status', 'Last Run', 'Next Run')
            self.module_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

            # Set column headings
            for col in columns:
                self.module_tree.heading(col, text=col)
                self.module_tree.column(col, width=100)

            self.module_tree.pack(fill="both", expand=True, padx=5, pady=5)

            # Control buttons frame
            ctrl_frame = ttk.Frame(self.modules_tab)
            ctrl_frame.pack(fill="x", padx=10, pady=5)

            ttk.Button(ctrl_frame, text="Start", command=self.start_selected).pack(side="left", padx=5)
            ttk.Button(ctrl_frame, text="Stop", command=self.stop_selected).pack(side="left", padx=5)
            ttk.Button(ctrl_frame, text="Reload", command=self.reload_selected).pack(side="left", padx=5)
            ttk.Button(ctrl_frame, text="Refresh", command=self.refresh_modules).pack(side="left", padx=5)

            # Initial population
            self.refresh_modules()

        def setup_logs_tab(self):
            # Log viewer
            self.log_text = scrolledtext.ScrolledText(self.logs_tab, wrap=tk.WORD)
            self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

            # Add a custom handler to capture logs
            self.log_handler = GUILogHandler(self.log_text)
            self.log_handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(self.log_handler)

            # Control buttons
            ctrl_frame = ttk.Frame(self.logs_tab)
            ctrl_frame.pack(fill="x", padx=10, pady=5)

            ttk.Button(ctrl_frame, text="Clear Logs", command=self.clear_logs).pack(side="left", padx=5)

        def setup_settings_tab(self):
            settings_frame = ttk.LabelFrame(self.settings_tab, text="Configuration")
            settings_frame.pack(fill="both", expand=True, padx=10, pady=10)

            # Webhook URL
            ttk.Label(settings_frame, text="Discord Webhook URL:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
            self.webhook_var = tk.StringVar(value=config.get("discord_webhook", ""))
            ttk.Entry(settings_frame, textvariable=self.webhook_var, width=50).grid(row=0, column=1, padx=5, pady=5)

            # Check interval
            ttk.Label(settings_frame, text="Global Check Interval (seconds):").grid(row=1, column=0, sticky="w", padx=5,
                                                                                    pady=5)
            self.interval_var = tk.IntVar(value=config.get("check_interval", 60))
            ttk.Spinbox(settings_frame, from_=5, to=3600, textvariable=self.interval_var, width=10).grid(row=1,
                                                                                                         column=1,
                                                                                                         sticky="w",
                                                                                                         padx=5, pady=5)

            # Use proxies
            self.use_proxies_var = tk.BooleanVar(value=config.get("use_proxies", True))
            ttk.Checkbutton(settings_frame, text="Use Proxies", variable=self.use_proxies_var).grid(row=2, column=0,
                                                                                                    sticky="w", padx=5,
                                                                                                    pady=5)

            # Save button
            ttk.Button(settings_frame, text="Save Settings", command=self.save_settings).grid(row=3, column=1,
                                                                                              sticky="e", padx=5,
                                                                                              pady=10)

        def start_selected(self):
            selection = self.module_tree.selection()
            if not selection:
                return

            module_name = self.module_tree.item(selection[0])['values'][0]
            result = self.dispatcher.start_module(module_name)
            self.refresh_modules()

        def stop_selected(self):
            selection = self.module_tree.selection()
            if not selection:
                return

            module_name = self.module_tree.item(selection[0])['values'][0]
            result = self.dispatcher.stop_module(module_name)
            self.refresh_modules()

        def reload_selected(self):
            selection = self.module_tree.selection()
            if not selection:
                return

            module_name = self.module_tree.item(selection[0])['values'][0]
            result = self.dispatcher.reload_module(module_name)
            self.refresh_modules()

        def refresh_modules(self):
            # Clear existing items
            for item in self.module_tree.get_children():
                self.module_tree.delete(item)

            # Get current status
            status = self.dispatcher.get_status()

            # Populate with updated data
            for module_name, details in status.items():
                values = (
                    module_name,
                    details.get('status', 'Unknown'),
                    details.get('last_run', 'N/A'),
                    details.get('next_run', 'N/A')
                )
                self.module_tree.insert('', 'end', values=values)

        def update_status(self):
            """Periodically update module status"""
            self.refresh_modules()
            self.root.after(5000, self.update_status)  # Update every 5 seconds

        def clear_logs(self):
            """Clear the log display"""
            self.log_text.delete(1.0, tk.END)

        def save_settings(self):
            """Save settings to config file"""
            config["discord_webhook"] = self.webhook_var.get()
            config["check_interval"] = self.interval_var.get()
            config["use_proxies"] = self.use_proxies_var.get()

            with open('config/config.json', 'w') as f:
                json.dump(config, f, indent=4)

            # Update components with new settings
            self.dispatcher.notifier.set_webhook(config["discord_webhook"])
            logger.info("Settings saved")

    class GUILogHandler(logging.Handler):
        """Custom log handler that writes to the GUI"""

        def __init__(self, text_widget):
            super().__init__()
            self.text_widget = text_widget

        def emit(self, record):
            msg = self.format(record)

            def append():
                self.text_widget.configure(state='normal')
                self.text_widget.insert(tk.END, msg + '\n')
                self.text_widget.configure(state='disabled')
                self.text_widget.yview(tk.END)

            # Schedule the append operation on the main thread
            self.text_widget.after(0, append)

    # Create and run the GUI
    root = tk.Tk()
    app = StockCheckerGUI(root, dispatcher)
    root.mainloop()


def main():
    """Main entry point for the stock checker application"""
    parser = argparse.ArgumentParser(description='Stock Checker')
    parser.add_argument('--gui', action='store_true', help='Run with GUI interface')
    parser.add_argument('--no-proxies', action='store_true', help='Disable proxy usage')
    args = parser.parse_args()

    # Load configuration
    config = load_config()

    # Override config with command line args
    if args.no_proxies:
        config['use_proxies'] = False

    use_gui = args.gui or config.get('gui_enabled', False)

    # Initialize components
    proxy_manager = ProxyManager('proxies.txt') if config['use_proxies'] else None
    notifier = DiscordNotifier(config['discord_webhook'])

    # Create dispatcher to manage modules
    dispatcher = ModuleDispatcher(
        notifier=notifier,
        proxy_manager=proxy_manager,
        config=config
    )

    # Load modules
    modules_dir = Path('modules')
    if not modules_dir.exists():
        modules_dir.mkdir()
        logger.info(f"Created modules directory at {modules_dir}")

    dispatcher.discover_modules()

    # Start enabled modules
    for module_name, module_config in config.get('modules', {}).items():
        if module_config.get('enabled', False):
            dispatcher.start_module(module_name)

    # Run the appropriate interface
    if use_gui:
        setup_gui(config, dispatcher)
    else:
        run_cli(config, dispatcher)


if __name__ == "__main__":
    main()