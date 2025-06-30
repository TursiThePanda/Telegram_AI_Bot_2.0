# src/handlers/admin.py
"""
Handles administrative commands exclusive to the bot owner. Now uses a
self-contained ConversationHandler for the MOTD feature to prevent conflicts.
"""
import logging
import asyncio
import time # For timed blocks
from datetime import timedelta, datetime # For formatting timed blocks
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)
from telegram.constants import ParseMode
import html

import src.config as config
from src.utils import files as file_utils
from src.services import ai_models as ai_service
from src.services import monitoring as monitoring_service
from src.services import database as db_service # Import for blocklist
from src.utils.files import load_json, save_json
from src.utils import logging as logging_utils

import os

logger = logging.getLogger(__name__)

# --- State for the MOTD sub-conversation ---
EDITING_MOTD = range(1)

# --- Persistence file for toggles ---
TOGGLES_FILE = os.path.join(config.DATA_DIR, "admin_toggles.json")

def load_admin_toggles():
    data = load_json(TOGGLES_FILE, default={})
    return {
        "streaming_enabled": data.get("streaming_enabled", False),
        "vector_memory_enabled": data.get("vector_memory_enabled", config.VECTOR_MEMORY_ENABLED)
    }

def save_admin_toggles(context):
    data = {
        "streaming_enabled": context.bot_data.get('streaming_enabled', False),
        "vector_memory_enabled": context.bot_data.get('vector_memory_enabled', config.VECTOR_MEMORY_ENABLED)
    }
    save_json(TOGGLES_FILE, data)

def owner_only(func):
    """Decorator to restrict access to bot owner, with user feedback and logging."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if config.BOT_OWNER_ID is None:
            logger.error("BOT_OWNER_ID is not set in config. Admin commands are disabled.")
            if getattr(update, 'message', None):
                await update.message.reply_text("❌ Admin commands are not configured. Please set BOT_OWNER_ID.")
            elif getattr(update, 'callback_query', None):
                await update.callback_query.answer("❌ Admin commands not configured.", show_alert=True)
            return

        if update.effective_user.id != config.BOT_OWNER_ID:
            logger.warning(
                f"Unauthorized admin access attempt by user {update.effective_user.id} ({update.effective_user.username}). "
                f"Command/Callback: {update.effective_message.text if update.effective_message else update.callback_query.data}"
            )
            if getattr(update, 'message', None):
                await update.message.reply_text("❌ You are not authorized to use this command.")
            elif getattr(update, 'callback_query', None):
                await update.callback_query.answer("❌ Access denied.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Helper Functions for Formatting ---
def _get_performance_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    stats = monitoring_service.performance_monitor.get_overall_stats()
    uptime_delta = timedelta(seconds=int(stats.get('uptime_seconds', 0)))
    rpm = (stats.get('completed_requests', 0) / max(stats.get('uptime_seconds', 1), 1)) * 60
    return (
        f"<b>📊 Performance Metrics</b>\n\n"
        f"<b>Uptime:</b> {str(uptime_delta)}\n"
        f"<b>Completed Requests:</b> {stats.get('completed_requests', 0)}\n"
        f"<b>Success Rate:</b> {stats.get('success_rate', 1.0):.2%}\n"
        f"<b>Avg. Response Time:</b> {stats.get('average_response_time', 0):.2f}s\n"
        f"<b>Requests Per Minute:</b> {rpm:.2f}\n"
        f"<b>Active/Total Users:</b> {stats.get('active_users_1h', 0)} / {stats.get('total_users_seen', 0)}"
    )

async def _get_status_text() -> str:
    ai_online = await ai_service.is_service_online()
    metrics = monitoring_service.get_system_metrics()
    status_msg = (
        f"<b>📡 System Status</b>\n\n"
        f"<b>AI Service:</b> {'✅ Online' if ai_online else '❌ Offline'}\n"
        f"<b>CPU Load:</b> {metrics.get('cpu_load', 'N/A'):.1f}%\n"
    )
    if metrics.get('gpu_load') is not None:
        status_msg += f"<b>GPU Load:</b> {metrics.get('gpu_load', 'N/A'):.1f}%\n"
    status_msg += f"<b>Memory Usage:</b> {metrics.get('memory_percent', 'N/A'):.1f}%"
    return status_msg

# --- Menu Display Functions ---
async def _display_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main admin panel, editing the message if it's from a callback."""
    streaming_enabled = context.bot_data.get('streaming_enabled', False)
    vector_mem_enabled = context.bot_data.get('vector_memory_enabled', config.VECTOR_MEMORY_ENABLED)

    buttons = [
        [InlineKeyboardButton("📊 Performance", callback_data="admin_performance"), InlineKeyboardButton("📡 System Status", callback_data="admin_status")],
        [InlineKeyboardButton(f"💨 AI Chat Streaming: {'ON' if streaming_enabled else 'OFF'}", callback_data="admin_toggle_streaming")],
        [InlineKeyboardButton(f"🧠 Vector memory: {'ON' if vector_mem_enabled else 'OFF'}", callback_data="admin_toggle_vector")],
        [InlineKeyboardButton("📢 Manage MOTD", callback_data="admin_motd_menu")],
        [InlineKeyboardButton("🔄 Reload Files", callback_data="admin_reload")],
        [InlineKeyboardButton("🚫 Manage Blocklist", callback_data="admin_blocklist_menu")] # New: Blocklist menu
    ]
    markup = InlineKeyboardMarkup(buttons)
    text = "<b>👑 Admin Panel</b>"

    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        if update.effective_message:
            await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

# --- MOTD Sub-Conversation Handlers ---
@owner_only
async def motd_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the MOTD management sub-menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    current_motd = context.bot_data.get('motd', 'Not currently set')
    text = f"<b>📢 MOTD Management</b>\n\n<b>Current:</b>\n<i>{html.escape(current_motd)}</i>"
    buttons = [
        [InlineKeyboardButton("✍️ Edit", callback_data="admin_motd_edit"), InlineKeyboardButton("🗑️ Disable", callback_data="admin_motd_disable")],
        [InlineKeyboardButton("« Back", callback_data="admin_motd_cancel")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    return EDITING_MOTD

@owner_only
async def motd_prompt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the admin to send the new MOTD text."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    await query.message.edit_text("Please send the new Message of the Day now.")
    return EDITING_MOTD

@owner_only
async def motd_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new MOTD text and ends the sub-conversation."""
    if config.LOG_USER_COMMANDS: # Logged as a command/text input
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided MOTD text.")

    context.bot_data['motd'] = update.message.text
    await update.message.reply_text("✅ New MOTD has been set.")
    await _display_admin_menu(update, context)
    return ConversationHandler.END

@owner_only
async def motd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Disables the MOTD and ends the sub-conversation."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    context.bot_data.pop('motd', None)
    await query.message.edit_text("✅ MOTD has been disabled.")
    await asyncio.sleep(2)
    await _display_admin_menu(update, context)
    return ConversationHandler.END

@owner_only
async def motd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns to the main admin menu from the MOTD sub-menu."""
    if update.callback_query and config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")
    elif update.message and config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"COMMAND: {update.message.text}")

    if update.callback_query:
        await update.callback_query.answer()

    await _display_admin_menu(update, context)
    return ConversationHandler.END

# --- Main Admin Panel Handlers ---
@owner_only
async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the /admin command."""
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    await _display_admin_menu(update, context)

@owner_only
async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher for the main admin menu buttons."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "admin_toggle_streaming":
        context.bot_data['streaming_enabled'] = not context.bot_data.get('streaming_enabled', False)
        save_admin_toggles(context)
        await _display_admin_menu(update, context)
    elif action == "admin_toggle_vector":
        context.bot_data['vector_memory_enabled'] = not context.bot_data.get('vector_memory_enabled', config.VECTOR_MEMORY_ENABLED)
        save_admin_toggles(context)
        await _display_admin_menu(update, context)
    elif action == "admin_reload":
        await reload_command(update, context, from_callback=True)
    elif action == "admin_performance":
        text = _get_performance_text(context)
        buttons = [[InlineKeyboardButton("« Back", callback_data="admin_menu_back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    elif action == "admin_status":
        text = await _get_status_text()
        buttons = [[InlineKeyboardButton("« Back", callback_data="admin_menu_back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    elif action == "admin_blocklist_menu":
        await list_blocked_users(update, context) # Direct to blocklist view
    elif action == "admin_menu_back":
        await _display_admin_menu(update, context)

@owner_only
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool = False):
    """Reloads personas and sceneries from files."""
    if from_callback and config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data 'admin_reload'")
    elif not from_callback and config.LOG_USER_COMMANDS:
         user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
         user_logger.info(f"COMMAND: {update.effective_message.text}")

    message_target = update.callback_query.message if from_callback else update.message
    await message_target.reply_text("⏳ Reloading ...")
    try:
        personas_path_resolved = os.path.abspath(config.PERSONAS_PATH)
        sceneries_path_resolved = os.path.abspath(config.SCENERIES_PATH)
        logger.info(f"Reloading personas from: {personas_path_resolved}")
        logger.info(f"Reloading sceneries from: {sceneries_path_resolved}")
        context.bot_data['personas'] = file_utils.load_from_directory(config.PERSONAS_PATH, key_name="name")
        sceneries_data = file_utils.load_from_directory(config.SCENERIES_PATH, key_name="name")
        context.bot_data['sceneries_full_data'] = sceneries_data
        context.bot_data['sceneries'] = { name: data.get('description', '') for name, data in sceneries_data.items() }
        msg = f"✅ Reload complete: {len(context.bot_data['personas'])} personas, {len(context.bot_data['sceneries'])} sceneries."
        logger.info(msg)
    except Exception as e:
        logger.error(f"Error during /reload: {e}", exc_info=True)
        msg = f"❌ An error occurred during reload: {html.escape(str(e))}"
    await message_target.reply_text(msg)

@owner_only
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blocks a user, optionally with a duration and reason."""
    user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
    user_logger.info(f"COMMAND: {update.effective_message.text}")

    if not context.args:
        await update.message.reply_text("Usage: `/block <user_id> [duration_hours] [reason]`\nDuration is optional. Reason is optional.", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric Telegram user ID.")
        return

    if target_user_id == config.BOT_OWNER_ID:
        await update.message.reply_text("❌ You cannot block the bot owner.")
        return

    blocked_until: Optional[float] = None
    reason: Optional[str] = None

    if len(context.args) > 1:
        try:
            duration_hours = float(context.args[1])
            if duration_hours <= 0:
                raise ValueError
            blocked_until = time.time() + duration_hours * 3600
            reason_start_idx = 2
        except ValueError:
            # If second arg is not a valid number, assume it's the start of the reason
            reason_start_idx = 1

        if len(context.args) > reason_start_idx:
            reason = " ".join(context.args[reason_start_idx:])

    try:
        await db_service.add_blocked_user(target_user_id, blocked_until, reason)
        block_duration_text = f" until {datetime.fromtimestamp(blocked_until).strftime('%Y-%m-%d %H:%M:%S CEST')}" if blocked_until else " permanently"
        block_reason_text = f" (Reason: {reason})" if reason else ""
        await update.message.reply_text(f"✅ User `{target_user_id}` has been blocked{block_duration_text}{block_reason_text}.", parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Admin {update.effective_user.id} blocked user {target_user_id}{block_duration_text}{block_reason_text}.")

        # Notify the blocked user if possible
        try:
            unblock_info = f"This block is permanent." if blocked_until is None else f"You will be unblocked on {datetime.fromtimestamp(blocked_until).strftime('%Y-%m-%d %H:%M:%S CEST')}."
            reason_info = f"Reason: {reason}" if reason else "No specific reason provided."
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🚫 You have been blocked from interacting with this bot.\n\n{reason_info}\n{unblock_info}"
            )
        except Exception as e:
            logger.warning(f"Could not send block notification to user {target_user_id}: {e}")

    except Exception as e:
        logger.error(f"Error blocking user {target_user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ An error occurred while blocking user `{target_user_id}`: {html.escape(str(e))}", parse_mode=ParseMode.HTML)


@owner_only
async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblocks a user."""
    user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
    user_logger.info(f"COMMAND: {update.effective_message.text}")

    if not context.args:
        await update.message.reply_text("Usage: `/unblock <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric Telegram user ID.")
        return

    try:
        blocked_user_info = await db_service.get_blocked_user(target_user_id)
        if blocked_user_info:
            await db_service.remove_blocked_user(target_user_id)
            await update.message.reply_text(f"✅ User `{target_user_id}` has been unblocked.", parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Admin {update.effective_user.id} unblocked user {target_user_id}.")
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="✅ You have been unblocked and can now interact with the bot again."
                )
            except Exception as e:
                logger.warning(f"Could not send unblock notification to user {target_user_id}: {e}")
        else:
            await update.message.reply_text(f"ℹ️ User `{target_user_id}` is not currently blocked.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error unblocking user {target_user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ An error occurred while unblocking user `{target_user_id}`: {html.escape(str(e))}", parse_mode=ParseMode.HTML)


@owner_only
async def list_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all currently blocked users."""
    user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
    if update.callback_query:
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")
        await update.callback_query.answer()
    else:
        user_logger.info(f"COMMAND: {update.effective_message.text}")

    blocked_users = await db_service.get_all_blocked_users()

    if not blocked_users:
        text = "✅ No users are currently blocked."
    else:
        text = "<b>🚫 Currently Blocked Users:</b>\n\n"
        for user_id, blocked_until, reason in blocked_users:
            until_text = ""
            if blocked_until is not None:
                until_dt = datetime.fromtimestamp(blocked_until)
                if until_dt > datetime.now():
                    until_text = f" (Until: {until_dt.strftime('%Y-%m-%d %H:%M:%S CEST')})"
                else:
                    # Should be cleaned by unblock task, but show as expired if still listed
                    until_text = " (Expired)"
            reason_text = f" - Reason: {reason}" if reason else ""
            text += f"• `{user_id}`{until_text}{reason_text}\n"

    buttons = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_menu_back")]]
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text, reply_markup=markup)

def register(application: Application):
    """Registers all admin-related handlers."""

    motd_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(motd_menu_handler, pattern="^admin_motd_menu$")],
        states={
            EDITING_MOTD: [
                CallbackQueryHandler(motd_prompt_edit, pattern="^admin_motd_edit$"),
                CallbackQueryHandler(motd_disable, pattern="^admin_motd_disable$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, motd_receive_text)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(motd_cancel, pattern="^admin_motd_cancel$"),
            CommandHandler('cancel', motd_cancel)
        ],
        per_user=True,
        per_chat=True,
        persistent=True,
        name="motd_conversation_handler"
    )

    admin_panel_dispatcher = CallbackQueryHandler(
        admin_menu_callback,
        pattern="^admin_(toggle_streaming|toggle_vector|reload|performance|status|menu_back|blocklist_menu)$"
    )

    application.add_handler(CommandHandler("admin", admin_menu_command))
    application.add_handler(CommandHandler("block", block_user))
    application.add_handler(CommandHandler("unblock", unblock_user))
    application.add_handler(CommandHandler("blocklist", list_blocked_users))
    application.add_handler(motd_conv)
    application.add_handler(admin_panel_dispatcher)