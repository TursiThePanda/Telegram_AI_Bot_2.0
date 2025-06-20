# src/core/application.py
"""
Handles the creation and configuration of the main Telegram bot application.
"""
import logging
import os
import asyncio
from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder, PicklePersistence

import src.config as config
from src.core import tasks
from src.utils import logging as logging_utils
from src.utils import files as file_utils
from src.utils import error_handler
from src import services
from src import handlers

logger = logging.getLogger(__name__)
background_tasks = set() # Changed to a set to easily manage active tasks

# Ensure required directories exist
REQUIRED_DIRS = [
    config.DATA_DIR,        # For general data, logs, persistence, db
    config.LOGS_DIR,
    config.USER_LOGS_DIR,
    config.PERSISTENCE_DIR,
    config.DB_DIR,
    
    # Personas and Sceneries are now explicitly expected ONLY in the root directory.
    # The previous entries like os.path.join(config.DATA_DIR, config.PERSONAS_PATH)
    # are removed here to prevent them from being created inside /data/.
    config.PERSONAS_PATH,   # This will be 'personas' directly in bot's root
    config.SCENERIES_PATH,  # This will be 'sceneries' directly in bot's root
]

def ensure_directories():
    for path in REQUIRED_DIRS:
        try:
            os.makedirs(path, exist_ok=True)
            logger.debug(f"Ensured directory exists: {path}")
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")

async def post_init(application: Application):
    # Local import to avoid potential circular dependency during startup phase
    from src.handlers.admin import load_admin_toggles 

    ensure_directories()
    # Initialize services after directories are ensured and config is loaded
    services.database.init_db() 
    services.ai_models.init_ai_client() # Initialize AI client

    # Load personas and sceneries from their respective directories in the root
    # Use config.PERSONAS_PATH and config.SCENERIES_PATH directly
    application.bot_data['personas'] = file_utils.load_from_directory(config.PERSONAS_PATH, key_name="name")
    sceneries_full_data = file_utils.load_from_directory(config.SCENERIES_PATH, key_name="name")
    application.bot_data['sceneries_full_data'] = sceneries_full_data
    application.bot_data['sceneries'] = { name: data.get('description', '') for name, data in sceneries_full_data.items() }
    logger.info(f"Loaded {len(application.bot_data['personas'])} personas and {len(application.bot_data['sceneries'])} sceneries.")
    
    logger.info("Starting background tasks...")
    task_coroutines = [tasks.performance_report_task(), tasks.health_check_task(application)]
    for task_coro in task_coroutines:
        task = asyncio.create_task(task_coro)
        background_tasks.add(task)
        # Add a done callback to remove the task from the set once it completes (or is cancelled/fails)
        task.add_done_callback(background_tasks.discard) 
    logger.info(f"{len(background_tasks)} background tasks scheduled.")
    
    logger.info("Setting bot command menu...")
    commands = [
        BotCommand("start", "Restart & begin setup"), 
        BotCommand("setup", "Configure your character & persona"),
        BotCommand("regenerate", "Redo the last AI response"), 
        BotCommand("clear", "Clear conversation history"),
        BotCommand("help", "Show help and commands"), 
        BotCommand("admin", "Bot owner commands"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Load admin toggles at startup
    toggles = load_admin_toggles()
    application.bot_data['streaming_enabled'] = toggles['streaming_enabled']
    application.bot_data['vector_memory_enabled'] = toggles['vector_memory_enabled']
    logger.info("Bot command menu has been set.")

async def post_shutdown(application: Application):
    logger.info("Bot shutting down. Cancelling background tasks...")
    
    # Cancel all running background tasks
    for task in list(background_tasks): # Iterate over a copy as the set might change during iteration
        task.cancel()
    
    # Wait for all background tasks to finish, handling potential CancelledError
    if background_tasks: # Check if there are any tasks to wait for
        # Give tasks a moment to wrap up. A short timeout helps avoid hanging.
        done, pending = await asyncio.wait(background_tasks, timeout=5.0) 
        
        for task in done:
            if task.exception():
                # Only log exceptions that are NOT CancelledError, as CancelledError
                # signifies a successful, intended cancellation.
                if not isinstance(task.exception(), asyncio.CancelledError):
                    logger.error(f"Background task {task.get_name()} raised an unexpected exception during shutdown: {task.exception()}", exc_info=True)
                else:
                    # Optional: Log successful cancellation for clarity, useful during debugging shutdown.
                    logger.info(f"Background task {task.get_name()} was successfully cancelled during shutdown.")

        for task in pending:
            logger.warning(f"Background task {task.get_name()} is still pending after shutdown timeout.")
    
    logger.info("All background tasks cancelled and awaited.")

def create_app() -> Application:
    """Builds and configures the Telegram Application object."""
    ensure_directories() # Ensure directories early, before logging attempts to write files
    logging_utils.setup_logging() # Centralized logging setup
    if config.DEBUG_LOGGING:
        logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
        logging.getLogger("src.utils.files").setLevel(logging.DEBUG)
        logger.info("Telegram and File Utils extensive debug logging is ENABLED.")
    else:
        logging.getLogger("telegram.ext").setLevel(logging.INFO)
        logging.getLogger("src.utils.files").setLevel(logging.INFO)

    persistence = PicklePersistence(
        filepath=os.path.join(config.PERSISTENCE_DIR, "bot_persistence.pickle")
    )
    
    application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_error_handler(error_handler.handle_error)

    # Register all other handlers
    handlers.admin.register(application)
    handlers.user.register(application)
    handlers.conversation.register(application)
    handlers.chat.register(application)

    logger.info("Application setup complete. All services and handlers are registered.")
    return application