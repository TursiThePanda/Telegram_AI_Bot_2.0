# src/handlers/conversation/hub.py
"""Handles the main Setup Hub menu and dispatches to sub-menus."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

import src.config as config
from src.utils import module_loader

NSFW_MODULE_AVAILABLE = module_loader.is_module_available("src.handlers.nsfw")

async def setup_hub_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main setup hub with configuration options."""
    query = update.callback_query
    if query:
        await query.answer()

    buttons = [
        [
            InlineKeyboardButton("🤖 Persona", callback_data="hub_persona"),
            InlineKeyboardButton("🏞️ Scene", callback_data="hub_scene")
        ],
        [InlineKeyboardButton("✏️ Edit Name/Profile", callback_data="hub_profile")],
        [InlineKeyboardButton("🗑️ Delete Data", callback_data="hub_delete")]
    ]
    if NSFW_MODULE_AVAILABLE:
        nsfw_status = "ON" if context.user_data.get("nsfw_enabled", False) else "OFF"
        buttons.insert(2, [InlineKeyboardButton(f"🔞 NSFW Features: {nsfw_status}", callback_data="hub_toggle_nsfw")])

    markup = InlineKeyboardMarkup(buttons)
    text = "<b>⚙️ Setup Hub</b>\n\nConfigure your character and role-playing environment."

    # Edit the message if coming from a button, otherwise send a new one.
    if query:
        await query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        
    return config.SETUP_HUB

def get_states():
    """Returns the state handlers for the hub, which dispatch to other modules."""
    from .persona import persona_menu
    from .scenery import scenery_menu
    from .profile import profile_menu
    from .data_management import delete_menu
    
    # Corrected import: Changed from relative '.nsfw' to absolute 'src.handlers.nsfw'
    if NSFW_MODULE_AVAILABLE:
        from src.handlers.nsfw import toggle_nsfw_handler

    states = {
        config.SETUP_HUB: [
            CallbackQueryHandler(persona_menu, pattern="^hub_persona$"),
            CallbackQueryHandler(scenery_menu, pattern="^hub_scene$"),
            CallbackQueryHandler(profile_menu, pattern="^hub_profile$"),
            CallbackQueryHandler(delete_menu, pattern="^hub_delete$"),
            CallbackQueryHandler(setup_hub_command, pattern="^hub_back$"),
        ]
    }
    
    if NSFW_MODULE_AVAILABLE:
        states[config.SETUP_HUB].append(CallbackQueryHandler(toggle_nsfw_handler, pattern="^hub_toggle_nsfw$"))

    return states