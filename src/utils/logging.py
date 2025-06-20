# src/utils/logging.py
"""
Configures logging for the entire application.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
import src.config as config

logger = logging.getLogger(__name__)

def setup_logging():
    """Initializes console and file logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO) # Set the default level for the root logger

    # Clear any existing handlers to prevent duplicates on successive calls
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a stream handler for console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(console_handler)

    # Add a rotating file handler for persistent logs.
    log_file_path = os.path.join(config.LOGS_DIR, "bot_activity.log")
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

    # Reduce noise from overly verbose libraries.
    for lib_name in ["httpx", "openai", "chromadb", "sentence_transformers", "apscheduler", "telegram.ext"]:
        logging.getLogger(lib_name).setLevel(logging.WARNING)

    logger.info("Logging configured successfully.")