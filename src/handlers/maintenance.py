# src/handlers/maintenance.py
"""
Admin-only maintenance menu for dangerous dev/testing actions.
Allows deleting __pycache__, persistence, and database folders.
"""

import os
import shutil
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import src.config as config

logger = logging.getLogger(__name__)

def is_owner(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == config.BOT_OWNER_ID

# --- Maintenance Menu Logic ---

async def maintenance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("❌ This menu is for the bot owner only.")
        return

    text = (
        "<b>🛠️ Maintenance Menu</b>\n\n"
        "⚠️ <i>Dangerous development actions for admin only!</i>"
    )
    buttons = [
        [InlineKeyboardButton("🧹 Delete all __pycache__ folders", callback_data="mntn_del_pycache")],
        [InlineKeyboardButton("🗑️ Delete ALL persistence data", callback_data="mntn_del_persistence")],
        [InlineKeyboardButton("💣 Delete ALL database data", callback_data="mntn_del_database")],
        [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise

# --- Confirmation prompt handler ---
async def maintenance_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.replace("mntn_", "")
    text = ""
    btns = []
    if action == "del_pycache":
        text = "⚠️ Are you sure you want to DELETE all __pycache__ directories in the bot?"
        btns = [
            [InlineKeyboardButton("✅ Yes, delete __pycache__", callback_data="mntn_confirm_del_pycache")],
            [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
        ]
    elif action == "del_persistence":
        text = "⚠️ Are you sure you want to DELETE the entire /data/persistence folder?\nThis will wipe all conversation and state!"
        btns = [
            [InlineKeyboardButton("✅ Yes, delete persistence", callback_data="mntn_confirm_del_persistence")],
            [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
        ]
    elif action == "del_database":
        text = "⚠️ Are you sure you want to DELETE the entire /data/database folder?\nThis will wipe all database and vector memory!"
        btns = [
            [InlineKeyboardButton("✅ Yes, delete database", callback_data="mntn_confirm_del_database")],
            [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
        ]
    elif action == "exit":
        text = "Exited maintenance menu."
        await query.edit_message_text(text)
        return
    else:
        text = "Unknown maintenance action."
        await query.edit_message_text(text)
        return

    markup = InlineKeyboardMarkup(btns)
    await query.edit_message_text(text, reply_markup=markup)

# --- Deletion logic handlers ---
async def do_delete_pycache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    deleted = []
    for root, dirs, files in os.walk(os.getcwd()):
        if "__pycache__" in dirs:
            pyc_dir = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pyc_dir)
                deleted.append(pyc_dir)
            except Exception as e:
                logger.error(f"Failed to delete {pyc_dir}: {e}")
    msg = f"✅ Deleted {len(deleted)} __pycache__ directories." if deleted else "No __pycache__ folders found."
    buttons = [
        [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(msg, reply_markup=markup)
    logger.warning(f"ADMIN DELETED __pycache__: {deleted}")

async def do_delete_persistence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    folder = config.PERSISTENCE_DIR
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder)
            msg = "✅ Persistence folder deleted."
            logger.warning(f"ADMIN DELETED persistence folder: {folder}")
        except Exception as e:
            msg = f"❌ Error deleting persistence: {e}"
            logger.error(f"Failed to delete persistence: {e}")
    else:
        msg = "Persistence folder does not exist."
    buttons = [
        [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(msg, reply_markup=markup)

async def do_delete_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    folder = config.DB_DIR
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder)
            msg = "✅ Database folder deleted."
            logger.warning(f"ADMIN DELETED database folder: {folder}")
        except Exception as e:
            msg = f"❌ Error deleting database: {e}"
            logger.error(f"Failed to delete database: {e}")
    else:
        msg = "Database folder does not exist."
    buttons = [
        [InlineKeyboardButton("« Back to Maintenance Menu", callback_data="mntn_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(msg, reply_markup=markup)

# --- Register maintenance handlers ---
def register(application: Application):
    application.add_handler(CommandHandler("maintenance", maintenance_menu))
    application.add_handler(CallbackQueryHandler(maintenance_confirm, pattern="^mntn_del_"))
    application.add_handler(CallbackQueryHandler(do_delete_pycache, pattern="^mntn_confirm_del_pycache$"))
    application.add_handler(CallbackQueryHandler(do_delete_persistence, pattern="^mntn_confirm_del_persistence$"))
    application.add_handler(CallbackQueryHandler(do_delete_database, pattern="^mntn_confirm_del_database$"))
    application.add_handler(CallbackQueryHandler(maintenance_menu, pattern="^mntn_back$"))   # <--- This is new
    application.add_handler(CallbackQueryHandler(maintenance_confirm, pattern="^mntn_exit$"))
