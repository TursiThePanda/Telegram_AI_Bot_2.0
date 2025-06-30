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
background_tasks = set()

# Ensure required directories exist
REQUIRED_DIRS = [
    config.DATA_DIR,
    config.LOGS_DIR,
    config.USER_LOGS_DIR,
    config.PERSISTENCE_DIR,
    config.DB_DIR,
    config.PERSONAS_PATH,
    config.SCENERIES_PATH,
]

def ensure_directories():
    for path in REQUIRED_DIRS:
        try:
            os.makedirs(path, exist_ok=True)
            logger.debug(f"Ensured directory exists: {path}")
        except Exception as e:
            logger.critical(f"Failed to create directory {path}: {e}")
            # If critical directories cannot be created, raise to prevent bot from starting
            raise RuntimeError(f"FATAL: Could not create essential directory {path}. Exiting.") from e

async def post_init(application: Application):
    # Local import to avoid potential circular dependency during startup phase
    from src.handlers.admin import load_admin_toggles

    ensure_directories() # Ensure directories early, before logging attempts to write files

    # Initialize services after directories are ensured and config is loaded
    services.database.init_db()
    services.ai_models.init_ai_client()
    if services.ai_models.ai_client is None:
        logger.critical("AI client could not be initialized. Bot cannot function without AI service.")
        # Depending on desired behavior, could raise an exception to stop startup
        # For now, will continue but AI functionality will be severely limited.
        pass

    # Load personas and sceneries from their respective directories in the root
    # Use config.PERSONAS_PATH and config.SCENERIES_PATH directly
    application.bot_data['personas'] = file_utils.load_from_directory(config.PERSONAS_PATH, key_name="name")
    sceneries_full_data = file_utils.load_from_directory(config.SCENERIES_PATH, key_name="name")
    application.bot_data['sceneries_full_data'] = sceneries_full_data
    application.bot_data['sceneries'] = { name: data.get('description', '') for name, data in sceneries_full_data.items() }
    logger.info(f"Loaded {len(application.bot_data['personas'])} personas and {len(application.bot_data['sceneries'])} sceneries.")

    logger.info("Starting background tasks...")
    task_coroutines = [
        tasks.health_check_task(application),
        tasks.unblock_users_task(application) # New: Task to unblock timed users
    ]

    if config.PERFORMANCE_REPORTING_ENABLED:
        task_coroutines.append(tasks.performance_report_task())
        logger.info("Performance reporting is ENABLED by config.")
    else:
        logger.info("Performance reporting is DISABLED by config.")

    for task_coro in task_coroutines:
        task = asyncio.create_task(task_coro)
        background_tasks.add(task)
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
    application.bot_data['streaming_enabled'] = toggles.get('streaming_enabled', False)
    application.bot_data['vector_memory_enabled'] = toggles.get('vector_memory_enabled', config.VECTOR_MEMORY_ENABLED)
    logger.info("Bot command menu has been set.")

async def post_shutdown(application: Application):
    logger.info("Bot shutting down. Cancelling background tasks...")

    # Cancel all running background tasks
    for task in list(background_tasks):
        task.cancel()

    if background_tasks:
        done, pending = await asyncio.wait(background_tasks, timeout=5.0)

        for task in done:
            if task.exception():
                if not isinstance(task.exception(), asyncio.CancelledError):
                    logger.error(f"Background task {task.get_name()} raised an unexpected exception during shutdown: {task.exception()}", exc_info=True)
                else:
                    logger.info(f"Background task {task.get_name()} was successfully cancelled during shutdown.")

        for task in pending:
            logger.warning(f"Background task {task.get_name()} is still pending after shutdown timeout.")
            await asyncio.sleep(0.1) # Give a moment for log messages to print

    logger.info("All background tasks cancelled and awaited.")

def create_app() -> Application:
    """Builds and configures the Telegram Application object."""
    ensure_directories()
    logging_utils.setup_logging()
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