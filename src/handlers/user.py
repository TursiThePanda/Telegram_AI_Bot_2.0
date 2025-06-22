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
# --- MODIFICATION START: Added import for logging utils ---
from src.utils import logging as logging_utils
# --- MODIFICATION END ---

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the public help message with available commands."""
    # --- MODIFICATION START: Added command logging ---
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")
    # --- MODIFICATION END ---

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
    # --- MODIFICATION START: Added command logging ---
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")
    # --- MODIFICATION END ---

    # We previously fixed this bug, so the command now works.
    await update.message.reply_html(
        "<b>🤖 About This Bot</b>\n\n"
        "This is a sophisticated AI Role-Playing Companion designed for an immersive "
        "and interactive narrative experience." 
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the public operational status of the bot's AI service."""
    # --- MODIFICATION START: Added command logging ---
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")
    # --- MODIFICATION END ---

    ai_online = await ai_service.is_service_online()
    status_msg = f"<b>📡 Bot Status</b>\n\n<b>AI Service:</b> {'✅ Online' if ai_online else '❌ Offline'}"
    await update.message.reply_html(status_msg)

async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the user's conversation history."""
    # --- MODIFICATION START: Added command logging ---
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")
    # --- MODIFICATION END ---

    await db_service.clear_history(update.effective_chat.id)
    await update.message.reply_text("✅ Conversation history and memories have been cleared.")

async def regenerate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the last interaction and re-runs the AI for the last user message."""
    # --- MODIFICATION START: Added command logging ---
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")
    # --- MODIFICATION END ---

    from src.handlers.chat import chat_handler
    
    history = await db_service.get_history_from_db(update.effective_chat.id, limit=2)
    if len(history) < 1 or history[-1].get("role") == "user":
        await update.message.reply_text("There is no previous AI response to regenerate.")
        return
        
    last_user_message = next((msg for msg in reversed(history) if msg['role'] == 'user'), None)
    if not last_user_message:
        await update.message.reply_text("Could not find a previous message to regenerate from.")
        return

    await update.message.reply_html(f"🔄 Regenerating response for: \"<i>{last_user_message['content'][:50]}...</i>\"")
    await db_service.delete_last_interaction(update.effective_chat.id)
    
    # We must use effective_message here for consistency with chat_handler
    if update.effective_message:
        update.effective_message.text = last_user_message['content']
    
    await chat_handler(update, context)


def register(application: Application):
    """Registers all public user command handlers."""
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_history_command))
    application.add_handler(CommandHandler("regenerate", regenerate_command))