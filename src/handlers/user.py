# src/handlers/user.py
"""
Handles general, global commands available to all users.
"""
import logging
import asyncio
import html
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service
from src.services import monitoring as monitoring_service
from src.utils import logging as logging_utils
from src.handlers.chat import _run_summarization_task # Import the task

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the public help message with available commands."""
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    # --- MODIFIED: Added new commands and organized into categories ---
    help_text = (
        "<b>ℹ️ Available Commands</b>\n\n"
        "<b>Setup & Session:</b>\n"
        "▶️  /start - Begin a new chat session (clears history).\n"
        "⚙️  /setup - Open the main settings menu.\n\n"
        "<b>In-Conversation:</b>\n"
        "🔄  /regenerate - Redo the last AI response.\n"
        "🗑️  /clear - Wipe the current conversation history.\n"
        "✍️  /summarize - Manually create a new memory summary.\n"
        "🧠  /memory - View the bot's latest memory summaries.\n\n"
        "<b>General:</b>\n"
        "📡  /status - View the bot's operational status.\n"
        "🤖  /about - Learn more about this bot.\n"
        "🆘  /help - Display this help message."
    )
    # --- END OF MODIFICATION ---
    
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

    history = await db_service.get_history_from_db(chat_id, limit=10)
    if not history:
        await update.message.reply_text("There is no history to regenerate from.")
        return

    last_user_message = None
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "user" and not history[i].get("content", "").startswith('/'):
            if i + 1 < len(history) and history[i+1].get("role") == "assistant":
                 last_user_message = history[i]
                 break

    if not last_user_message:
        await update.message.reply_text("Could not find a previous AI response to regenerate.")
        return

    await update.message.reply_html(f"🔄 Regenerating response for: \"<i>{html.escape(last_user_message['content'][:50])}...</i>\"")
    await db_service.delete_last_interaction(chat_id)

    if update.effective_message:
        new_update = Update(update.update_id, message=update.effective_message)
        new_update.message.text = last_user_message['content']
        await chat_handler(new_update, context)
    else:
        await update.message.reply_text("❌ Could not regenerate response due to an internal error.")

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the most recent memory summaries for the user."""
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"COMMAND: /memory")
    
    summaries = await db_service.get_summaries_from_db(update.effective_chat.id, limit=3)
    
    if not summaries:
        await update.message.reply_html("<b>🧠 Memory Bank</b>\n\nNo summaries have been created for this conversation yet.")
        return
        
    response_text = "<b>🧠 Recent Memory Summaries</b>\n\n"
    for i, summary in enumerate(summaries, 1):
        response_text += f"<b>Summary {i}:</b>\n<i>{html.escape(summary)}</i>\n\n"
        
    await update.message.reply_html(response_text)

async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually triggers the conversation summarization task."""
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"COMMAND: /summarize")

    await update.message.reply_text("✍️ Manually triggering a memory summary. This will happen in the background...")
    
    # Schedule the summarization task to run without blocking
    asyncio.create_task(_run_summarization_task(context, update.effective_chat.id))
    
    # We can also reset the counter here to avoid an immediate automatic summary
    context.chat_data['messages_since_last_summary'] = 0

def register(application: Application):
    """Registers all public user command handlers."""
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_history_command))
    application.add_handler(CommandHandler("regenerate", regenerate_command))
    application.add_handler(CommandHandler("summarize", summarize_command))
    application.add_handler(CommandHandler("memory", memory_command))