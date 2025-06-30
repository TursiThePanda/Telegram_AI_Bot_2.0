# src/handlers/conversation/entry.py
"""
Handles the entry and exit points for the main conversation, including
the initial user onboarding flow.
"""
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from telegram.constants import ParseMode

import src.config as config
from src.services import database as db_service
from src.utils import module_loader
from src.utils import logging as logging_utils

NSFW_MODULE_AVAILABLE = module_loader.is_module_available("src.handlers.nsfw")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This function was already provided in a previous response
    # It remains the same, with the announcement text added
    user = update.effective_user
    if config.LOG_USER_COMMANDS:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /start")

    announcement_text = """<b>A quick note about how I work.</b>

I’m a little different from most bots. I run a powerful Large Language Model (LLM) locally, right on my owner's personal computer. This allows for some cool experimentation!

However, it also means I have some limitations. To conserve energy, my owner powers down their PC at night, so I will be offline during nighttime hours (CEST/CET).

I am truly sorry if you stop by for a roleplay or a chat during my downtime and I can't respond. I know it's disappointing to find me unavailable.

<b>Why not run 24/7 on a server?</b>
Powering an LLM like me requires significant hardware resources, specifically a high-end GPU. Renting a server with that kind of power is very expensive, and since this bot is primarily an experiment to explore LLM and Telegram capabilities, it's not feasible right now.

<b>Want to run your own version?</b>
The great news is that you can run this bot yourself! My owner has made the entire project open-source. You can download the bot, run a local LLM server like LM Studio on your own PC, and play with it as much as you want, whenever you want.

You can find everything you need right here:
➡️ GitHub Repository: https://github.com/TursiThePanda/Telegram_AI_Bot_2.0

⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️

Please understand that this bot is under continuous development and it can and it will happen that the bot data is frequently purged while a new version with bug fixes is introduced.

⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️

Thanks for your understanding and happy experimenting!
"""
    await update.message.reply_html(announcement_text, disable_web_page_preview=True)

    chat_id = update.effective_chat.id
    context.chat_data['chat_id'] = chat_id
    context.user_data['user_id'] = user.id

    if motd := context.bot_data.get('motd'):
        await update.message.reply_html(f"<b>Message of the Day</b>\n\n{motd}")

    if 'user_display_name' in context.user_data:
        await update.message.reply_text(f"Welcome back, {context.user_data['user_display_name']}!")
        await db_service.clear_history(user.id)
        return ConversationHandler.END
    else:
        await update.message.reply_html("<b>Welcome!</b> Let's create your character.\n\nFirst, what is your character's name?")
        return config.START_SETUP_NAME


async def receive_name_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the user's character name and asks for their profile."""
    name = update.message.text.strip()
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided character name: '{name}'")
    context.user_data['user_display_name'] = name
    text = (
        "Name set.\n\n"
        "Now, please describe your character's profile (e.g., appearance, personality, species, kinks).\n\n"
        "<i>For the best results, please write in the third person (e.g., \"He is a brave knight...\").</i>"
    )
    await update.message.reply_html(text)
    return config.ASK_PROFILE

async def receive_profile_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the user's profile and asks for their gender."""
    profile = update.message.text.strip()
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided character profile:\n{profile}")
    context.user_data['user_profile'] = profile

    buttons = [
        [InlineKeyboardButton("Male", callback_data="gender_Male"), InlineKeyboardButton("Female", callback_data="gender_Female")],
        [InlineKeyboardButton("Non-binary", callback_data="gender_Non-binary")]
    ]
    await update.message.reply_text("Profile set. Now, what is your character's gender?", reply_markup=InlineKeyboardMarkup(buttons))
    return config.ASK_GENDER

async def receive_gender_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves gender and asks for role."""
    query = update.callback_query
    await query.answer()
    context.user_data['user_gender'] = query.data.replace("gender_", "")
    buttons = [
        [InlineKeyboardButton("Dominant", callback_data="role_Dominant"), InlineKeyboardButton("Submissive", callback_data="role_Submissive")],
        [InlineKeyboardButton("Switch", callback_data="role_Switch")]
    ]
    await query.edit_message_text("Gender set. What is your character's preferred role?", reply_markup=InlineKeyboardMarkup(buttons))
    return config.ASK_ROLE

async def receive_role_for_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves role and concludes the structured part of setup."""
    query = update.callback_query
    await query.answer()
    context.user_data['user_role'] = query.data.replace("role_", "")
    
    if NSFW_MODULE_AVAILABLE:
        buttons = [
            [InlineKeyboardButton("Yes, enable NSFW", callback_data="onboard_nsfw_yes")],
            [InlineKeyboardButton("No, keep it SFW", callback_data="onboard_nsfw_no")]
        ]
        await query.edit_message_text(
            "Role set. Would you like to enable optional NSFW features and content?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return config.ASK_NSFW_ONBOARDING
    else:
        await query.edit_message_text("✅ Profile set! You can now start chatting. Use /setup to change settings later.")
        return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic cancel command to exit any conversation state."""
    # ... (rest of the file is the same)
    if config.LOG_USER_COMMANDS:
        user = update.effective_user
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"COMMAND: /cancel")

    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


def get_entry_points():
    """Returns the entry points for the conversation."""
    from .hub import setup_hub_command
    return [
        CommandHandler("start", start_command),
        CommandHandler("setup", setup_hub_command),
    ]

def get_fallbacks():
    """Returns the fallbacks for the conversation."""
    from .hub import setup_hub_command
    from .persona import persona_menu
    from .profile import profile_menu
    
    return [
        CallbackQueryHandler(setup_hub_command, pattern="^hub_back$"),
        CallbackQueryHandler(persona_menu, pattern="^persona_menu_back$"),
        CallbackQueryHandler(profile_menu, pattern="^profile_menu_back$"),
        CommandHandler("cancel", cancel_command)
    ]

def get_states():
    """Returns the state handlers managed by this module."""
    if NSFW_MODULE_AVAILABLE:
        from src.handlers.nsfw import nsfw_onboarding_handler
    
    states = {
        config.START_SETUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name_for_setup)],
        config.ASK_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_profile_for_setup)],
        config.ASK_GENDER: [CallbackQueryHandler(receive_gender_for_setup, pattern="^gender_")],
        config.ASK_ROLE: [CallbackQueryHandler(receive_role_for_setup, pattern="^role_")],
    }
    if NSFW_MODULE_AVAILABLE:
        states[config.ASK_NSFW_ONBOARDING] = [CallbackQueryHandler(nsfw_onboarding_handler, pattern="^onboard_nsfw_")]

    return states