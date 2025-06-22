# src/utils/logging.py
"""
Configures logging for the entire application.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
# --- MODIFICATION START ---
from typing import Optional
# --- MODIFICATION END ---
import src.config as config

logger = logging.getLogger(__name__)

def setup_logging():
    """Initializes console and file logging."""
    root_logger = logging.getLogger()
    
    # --- FIX: Reverted the default logging level back to INFO ---
    root_logger.setLevel(logging.INFO) 
    # --- FIX END ---

    # Clear any existing handlers to prevent duplicates on successive calls
    for handler in root_logger.handlers[:]: #
        root_logger.removeHandler(handler) #

    # Add a stream handler for console output
    console_handler = logging.StreamHandler(sys.stdout) #
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')) #
    root_logger.addHandler(console_handler) #

    # Add a rotating file handler for persistent logs.
    log_file_path = os.path.join(config.LOGS_DIR, "bot_activity.log") #
    file_handler = RotatingFileHandler( #
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')) #
    root_logger.addHandler(file_handler) #

    # Reduce noise from overly verbose libraries.
    for lib_name in ["httpx", "openai", "chromadb", "sentence_transformers", "apscheduler", "telegram.ext"]: #
        logging.getLogger(lib_name).setLevel(logging.WARNING) #

    logger.info("Logging configured successfully.") #

# --- Per-User Conversation Logging ---

_user_loggers = {} # Cache for user logger instances

def get_user_logger(user_id: int, username: Optional[str] = None) -> logging.Logger:
    """
    Creates and returns a dedicated logger for a specific user ID that saves
    their conversation to a separate file. This function now always returns
    a logger; the decision to log is handled by the caller.
    """
    if user_id in _user_loggers:
        return _user_loggers[user_id]

    try:
        sanitized_username = ''.join(c for c in username if c.isalnum() or c in ('-', '_')) if username else 'NoUsername'
        log_file_name = f"{user_id}-{sanitized_username}.log"
        log_file = os.path.join(config.USER_LOGS_DIR, log_file_name)
        
        user_logger = logging.getLogger(f"user.{user_id}")
        user_logger.setLevel(logging.INFO)
        user_logger.propagate = False

        handler = RotatingFileHandler(
            log_file, maxBytes=1 * 1024 * 1024, backupCount=1, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        
        user_logger.addHandler(handler)
        _user_loggers[user_id] = user_logger
        
        logger.info(f"Initialized conversation logger for user {user_id} ({sanitized_username}).")
        return user_logger

    except Exception as e:
        logger.error(f"Failed to create logger for user {user_id}: {e}", exc_info=True)
        # In case of failure, return the root logger to avoid crashes, though messages will go to the main log.
        return logging.getLogger()