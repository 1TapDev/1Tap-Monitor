#!/usr/bin/env python3
"""
Configuration Loader Utility
Provides functions for loading module configurations from the config directory.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ConfigLoader")


def ensure_config_dirs():
    """Create configuration directories if they don't exist"""
    dirs = [
        Path("../config"),
        Path("../config/modules"),
        Path("../config/targets")
    ]

    for directory in dirs:
        directory.mkdir(exist_ok=True)


def load_module_config(module_name: str) -> Dict[str, Any]:
    """
    Load module-specific configuration from config/modules directory

    Args:
        module_name: Name of the module

    Returns:
        Dict with module configuration
    """
    ensure_config_dirs()

    # Define path to module config
    config_path = Path(f"../config/modules/{module_name}.json")

    # Check if config file exists
    if not config_path.exists():
        logger.warning(f"No module config found for {module_name}")
        return {}

    # Load config
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            logger.info(f"Loaded module config for {module_name}")
            return config
    except Exception as e:
        logger.error(f"Error loading module config for {module_name}: {str(e)}")
        return {}


def load_module_targets(module_name: str) -> Dict[str, Any]:
    """
    Load all target configurations (URLs, PIDs, keywords) for a specific module

    Args:
        module_name: Name of the module

    Returns:
        Dict with all target configurations
    """
    ensure_config_dirs()

    # Create default return structure
    targets = {
        "urls": [],
        "search_urls": [],
        "item_urls": [],
        "pids": [],
        "priority_pids": [],
        "keywords": [],
        "categories": [],
        "brands": []
    }

    # Define paths
    base_path = Path("../config/targets") / module_name

    # Ensure module targets directory exists
    base_path.mkdir(exist_ok=True)

    # Load URLs if available
    url_file = base_path / "urls.json"
    if url_file.exists():
        try:
            with open(url_file, "r") as f:
                url_data = json.load(f)
                targets["search_urls"] = url_data.get("search_urls", [])
                targets["item_urls"] = url_data.get("item_urls", [])
                # For backward compatibility
                targets["urls"] = targets["search_urls"] + targets["item_urls"]
            logger.info(f"Loaded URL targets for {module_name}")
        except Exception as e:
            logger.error(f"Error loading URLs for {module_name}: {str(e)}")

    # Load PIDs if available
    pid_file = base_path / "pid_list.json"
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid_data = json.load(f)
                targets["pids"] = pid_data.get("pids", [])
                targets["priority_pids"] = pid_data.get("priority_pids", [])
            logger.info(f"Loaded PID targets for {module_name}")
        except Exception as e:
            logger.error(f"Error loading PIDs for {module_name}: {str(e)}")

    # Load keywords if available
    keyword_file = base_path / "keywords.json"
    if keyword_file.exists():
        try:
            with open(keyword_file, "r") as f:
                keyword_data = json.load(f)
                targets["keywords"] = keyword_data.get("keywords", [])
                targets["categories"] = keyword_data.get("categories", [])
                targets["brands"] = keyword_data.get("brands", [])
            logger.info(f"Loaded keyword targets for {module_name}")
        except Exception as e:
            logger.error(f"Error loading keywords for {module_name}: {str(e)}")

    return targets


def save_module_targets(module_name: str, target_type: str, data: Dict[str, Any]) -> bool:
    """
    Save target configuration for a specific module

    Args:
        module_name: Name of the module
        target_type: Type of target ('urls', 'pids', 'keywords')
        data: Target data to save

    Returns:
        bool: True if successful, False otherwise
    """
    ensure_config_dirs()

    # Define paths
    base_path = Path("../config/targets") / module_name

    # Ensure module targets directory exists
    base_path.mkdir(exist_ok=True)

    # Determine file path based on target type
    if target_type == 'urls':
        file_path = base_path / "urls.json"
    elif target_type == 'pids':
        file_path = base_path / "pid_list.json"
    elif target_type == 'keywords':
        file_path = base_path / "keywords.json"
    else:
        logger.error(f"Unknown target type: {target_type}")
        return False

    # Save data
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {target_type} targets for {module_name}")
        return True
    except Exception as e:
        logger.error(f"Error saving {target_type} for {module_name}: {str(e)}")
        return False


def update_pid_list(module_name: str, new_pids: List[str]) -> bool:
    """
    Update PID list for a module by adding new PIDs

    Args:
        module_name: Name of the module
        new_pids: List of new PIDs to add

    Returns:
        bool: True if successful, False otherwise
    """
    # Load current PIDs
    targets = load_module_targets(module_name)
    current_pids = set(targets.get("pids", []))

    # Add new PIDs
    current_pids.update(new_pids)

    # Save updated PIDs
    pid_data = {
        "pids": list(current_pids),
        "priority_pids": targets.get("priority_pids", []),
        "last_updated": targets.get("last_updated", ""),
        "last_scanned": targets.get("last_scanned", "")
    }

    return save_module_targets(module_name, "pids", pid_data)


def load_global_config() -> Dict[str, Any]:
    """
    Load global configuration

    Returns:
        Dict with global configuration
    """
    ensure_config_dirs()

    # Define path to global config
    config_path = Path("../config/global.json")

    # Check if config file exists and create default if it doesn't
    if not config_path.exists():
        default_config = {
            "discord_webhook": "",
            "check_interval": 60,
            "use_proxies": True,
            "gui_enabled": False,
            "debug": {
                "verbose": False,
                "log_level": "INFO"
            }
        }

        try:
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=2)
            logger.info("Created default global config")
        except Exception as e:
            logger.error(f"Error creating default global config: {str(e)}")
            return default_config

    # Load config
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            logger.info("Loaded global config")
            return config
    except Exception as e:
        logger.error(f"Error loading global config: {str(e)}")
        return {}