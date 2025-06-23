# src/handlers/user.py
"""
Handles general, global commands available to all users.
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service
from src.services import monitoring as monitoring_service
from src.utils import logging as logging_utils

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the public help message with available commands."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    help_text = (
        "<b>ℹ️ Available Commands</b>\n\n"
        "▶️  /start - Begin a new chat session (clears history).\n"
        "⚙️  /setup - Open the main settings menu.\n"
        "🔄  /regenerate - Redo the last AI response.\n"
        "🗑️  /clear - Wipe the current conversation history.\n"
        "📡  /status - View the bot's operational status.\n"
        "🤖  /about - Learn more about this bot.\n"
        "🆘  /help - Display this help message."
    )
    await update.message.reply_html(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays information about the bot."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    await update.message.reply_html(
        "<b>🤖 About This Bot</b>\n\n"
        "This is a sophisticated AI Role-Playing Companion designed for an immersive "
        "and interactive narrative experience."
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the public operational status of the bot's AI service."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    ai_online = await ai_service.is_service_online()
    status_msg = f"<b>📡 Bot Status</b>\n\n<b>AI Service:</b> {'✅ Online' if ai_online else '❌ Offline'}"
    await update.message.reply_html(status_msg)

async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the user's conversation history."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    await db_service.clear_history(update.effective_chat.id)
    await update.message.reply_text("✅ Conversation history and memories have been cleared.")

async def regenerate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the last interaction and re-runs the AI for the last valid user message."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    from src.handlers.chat import chat_handler
    chat_id = update.effective_chat.id

    history = await db_service.get_history_from_db(chat_id, limit=10) # Fetch more history to find a valid message
    if not history:
        await update.message.reply_text("There is no history to regenerate from.")
        return

    # Find the last message from the user that was not a command
    last_user_message = None
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "user" and not history[i].get("content", "").startswith('/'):
            # Check if the message right after this was from the assistant
            if i + 1 < len(history) and history[i+1].get("role") == "assistant":
                 last_user_message = history[i]
                 break

    if not last_user_message:
        await update.message.reply_text("Could not find a previous AI response to regenerate.")
        return

    await update.message.reply_html(f"🔄 Regenerating response for: \"<i>{last_user_message['content'][:50]}...</i>\"")
    await db_service.delete_last_interaction(chat_id)

    # We must use effective_message here for consistency with chat_handler
    if update.effective_message:
        # Create a new message object to pass to the handler
        new_update = Update(update.update_id, message=update.effective_message)
        new_update.message.text = last_user_message['content']
        await chat_handler(new_update, context)
    else:
        # This case should be rare, but as a fallback
        await update.message.reply_text("❌ Could not regenerate response due to an internal error.")


def register(application: Application):
    """Registers all public user command handlers."""
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_history_command))
    application.add_handler(CommandHandler("regenerate", regenerate_command))