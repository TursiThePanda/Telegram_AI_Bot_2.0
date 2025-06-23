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
from src.utils import logging as logging_utils


async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the profile editing menu."""
    if config.LOG_USER_UI_INTERACTIONS and update.callback_query:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Profile Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    if query:
        await query.answer()

    name = context.user_data.get('user_display_name', 'Not Set')
    profile_text = context.user_data.get('user_profile', 'Not Set')
    gender = context.user_data.get('user_gender', 'Not Set')
    role = context.user_data.get('user_role', 'Not Set')

    display_profile_text = f"{profile_text[:120]}..." if len(profile_text) > 120 else profile_text

    text = (
        f"<b>✏️ Edit Your Info</b>\n\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Gender:</b> {gender}\n"
        f"<b>Role:</b> {role}\n"
        f"<b>Profile:</b> <i>{display_profile_text}</i>"
    )
    buttons = [
        [
            InlineKeyboardButton("Edit Name", callback_data="profile_edit_name"),
            InlineKeyboardButton("Edit Profile Text", callback_data="profile_edit_profile")
        ],
        [InlineKeyboardButton("Edit Gender/Role", callback_data="profile_edit_extras")],
        [InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    if query:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text, reply_markup=markup)
        
    return config.PROFILE_HUB

async def prompt_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to enter a new name."""
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton("« Back", callback_data="profile_menu_back")]]
    await query.message.edit_text("Please send your new character name.", reply_markup=InlineKeyboardMarkup(buttons))
    return config.EDIT_NAME_PROMPT

async def prompt_edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to enter a new profile description."""
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton("« Back", callback_data="profile_menu_back")]]
    await query.message.edit_text("Please send your new character profile description.", reply_markup=InlineKeyboardMarkup(buttons))
    return config.EDIT_PROFILE_PROMPT

async def prompt_edit_extras(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows a menu to edit Gender or Role."""
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("Edit Gender", callback_data="edit_gender")], # Changed pattern
        [InlineKeyboardButton("Edit Role", callback_data="edit_role")],     # Changed pattern
        [InlineKeyboardButton("« Back", callback_data="profile_menu_back")]
    ]
    await query.edit_message_text("What would you like to edit?", reply_markup=InlineKeyboardMarkup(buttons))
    return config.EDIT_EXTRAS_MENU

# --- NEW: Async function to handle the 'Edit Gender' button press ---
async def prompt_edit_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the gender selection menu for editing."""
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("Male", callback_data="gender_Male"), InlineKeyboardButton("Female", callback_data="gender_Female")],
        [InlineKeyboardButton("Non-binary", callback_data="gender_Non-binary")]
    ]
    await query.edit_message_text("Please select your character's new gender.", reply_markup=InlineKeyboardMarkup(buttons))
    return config.ASK_GENDER

# --- NEW: Async function to handle the 'Edit Role' button press ---
async def prompt_edit_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the role selection menu for editing."""
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("Dominant", callback_data="role_Dominant"), InlineKeyboardButton("Submissive", callback_data="role_Submissive")],
        [InlineKeyboardButton("Switch", callback_data="role_Switch")]
    ]
    await query.edit_message_text("Please select your character's new role.", reply_markup=InlineKeyboardMarkup(buttons))
    return config.ASK_ROLE


async def receive_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new character name and returns to the profile menu."""
    name = update.message.text.strip()
    context.user_data['user_display_name'] = name
    await update.message.reply_text(f"✅ Name updated to: <b>{name}</b>", parse_mode=ParseMode.HTML)
    return await profile_menu(update, context)


async def receive_new_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new character profile and returns to the profile menu."""
    profile = update.message.text.strip()
    context.user_data['user_profile'] = profile
    await update.message.reply_text("✅ Profile updated.")
    return await profile_menu(update, context)

def get_states():
    """Returns the state handlers for the profile editing module."""
    # We re-use the handlers from the initial setup flow for saving the data
    from .entry import receive_gender_for_setup, receive_role_for_setup
    
    return {
        config.PROFILE_HUB: [
            CallbackQueryHandler(prompt_edit_name, pattern="^profile_edit_name$"),
            CallbackQueryHandler(prompt_edit_profile, pattern="^profile_edit_profile$"),
            CallbackQueryHandler(prompt_edit_extras, pattern="^profile_edit_extras$"),
        ],
        config.EDIT_NAME_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_name)],
        config.EDIT_PROFILE_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_profile)],
        config.EDIT_EXTRAS_MENU: [
            # --- UPDATED: Use the new async handler functions ---
            CallbackQueryHandler(prompt_edit_gender, pattern="^edit_gender$"),
            CallbackQueryHandler(prompt_edit_role, pattern="^edit_role$"),
            CallbackQueryHandler(profile_menu, pattern="^profile_menu_back$"),
        ],
        # Add handlers to the main setup states. When a gender or role button is pressed,
        # these handlers will save the data and then return to the profile menu.
        config.ASK_GENDER: [CallbackQueryHandler(receive_gender_for_setup, pattern="^gender_")],
        config.ASK_ROLE: [CallbackQueryHandler(receive_role_for_setup, pattern="^role_")],
    }