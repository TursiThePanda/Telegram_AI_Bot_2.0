# src/handlers/conversation/data_management.py
"""
Handles the conversation flow for deleting user data, such as chat
history and custom personas/sceneries.
"""
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import html # Import html for escaping names in messages


import src.config as config
from src.services import database as db_service
from src.utils import logging as logging_utils


# Helper to truncate names for callback answers
def _truncate_name_for_answer(name: str, max_len: int = 40) -> str:
    return name[:max_len] + "..." if len(name) > max_len else name


async def delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the data deletion confirmation menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Delete Data Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("🗑️ Delete Chat History", callback_data="del_history")],
        [InlineKeyboardButton("👤 Delete a Custom Persona", callback_data="del_custom_persona_menu")],
        [InlineKeyboardButton("🏞️ Delete a Custom Scenery", callback_data="del_custom_scenery_menu")],
        [InlineKeyboardButton("💥 DELETE ALL MY DATA", callback_data="del_all")],
        [InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")]
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
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    choice = query.data
    chat_id = update.effective_chat.id

    if choice == 'del_history':
        await db_service.clear_history(chat_id)
        buttons = [
            [InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("✅ Chat history and memories have been cleared.", reply_markup=markup)
        return config.DELETE_MENU

    elif choice == 'del_all':
        await db_service.clear_history(chat_id)
        context.user_data.clear()
        context.chat_data.clear()
        await query.edit_message_text("✅ All your data has been deleted. Use /start to begin again.")
        return ConversationHandler.END

    return config.DELETE_MENU

async def select_persona_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a menu of the user's custom personas for deletion."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Persona Delete Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    custom_personas = context.user_data.get('custom_personas', {})
    if not custom_personas:
        buttons = [[InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")]]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("You have no custom personas to delete.", reply_markup=markup)
        return config.DELETE_MENU

    buttons = []
    context.user_data['temp_persona_delete_map'] = {}
    temp_idx = 0

    for name in sorted(custom_personas.keys()):
        context.user_data['temp_persona_delete_map'][str(temp_idx)] = name
        buttons.append([InlineKeyboardButton(f"❌ {html.escape(name)}", callback_data=f"del_specific_persona_idx_{temp_idx}")])
        temp_idx += 1

    buttons.append([InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")])

    await query.edit_message_text("Select a custom persona to delete:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.DELETE_CUSTOM_PERSONA_SELECT

async def delete_specific_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Deletes a specific custom persona chosen by the user and returns to the persona deletion menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Deleting custom persona. Callback data: '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()

    callback_data_parts = query.data.split('_')
    if len(callback_data_parts) < 5 or callback_data_parts[3] != "idx":
        logger.error(f"Invalid callback data for deleting persona: {query.data}")
        await query.edit_message_text("❌ Error: Invalid persona deletion data.")
        return await select_persona_to_delete(update, context)

    index_to_delete = callback_data_parts[4]
    
    persona_name = context.user_data.get('temp_persona_delete_map', {}).pop(index_to_delete, None)
    context.user_data.pop('temp_persona_delete_map', None) # Clear the entire map

    if persona_name:
        custom_personas = context.user_data.get('custom_personas', {})
        if persona_name in custom_personas:
            del custom_personas[persona_name]
            context.user_data['custom_personas'] = custom_personas
            
            if context.chat_data.get('persona_name') == persona_name:
                context.chat_data.pop('persona_name', None)
                context.chat_data.pop('persona_prompt', None)

            short_name = _truncate_name_for_answer(persona_name)
            await query.answer(f"Persona '{html.escape(short_name)}' has been deleted.")
        else:
            await query.answer(f"Persona '{html.escape(persona_name)}' not found.", show_alert=True)
    else:
        await query.answer("Error: Persona not found or session expired.", show_alert=True)

    return await select_persona_to_delete(update, context)


# --- Custom Scenery Deletion Functions ---

async def select_scenery_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a menu of the user's custom sceneries for deletion."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Scenery Delete Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()

    custom_sceneries = context.user_data.get('custom_sceneries', {})
    if not custom_sceneries:
        buttons = [[InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")]]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("You have no custom sceneries to delete.", reply_markup=markup)
        return config.DELETE_MENU

    buttons = []
    context.user_data['temp_scenery_delete_map'] = {}
    temp_idx = 0

    for name in sorted(custom_sceneries.keys()):
        context.user_data['temp_scenery_delete_map'][str(temp_idx)] = name
        buttons.append([InlineKeyboardButton(f"❌ {html.escape(name)}", callback_data=f"del_specific_scenery_idx_{temp_idx}")])
        temp_idx += 1

    buttons.append([InlineKeyboardButton("« Back to Delete Menu", callback_data="del_menu_back")])

    await query.edit_message_text("Select a custom scenery to delete:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.DELETE_CUSTOM_SCENERY_SELECT

async def delete_specific_scenery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Deletes a specific custom scenery chosen by the user and returns to the scenery deletion menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Deleting custom scenery. Callback data: '{update.callback_query.data}'")

    query = update.callback_query
    # Parse the index from the callback_data
    callback_data_parts = query.data.split('_') # e.g., ["del", "specific", "scenery", "idx", "0"]
    if len(callback_data_parts) < 5 or callback_data_parts[3] != "idx":
        logger.error(f"Invalid callback data for deleting scenery: {query.data}")
        await query.answer("❌ Error: Invalid scenery deletion data.", show_alert=True) # Answer query to prevent "loading"
        return await select_scenery_to_delete(update, context)

    index_to_delete = callback_data_parts[4]

    # Retrieve the actual scenery name using the index from the temporary map
    scenery_name = context.user_data.get('temp_scenery_delete_map', {}).pop(index_to_delete, None) # Pop to remove it

    # Clean up the entire map after processing a selection to avoid stale data
    context.user_data.pop('temp_scenery_delete_map', None)

    if scenery_name:
        custom_sceneries = context.user_data.get('custom_sceneries', {})
        if scenery_name in custom_sceneries:
            del custom_sceneries[scenery_name]
            context.user_data['custom_sceneries'] = custom_sceneries

            if context.chat_data.get('scenery_name') == scenery_name:
                context.chat_data.pop('scenery_name', None)
                context.chat_data.pop('scenery', None)

            # Truncate name for the callback answer message
            short_name = _truncate_name_for_answer(scenery_name)
            await query.answer(f"Scenery '{html.escape(short_name)}' has been deleted.")
        else:
            await query.answer(f"Scenery '{html.escape(scenery_name)}' not found.", show_alert=True)
    else:
        await query.answer("Error: Scenery not found or session expired.", show_alert=True)

    return await select_scenery_to_delete(update, context)


def get_states():
    """Returns the state handlers for the data management module."""
    from .hub import setup_hub_command

    return {
        config.DELETE_MENU: [
            CallbackQueryHandler(delete_data_choice, pattern="^del_(history|all)$"),
            CallbackQueryHandler(select_persona_to_delete, pattern="^del_custom_persona_menu$"),
            CallbackQueryHandler(select_scenery_to_delete, pattern="^del_custom_scenery_menu$"),
            CallbackQueryHandler(delete_menu, pattern="^del_menu_back$"),
        ],
        config.DELETE_CUSTOM_PERSONA_SELECT: [
            CallbackQueryHandler(delete_specific_persona, pattern="^del_specific_persona_idx_"),
            CallbackQueryHandler(delete_menu, pattern="^del_menu_back$"),
        ],
        config.DELETE_CUSTOM_SCENERY_SELECT: [
            CallbackQueryHandler(delete_specific_scenery, pattern="^del_specific_scenery_idx_"),
            CallbackQueryHandler(delete_menu, pattern="^del_menu_back$"),
        ],
    }