# src/handlers/conversation/entry.py
"""
Handles the entry and exit points for the main conversation, including
the initial user onboarding flow.
"""
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup # <--- ADD InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler


import src.config as config
from src.services import database as db_service
from src.utils import module_loader

# Check for the NSFW module once
NSFW_MODULE_AVAILABLE = module_loader.is_module_available("src.handlers.nsfw")

# --- Onboarding Functions ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /start. Routes new vs. existing users."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Crucial: Ensure chat_id is always stored for context, especially in group chats
    context.chat_data['chat_id'] = chat_id 
    context.user_data['user_id'] = user.id # Also ensure user_id is stored if not already

    if motd := context.bot_data.get('motd'):
        await update.message.reply_html(f"<b>Message of the Day</b>\n\n{motd}")

    if 'user_display_name' in context.user_data:
        await update.message.reply_text(f"Welcome back, {context.user_data['user_display_name']}!")
        await db_service.clear_history(user.id) # Clear history on re-start
        return ConversationHandler.END
    else:
        await update.message.reply_html("<b>Welcome!</b> Let's create your character.\n\nFirst, what is your character's name?")
        return config.START_SETUP_NAME

async def receive_name_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the user's character name and asks for their profile."""
    context.user_data['user_display_name'] = update.message.text.strip()
    await update.message.reply_text("Name set.\n\nNow, please describe your character's profile (e.g., appearance, personality).")
    return config.ASK_PROFILE

async def receive_profile_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the user's profile and checks if it should ask about NSFW."""
    context.user_data['user_profile'] = update.message.text.strip()

    if NSFW_MODULE_AVAILABLE:
        buttons = [[
            InlineKeyboardButton("Yes, enable NSFW", callback_data="onboard_nsfw_yes"),
            InlineKeyboardButton("No, keep it SFW", callback_data="onboard_nsfw_no")
        ]]
        await update.message.reply_text(
            "Profile set. Would you like to enable optional NSFW features and content?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return config.ASK_NSFW_ONBOARDING
    else:
        await update.message.reply_text("✅ Profile set! You can now start chatting. Use /setup to change settings later.")
        return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic cancel command to exit any conversation state."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# --- Exported Functions for the Assembler ---

def get_entry_points():
    """Returns the entry points for the conversation."""
    from .hub import setup_hub_command # Local import to avoid circular dependency
    return [
        CommandHandler("start", start_command),
        CommandHandler("setup", setup_hub_command),
    ]

def get_fallbacks():
    """Returns the fallbacks for the conversation."""
    # --- FIX: Import setup_hub_command locally to be used in the fallback ---
    from .hub import setup_hub_command
    return [
        # --- FIX: Add a callback query handler for the main "back" button ---
        CallbackQueryHandler(setup_hub_command, pattern="^hub_back$"),
        CommandHandler("cancel", cancel_command)
    ]

def get_states():
    """Returns the state handlers managed by this module."""
    # Local import here because nsfw module might not exist, handled by NSFW_MODULE_AVAILABLE
    if NSFW_MODULE_AVAILABLE:
        from src.handlers.nsfw import nsfw_onboarding_handler
    
    states = {
        config.START_SETUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name_for_setup)],
        config.ASK_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_profile_for_setup)],
    }
    if NSFW_MODULE_AVAILABLE:
        states[config.ASK_NSFW_ONBOARDING] = [CallbackQueryHandler(nsfw_onboarding_handler, pattern="^onboard_nsfw_")]

    return states