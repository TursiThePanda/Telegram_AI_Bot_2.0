# src/handlers/conversation/data_management.py
"""
Handles the conversation flow for deleting user data, such as chat
history and custom personas.
"""
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

import src.config as config
from src.services import database as db_service

async def delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the data deletion confirmation menu."""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("🗑️ Delete Chat History", callback_data="del_history")],
        [InlineKeyboardButton("👤 Delete a Custom Persona", callback_data="del_custom_persona_menu")],
        [InlineKeyboardButton("💥 DELETE ALL MY DATA", callback_data="del_all")],
        [InlineKeyboardButton("« Back to Setup Hub", callback_data="setup_back")]
    ]
    text = "<b>Delete Data</b>\n\n⚠️ <b>Warning:</b> These actions are permanent and cannot be undone."
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )
    return config.DELETE_MENU

async def delete_data_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's choice from the delete menu and provides appropriate navigation."""
    query = update.callback_query
    await query.answer()
    choice = query.data
    chat_id = update.effective_chat.id

    if choice == 'del_history':
        await db_service.clear_history(chat_id)
        buttons = [
            [InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")],
            [InlineKeyboardButton("« Back to Setup Hub", callback_data="setup_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("✅ Chat history and memories have been cleared.", reply_markup=markup)
        return config.DELETE_MENU

    elif choice == 'del_all':
        await db_service.clear_history(chat_id)
        context.user_data.clear()
        context.chat_data.clear()
        buttons = [
            [InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")],
            [InlineKeyboardButton("« Back to Setup Hub", callback_data="setup_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("✅ All your data has been deleted. Use /start to begin again.", reply_markup=markup)
        return ConversationHandler.END

    return config.DELETE_MENU

async def select_persona_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a menu of the user's custom personas for deletion."""
    query = update.callback_query
    await query.answer()

    custom_personas = context.user_data.get('custom_personas', {})
    if not custom_personas:
        buttons = [
            [InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")],
            [InlineKeyboardButton("« Back to Setup Hub", callback_data="setup_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("You have no custom personas to delete.", reply_markup=markup)
        return config.DELETE_MENU

    buttons = [[InlineKeyboardButton(f"❌ {name}", callback_data=f"del_specific_{name}")] for name in sorted(custom_personas.keys())]
    buttons.append([InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")])
    buttons.append([InlineKeyboardButton("« Back to Setup Hub", callback_data="setup_back")])
    
    await query.edit_message_text("Select a custom persona to delete:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.DELETE_CUSTOM_PERSONA_SELECT

async def delete_specific_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Deletes a specific custom persona chosen by the user and returns to the persona deletion menu."""
    query = update.callback_query
    persona_name = query.data.replace("del_specific_", "")
    
    custom_personas = context.user_data.get('custom_personas', {})
    if persona_name in custom_personas:
        del custom_personas[persona_name]
        context.user_data['custom_personas'] = custom_personas
        await query.answer(f"Persona '{persona_name}' has been deleted.")
    else:
        await query.answer(f"Persona '{persona_name}' not found.", show_alert=True)
        
    # Refresh the list of personas to delete
    return await select_persona_to_delete(update, context)

def get_states():
    """Returns the state handlers for the data management module."""
    return {
        config.DELETE_MENU: [
            CallbackQueryHandler(delete_data_choice, pattern="^del_(history|all)$"),
            CallbackQueryHandler(select_persona_to_delete, pattern="^del_custom_persona_menu$"),
            CallbackQueryHandler(delete_menu, pattern="^del_menu_back$"),
            CallbackQueryHandler(delete_menu, pattern="^setup_back$"),
        ],
        config.DELETE_CUSTOM_PERSONA_SELECT: [
            CallbackQueryHandler(delete_specific_persona, pattern="^del_specific_"),
            CallbackQueryHandler(delete_menu, pattern="^del_menu_back$"),
            CallbackQueryHandler(delete_menu, pattern="^setup_back$"),
        ],
    }
