# src/utils/module_loader.py
"""
Provides utilities for checking the availability of optional modules.
"""
import importlib.util

def is_module_available(module_name: str) -> bool:
    """
    Checks if a Python module can be found without actually importing it.
    
    Args:
        module_name: The full name of the module (e.g., "src.handlers.nsfw").

    Returns:
        True if the module exists, False otherwise.
    """
    spec = importlib.util.find_spec(module_name)
    return spec is not None