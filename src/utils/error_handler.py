# src/utils/error_handler.py
"""
Defines the global error handler for the application.
"""
import logging
import html
import json
import traceback
import time
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import telegram.constants

import src.config as config

logger = logging.getLogger(__name__)

# To prevent spamming the owner with error reports during cascading failures
LAST_ERROR_REPORT_TIME = 0
ERROR_REPORT_COOLDOWN = 30 # seconds

async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catches all uncaught exceptions and sends a detailed report to the bot owner.
    Also provides a generic error message to the user.
    """
    # First, log the error to the console/file for a persistent record.
    logger.error("Exception while handling an update:", exc_info=context.error)

    if not context.error:
        return

    # --- Send generic message to user ---
    user_message = "❌ An unexpected error occurred. Please try again later."
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            await update.effective_message.reply_text(user_message)
        except Exception as reply_error:
            logger.error(f"Failed to send error message to user: {reply_error}", exc_info=True)

    # --- Send detailed report to bot owner (rate-limited) ---
    global LAST_ERROR_REPORT_TIME
    current_time = time.time()

    if config.BOT_OWNER_ID is None:
        logger.warning("BOT_OWNER_ID is not configured. Cannot send error report to owner.")
        return

    if current_time - LAST_ERROR_REPORT_TIME < ERROR_REPORT_COOLDOWN:
        # Log the suppressed error as a warning
        logger.warning(
            f"Error report to admin skipped due to cooldown. Error: {context.error}",
            exc_info=context.error
        )
        return
    
    LAST_ERROR_REPORT_TIME = current_time

    # Format the traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Gather information about the update and user
    update_info = "N/A"
    if isinstance(update, Update):
        try:
            update_dict = update.to_dict()
            if 'message' in update_dict and 'photo' in update_dict['message']:
                update_dict['message']['photo'] = "[...photo data removed...]"
            update_info = json.dumps(update_dict, indent=2, ensure_ascii=False)
        except Exception:
            update_info = str(update)
    else:
        update_info = str(update)
    
    # Format the message to be sent to the admin
    message = (
        f"‼️ <b>An exception occurred!</b>\n\n"
        f"<b>Error:</b> <code>{html.escape(str(context.error))}</code>\n\n"
        f"<b>Update:</b>\n<pre>{html.escape(update_info)}</pre>\n\n"
        f"<b>Traceback:</b>\n<pre>{html.escape(tb_string)}</pre>"
    )

    max_len = 4096
    if len(message) > max_len:
        message = message[:max_len - (len("</pre>") + len("..."))] + "...</pre>"


    try:
        await context.bot.send_message(
            chat_id=config.BOT_OWNER_ID, text=message, parse_mode=ParseMode.HTML
        )
    except Exception as send_error:
        logger.critical(f"Failed to send error report to owner {config.BOT_OWNER_ID}: {send_error}", exc_info=True)