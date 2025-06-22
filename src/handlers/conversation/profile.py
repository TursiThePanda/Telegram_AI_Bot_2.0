# src/handlers/conversation/profile.py
"""
Handles the conversation flow for viewing and editing the user's
character name and profile description.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

import src.config as config
# --- MODIFICATION START: Added import for logging utils ---
from src.utils import logging as logging_utils
# --- MODIFICATION END ---


async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the profile editing menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Profile Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    name = context.user_data.get('user_display_name', 'Not Set')
    profile_text = context.user_data.get('user_profile', 'Not Set')

    display_profile_text = profile_text
    if len(profile_text) > 120:
        display_profile_text = f"{profile_text[:120]}..."

    text = (
        f"<b>✏️ Edit Your Info</b>\n\n"
        f"<b>Current Name:</b> {name}\n"
        f"<b>Current Profile:</b> <i>{display_profile_text}</i>"
    )
    buttons = [
        [
            InlineKeyboardButton("Edit Name", callback_data="profile_edit_name"),
            InlineKeyboardButton("Edit Profile", callback_data="profile_edit_profile")
        ],
        [InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )
    return config.PROFILE_HUB

async def prompt_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to enter a new name."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your new character name.")
    return config.EDIT_NAME_PROMPT

async def prompt_edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to enter a new profile description."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your new character profile description.")
    return config.EDIT_PROFILE_PROMPT


async def receive_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new character name and returns to the profile menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided new character name.")

    name = update.message.text.strip()
    context.user_data['user_display_name'] = name
    await update.message.reply_text(f"✅ Name updated to: <b>{name}</b>", parse_mode=ParseMode.HTML)
    
    from .hub import setup_hub_command
    return await setup_hub_command(update, context)


async def receive_new_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new character profile and returns to the profile menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided new character profile.")

    profile = update.message.text.strip()
    context.user_data['user_profile'] = profile
    await update.message.reply_text("✅ Profile updated.")

    from .hub import setup_hub_command
    return await setup_hub_command(update, context)


def get_states():
    """Returns the state handlers for the profile editing module."""
    return {
        config.PROFILE_HUB: [
            CallbackQueryHandler(prompt_edit_name, pattern="^profile_edit_name$"),
            CallbackQueryHandler(prompt_edit_profile, pattern="^profile_edit_profile$"),
        ],
        config.EDIT_NAME_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_name)],
        config.EDIT_PROFILE_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_profile)],
    }