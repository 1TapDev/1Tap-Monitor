#!/usr/bin/env python3
"""
Dispatcher Module
Handles loading, reloading, and scheduling of website modules.
"""

import os
import sys
import time
import json
import importlib
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("Dispatcher")


class ModuleThread(threading.Thread):
    """Thread class that runs a website module periodically"""

    def __init__(self, module_instance, interval: int, notifier, proxy_manager=None):
        """
        Initialize a module thread

        Args:
            module_instance: The module instance to run
            interval: Seconds between each run
            notifier: Notifier instance for sending alerts
            proxy_manager: Optional proxy manager instance
        """
        super().__init__(daemon=True)
        self.module = module_instance
        self.interval = interval
        self.notifier = notifier
        self.proxy_manager = proxy_manager
        self.running = False
        self.stop_event = threading.Event()
        self.last_run = None
        self.next_run = None

    def run(self):
        """Run the module periodically"""
        self.running = True

        while not self.stop_event.is_set():
            try:
                logger.info(f"Running module: {self.module.__class__.__name__}")
                self.last_run = datetime.now()

                proxy = None
                if self.proxy_manager:
                    proxy = self.proxy_manager.get_proxy()

                # Run the module and get results
                results = self.module.check_stock(proxy=proxy)

                # Check if any items are in stock
                if results and any(item.get('in_stock', False) for item in results):
                    # Send notifications for in-stock items
                    for item in results:
                        if item.get('in_stock', False):
                            self.notifier.send_alert(
                                title=f"In Stock: {item.get('name', 'Unknown Item')}",
                                description=f"Found at {self.module.NAME}",
                                url=item.get('url', ''),
                                image=item.get('image', ''),
                                store=self.module.NAME
                            )

                logger.info(f"Module {self.module.__class__.__name__} completed successfully")
            except Exception as e:
                logger.error(f"Error running module {self.module.__class__.__name__}: {str(e)}")

            # Calculate next run time
            self.next_run = datetime.now() + timedelta(seconds=self.interval)

            # Sleep until next run or until stopped
            for _ in range(self.interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def stop(self):
        """Signal the thread to stop"""
        self.stop_event.set()
        self.running = False


class ModuleDispatcher:
    """Manages loading, reloading and running of website modules"""

    def __init__(self, notifier, proxy_manager=None, config=None):
        """
        Initialize the dispatcher

        Args:
            notifier: Notifier instance for sending alerts
            proxy_manager: Optional proxy manager for rotation
            config: Application configuration dictionary
        """
        self.modules = {}  # type: Dict[str, Any]
        self.module_threads = {}  # type: Dict[str, ModuleThread]
        self.notifier = notifier
        self.proxy_manager = proxy_manager
        self.config = config or {}

    def discover_modules(self) -> List[str]:
        """
        Discover and load all available modules

        Returns:
            List of module names that were discovered
        """
        modules_dir = Path('modules')
        module_files = [f.stem for f in modules_dir.glob('*.py')
                        if f.is_file() and not f.stem.startswith('__')]

        loaded_modules = []
        for module_name in module_files:
            try:
                # Import the module
                spec = importlib.util.find_spec(f'modules.{module_name}')
                if spec:
                    loaded_modules.append(module_name)
                    # We don't instantiate here, just record that it exists
                    self.modules[module_name] = None
                    logger.info(f"Discovered module: {module_name}")
            except (ImportError, AttributeError) as e:
                logger.error(f"Error discovering module {module_name}: {str(e)}")

        return loaded_modules

    def load_module(self, module_name: str) -> bool:
        """
        Load a specific module by name

        Args:
            module_name: Name of the module to load

        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            # Try to load or reload the module
            module_path = f'modules.{module_name}'

            if module_path in sys.modules:
                # Reload if already loaded
                module = importlib.reload(sys.modules[module_path])
                logger.info(f"Reloaded module: {module_name}")
            else:
                # Import for the first time
                module = importlib.import_module(module_path)
                logger.info(f"Loaded module: {module_name}")

            # Get the main class from the module (assumed to be named after the module in CamelCase)
            class_name = ''.join(word.capitalize() for word in module_name.split('_'))

            if not hasattr(module, class_name):
                logger.error(f"Module {module_name} does not contain required class {class_name}")
                return False

            # Create an instance of the module class
            module_class = getattr(module, class_name)
            module_instance = module_class()

            # Load module-specific config if available
            module_config_file = Path(f'config_{module_name}.json')
            if module_config_file.exists():
                try:
                    with open(module_config_file, 'r') as f:
                        module_config = json.load(f)
                        # Set module configuration
                        if hasattr(module_instance, 'set_config'):
                            module_instance.set_config(module_config)
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    logger.error(f"Error loading module config for {module_name}: {str(e)}")

            # Store the module instance
            self.modules[module_name] = module_instance
            return True

        except Exception as e:
            logger.error(f"Error loading module {module_name}: {str(e)}")
            return False

    def start_module(self, module_name: str) -> str:
        """
        Start a module by name

        Args:
            module_name: Name of the module to start

        Returns:
            str: Status message
        """
        # Check if module exists
        if module_name not in self.modules:
            if not self.load_module(module_name):
                return f"Failed to load module {module_name}"

        # If module is already running, do nothing
        if module_name in self.module_threads and self.module_threads[module_name].running:
            return f"Module {module_name} is already running"

        # If module is None (not loaded), load it
        if self.modules[module_name] is None:
            if not self.load_module(module_name):
                return f"Failed to load module {module_name}"

        # Get the module interval - prioritize module-specific settings
        module_interval = 60  # Default to 60 seconds

        if self.config.get('modules', {}).get(module_name, {}).get('interval'):
            module_interval = self.config['modules'][module_name]['interval']
        elif hasattr(self.modules[module_name], 'INTERVAL'):
            module_interval = self.modules[module_name].INTERVAL
        else:
            module_interval = self.config.get('check_interval', 60)

        # Create and start a thread for the module
        thread = ModuleThread(
            module_instance=self.modules[module_name],
            interval=module_interval,
            notifier=self.notifier,
            proxy_manager=self.proxy_manager
        )
        thread.start()

        # Store the thread
        self.module_threads[module_name] = thread

        logger.info(f"Started module: {module_name}")
        return f"Module {module_name} started"

    def stop_module(self, module_name: str) -> str:
        """
        Stop a running module

        Args:
            module_name: Name of the module to stop

        Returns:
            str: Status message
        """
        if module_name not in self.module_threads or not self.module_threads[module_name].running:
            return f"Module {module_name} is not running"

        # Signal the thread to stop
        self.module_threads[module_name].stop()

        # Wait for the thread to stop (with timeout)
        self.module_threads[module_name].join(timeout=5)

        logger.info(f"Stopped module: {module_name}")
        return f"Module {module_name} stopped"

    def reload_module(self, module_name: str) -> str:
        """
        Reload a module's code and restart if it was running

        Args:
            module_name: Name of the module to reload

        Returns:
            str: Status message
        """
        # Check if module exists
        if module_name not in self.modules:
            return f"Module {module_name} not found"

        # Check if it's running and stop it
        was_running = False
        if module_name in self.module_threads and self.module_threads[module_name].running:
            was_running = True
            self.stop_module(module_name)

        # Reload the module
        if not self.load_module(module_name):
            return f"Failed to reload module {module_name}"

        # Restart if it was running
        if was_running:
            return self.start_module(module_name)

        return f"Module {module_name} reloaded"

    def stop_all(self) -> None:
        """Stop all running modules"""
        for module_name in list(self.module_threads.keys()):
            if self.module_threads[module_name].running:
                self.stop_module(module_name)

    def list_modules(self) -> List[str]:
        """
        List all available modules

        Returns:
            List of module names
        """
        return list(self.modules.keys())

    def is_module_running(self, module_name: str) -> bool:
        """
        Check if a module is currently running

        Args:
            module_name: Name of the module to check

        Returns:
            bool: True if running, False otherwise
        """
        return (module_name in self.module_threads and
                self.module_threads[module_name].running)

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the status of all modules

        Returns:
            Dict mapping module names to their status information
        """
        status = {}

        for module_name in self.modules:
            module_status = {'status': 'Stopped'}

            if module_name in self.module_threads and self.module_threads[module_name].running:
                thread = self.module_threads[module_name]
                module_status['status'] = 'Running'

                if thread.last_run:
                    module_status['last_run'] = thread.last_run.strftime('%Y-%m-%d %H:%M:%S')

                if thread.next_run:
                    module_status['next_run'] = thread.next_run.strftime('%Y-%m-%d %H:%M:%S')

            status[module_name] = module_status

        return status