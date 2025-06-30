# src/handlers/user.py
"""
Handles general user commands like /start, /help, etc.
"""
import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from telegram.constants import ParseMode # Ensure ParseMode is imported for HTML
import time # For status_command uptime calculation
from datetime import timedelta, datetime # For formatting uptime and summary timestamp

import src.config as config
from src.utils import logging as logging_utils
from src.services import database as db_service # For clearing history, getting summaries
from src.services import ai_models as ai_service # For regenerate, and AI status
from src.services import monitoring as monitoring_service # For system metrics
import asyncio # For regenerate and summarization task

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays a help message."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /help")

    vector_memory_enabled = context.bot_data.get('vector_memory_enabled', False)

    help_text = """
<b>ℹ️ Available Commands</b>

<b>⚙️ Setup & Session:</b>
•  ▶️ /start - Begin a new chat session (clears history).
•  ▶️ /setup - Open the main settings menu.

<b>💬 In-Conversation:</b>
•  🔄 /regenerate - Redo the last AI response.
•  🗑️ /clear - Wipe the current conversation history.
"""

    if vector_memory_enabled: # Only show these if vector memory is enabled
        help_text += """
•  📝 /summarize - Manually create a new memory summary.
•  🧠 /memory - View the bot's latest memory summaries.
"""

    help_text += """
<b>🌐 General:</b>
•  📡 /status - View the bot's operational status.
•  🦉 /about - Learn more about this bot.
•  🆘 /help - Display this help message.
"""

    if user.id == config.BOT_OWNER_ID:
        help_text += """
<b>👑 Admin Commands (Owner Only):</b>
•  ⚙️ /admin - Access the bot's admin panel.
•  🚫 /block &lt;user_id&gt; [duration_hours] [reason] - Block a user from using the bot.
•  ✅ /unblock &lt;user_id&gt; - Unblock a user.
•  📜 /blocklist - View all currently blocked users.
"""
    await update.message.reply_html(help_text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the conversation history for the current chat."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /clear")

    chat_id = update.effective_chat.id
    await db_service.clear_history(chat_id)
    context.chat_data.pop('messages_since_last_summary', None)
    context.chat_data.pop('scenery_name', None)
    context.chat_data.pop('scenery', None)
    context.chat_data.pop('persona_name', None)
    context.chat_data.pop('persona_prompt', None)


    await update.message.reply_text("✅ Conversation history and current context have been cleared.")


async def regenerate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Regenerates the last AI response by re-sending the last user message."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /regenerate")

    chat_id = update.effective_chat.id

    # 1. Delete the last AI response from history and from Telegram (if message_id is stored)
    await db_service.delete_last_interaction(chat_id)

    # Try to delete the last bot message from Telegram if its ID was stored
    last_bot_message_id = context.chat_data.pop('last_bot_message_id', None)
    if last_bot_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_bot_message_id)
        except Exception as e:
            logger.warning(f"Could not delete last bot message {last_bot_message_id} in chat {chat_id}: {e}")

    # 2. Get the last user message from history
    history = await db_service.get_history_from_db(chat_id, limit=1)
    if not history or history[0]["role"] != "user":
        await update.message.reply_text("🤔 No previous user message to regenerate from. Please send a new message.")
        return

    last_user_message_content = history[0]["content"]

    # 3. Simulate receiving the last user message again to trigger chat_handler
    # This involves calling the chat_handler directly as if the user sent the message.
    # We need to create a dummy Update object for the chat_handler.

    # Create a dummy message object
    dummy_message = update.effective_message.copy()
    dummy_message.text = last_user_message_content
    # The Update object needs to reference this dummy message
    dummy_update = Update(update_id=update.update_id, message=dummy_message, effective_user=update.effective_user, effective_chat=update.effective_chat, effective_message=dummy_message)

    from src.handlers.chat import chat_handler # Import here to avoid circular dependency
    await chat_handler(dummy_update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the bot's operational status and system metrics."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /status")

    ai_online = context.bot_data.get('ai_service_online', False)
    metrics = monitoring_service.get_system_metrics()

    uptime_seconds = monitoring_service.performance_monitor.get_overall_stats().get('uptime_seconds', 0)
    uptime_delta = timedelta(seconds=int(uptime_seconds))

    status_msg = (
        f"<b>📡 Bot Status</b>\n\n"
        f"<b>AI Service:</b> {'✅ Online' if ai_online else '❌ Offline'}\n"
        f"<b>Uptime:</b> {str(uptime_delta).split('.')[0]}\n"
        f"<b>CPU Load:</b> {metrics.get('cpu_load', 'N/A'):.1f}%\n"
    )
    if metrics.get('gpu_load') is not None:
        status_msg += f"<b>GPU Load:</b> {metrics.get('gpu_load', 'N/A'):.1f}%\n"
    status_msg += f"<b>Memory Usage:</b> {metrics.get('memory_percent', 'N/A'):.1f}%\n"
    status_msg += f"<b>Active Conversations (1h):</b> {metrics.get('active_conversations_1h', 'N/A')}\n"
    status_msg += f"<b>Total Messages Processed:</b> {monitoring_service.performance_monitor.get_overall_stats().get('completed_requests', 0)}"

    await update.message.reply_html(status_msg)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays information about the bot."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /about")

    about_text = """
<b>🦉 About This Bot</b>

I am an AI-powered Telegram bot, designed for interactive conversations and role-playing!

<b>Powered By:</b>
•  A local Large Language Model (LLM) server (e.g., LM Studio).
•  The Python Telegram Bot library.
•  SQLite for conversation history.
•  ChromaDB for semantic memory (if enabled).

<b>Open Source:</b>
This bot is an open-source project, allowing anyone to run and customize their own version. You can find the source code and more information here:
➡️ GitHub Repository: https://github.com/TursiThePanda/Telegram_AI_Bot_2.0

<b>Disclaimer:</b>
This bot is an experiment and may be offline during certain hours. Data may be purged during development updates.
"""
    await update.message.reply_html(about_text, disable_web_page_preview=True)

async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually triggers a conversation summary if vector memory is enabled."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /summarize")

    if not context.bot_data.get('vector_memory_enabled', False):
        await update.message.reply_text("🧠 Vector memory is currently disabled, so manual summarization is not available.")
        return

    chat_id = update.effective_chat.id
    current_messages_since_summary = context.chat_data.get('messages_since_last_summary', 0)

    if current_messages_since_summary < config.SUMMARY_THRESHOLD:
        await update.message.reply_text(
            f"ℹ️ Not enough new messages ({current_messages_since_summary} of {config.SUMMARY_THRESHOLD}) to create a new summary. Keep chatting!"
        )
        return

    await update.message.reply_text("⏳ Generating a conversation summary and updating memory...")
    
    # Import _run_summarization_task locally to avoid circular dependencies if chat.py imports user.py
    from src.handlers.chat import _run_summarization_task
    
    # Run the summarization task in the background
    asyncio.create_task(_run_summarization_task(context, chat_id))
    
    await update.message.reply_text("✅ Summarization task initiated. It will complete in the background.")

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Views the bot's latest memory summaries."""
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /memory")

    if not context.bot_data.get('vector_memory_enabled', False):
        await update.message.reply_text("🧠 Vector memory is currently disabled, so there are no summaries to view.")
        return

    chat_id = update.effective_chat.id
    summaries = await db_service.get_summaries_from_db(chat_id, limit=5) # Get latest 5 summaries

    if not summaries:
        await update.message.reply_text("🧠 No memory summaries found for this conversation yet. Keep chatting!")
        return

    response_text = "<b>🧠 Latest Memory Summaries:</b>\n\n"
    for i, summary in enumerate(summaries):
        # Summaries are stored with "Memory Summary: " prefix, remove it for display
        clean_summary = summary.replace("Memory Summary: ", "").strip()
        response_text += f"<b>{i+1}.</b> <i>{clean_summary}</i>\n\n"

    await update.message.reply_html(response_text)


def register(application):
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("regenerate", regenerate_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("summarize", summarize_command)) # Register new summarize command
    application.add_handler(CommandHandler("memory", memory_command))     # Register new memory command