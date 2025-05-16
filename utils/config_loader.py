#!/usr/bin/env python3
"""
Configuration Loader Utility
Provides functions for loading module configurations from the config directory.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ConfigLoader")


def ensure_config_dirs():
    """Create configuration directories if they don't exist"""
    # Get the project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Create required directories
    dirs = [
        root_dir / "config",
        root_dir / "config/modules",
        root_dir / "data"
    ]

    for directory in dirs:
        directory.mkdir(exist_ok=True)

    logger.debug("Configuration directories verified")


def load_module_config(module_name: str) -> Dict[str, Any]:
    """
    Load consolidated module configuration

    Args:
        module_name: Name of the module

    Returns:
        Dict with module configuration
    """
    ensure_config_dirs()

    # Get the project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Define possible config paths with preference order
    config_paths = [
        root_dir / f"config/modules/{module_name}.json",
        root_dir / f"config/{module_name}.json",
        root_dir / f"config/config_{module_name}.json",
        root_dir / f"config_{module_name}.json"
    ]

    # Try each path until we find a config file
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    logger.info(f"Loaded module config from {config_path}")
                    return config
            except Exception as e:
                logger.error(f"Error loading config from {config_path}: {str(e)}")

    # If no config found, check for legacy target files
    targets = load_legacy_targets(module_name)
    if targets:
        logger.info(f"Loaded legacy target files for {module_name}")
        return targets

    logger.warning(f"No configuration found for {module_name}")
    return {}


def load_legacy_targets(module_name: str) -> Dict[str, Any]:
    """
    Load legacy target files (for backward compatibility)

    Args:
        module_name: Name of the module

    Returns:
        Dict with target configurations
    """
    # Get the project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Define the legacy targets path
    targets_path = root_dir / "config/targets" / module_name

    if not targets_path.exists():
        return {}

    targets = {}

    # Load keywords if available
    keywords_file = targets_path / "keywords.json"
    if keywords_file.exists():
        try:
            with open(keywords_file, "r") as f:
                keyword_data = json.load(f)
                targets.update(keyword_data)
        except Exception as e:
            logger.error(f"Error loading keywords for {module_name}: {str(e)}")

    # Load PIDs if available
    pid_file = targets_path / "pid_list.json"
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid_data = json.load(f)
                targets.update(pid_data)
        except Exception as e:
            logger.error(f"Error loading PIDs for {module_name}: {str(e)}")

    # Load URLs if available
    url_file = targets_path / "urls.json"
    if url_file.exists():
        try:
            with open(url_file, "r") as f:
                url_data = json.load(f)
                targets.update(url_data)
        except Exception as e:
            logger.error(f"Error loading URLs for {module_name}: {str(e)}")

    return targets


def save_module_config(module_name: str, config: Dict[str, Any]) -> bool:
    """
    Save consolidated module configuration

    Args:
        module_name: Name of the module
        config: Configuration to save

    Returns:
        bool: True if successful
    """
    ensure_config_dirs()

    # Get the project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Define config path
    config_path = root_dir / f"config/modules/{module_name}.json"

    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved module config to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving config to {config_path}: {str(e)}")
        return False


def update_pid_list(module_name: str, new_pids: List[str]) -> bool:
    """
    Update PID list in configuration

    Args:
        module_name: Name of the module
        new_pids: New PIDs to add

    Returns:
        bool: True if successful
    """
    # Load current configuration
    config = load_module_config(module_name)

    # Add new PIDs
    current_pids = set(config.get("pids", []))
    current_pids.update(new_pids)

    # Update configuration
    config["pids"] = list(current_pids)

    # Save configuration
    return save_module_config(module_name, config)


def load_global_config() -> Dict[str, Any]:
    """
    Load global configuration

    Returns:
        Dict with global configuration
    """
    ensure_config_dirs()

    # Get the project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Define possible config paths with preference order
    config_paths = [
        root_dir / "config/global.json",
        root_dir / "config/config.json",
        root_dir / "config.json"
    ]

    # Try each path until we find a config file
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    logger.debug(f"Loaded global config from {config_path}")
                    return config
            except Exception as e:
                logger.error(f"Error loading global config from {config_path}: {str(e)}")

    # Return default configuration if no file found
    default_config = {
        "discord_webhook": "",
        "check_interval": 60,
        "use_proxies": True,
        "gui_enabled": False,
        "modules": {
            "booksamillion": {
                "enabled": True,
                "interval": 300
            }
        }
    }

    logger.warning("No global configuration found, using defaults")
    return default_config


if __name__ == "__main__":
    # Set up logging for testing
    logging.basicConfig(level=logging.DEBUG)

    # Test loading module config
    config = load_module_config("booksamillion")
    print("Module config:", json.dumps(config, indent=2) if config else "Not found")

    # Test loading global config
    global_config = load_global_config()
    print("Global config:", json.dumps(global_config, indent=2))