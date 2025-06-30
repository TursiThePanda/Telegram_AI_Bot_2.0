# src/utils/files.py
"""
This module contains shared utility functions used across the application,
such as loading data from files.
"""
import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def load_from_directory(path: str, key_name: str = "name") -> Dict[str, Any]:
    """
    Loads all .json files from a specified directory into a dictionary.

    Args:
        path (str): The absolute or relative path to the directory.
        key_name (str): The key within the JSON file to use as the dictionary
                        key for the returned data. Defaults to "name".

    Returns:
        Dict[str, Any]: A dictionary containing data from the JSON files.
    """
    
    # TEMPORARY DEBUG: Force this logger to DEBUG level
    logger.setLevel(logging.DEBUG)
    
    data: Dict[str, Any] = {}
    
    # Ensure the assets directory exists before trying to read from it.
    os.makedirs(path, exist_ok=True) # This is also handled by application.py, but remains for standalone use.
    
    if not os.path.isdir(path):
        logger.warning(f"Path is not a directory, cannot load files: {path}")
        return data

    for filename in os.listdir(path):
        if filename.endswith(".json"):
            filepath = os.path.join(path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    key = content.get(key_name)
                    if key:
                        data[key] = content
                    else:
                        # Fallback to using the filename without extension as the key
                        file_key = os.path.splitext(filename)[0]
                        data[file_key] = content
                        logger.debug(
                            f"File '{filename}' is missing the key '{key_name}'. "
                            f"Using filename '{file_key}' as key instead."
                        )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {filename}: {e}")
            except IOError as e:
                logger.error(f"Failed to read file {filename}: {e}")
    return data
    
def load_json(filepath, default=None):
    """Load a JSON file safely. Return default if missing or broken."""
    if not os.path.isfile(filepath):
        return default or {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from {filepath}: {e}")
        return default or {}
    except IOError as e:
        logger.error(f"Failed to read file {filepath}: {e}")
        return default or {}
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred while loading {filepath}: {e}")
        return default or {}

def save_json(filepath, data):
    """Write data to JSON file safely."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except (IOError, OSError) as e:
        logger.error(f"Failed to write file {filepath}: {e}")
        return False
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred while saving {filepath}: {e}")
        return False