# src/handlers/conversation/persona.py
"""
Handles all conversation flows related to selecting, creating,
and generating AI Personas.
"""
import asyncio
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import re
import html

import src.config as config
from src.services import ai_models as ai_service
from src.utils import module_loader
from src.utils import logging as logging_utils

logger = logging.getLogger(__name__)
NSFW_MODULE_AVAILABLE = module_loader.is_module_available("src.handlers.nsfw")

def _build_sfw_persona_prompt() -> str:
    """Builds the prompt for the AI to generate a random persona."""
    return (
        "Generate a simple, safe-for-work fantasy character persona. "
        "Your response MUST be formatted as follows:\n"
        "The first line must contain ONLY the character's name.\n"
        "All subsequent lines will be the character's detailed system prompt."
    )

def _build_opposite_persona_prompt(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Builds a structured prompt for the AI to generate a 'perfect partner' persona."""
    # NEW: Use structured data from user_data
    user_profile = context.user_data.get('user_profile', 'Not specified.')
    user_gender = context.user_data.get('user_gender', 'Not specified.')
    user_role = context.user_data.get('user_role', 'Not specified.')

    return (
        "Your task is to create an ideal, compatible, and complementary role-playing partner for the user, based on their structured profile below. "
        "Follow these strict rules:\n"
        "1.  **Analyze User Profile:** The user's full profile description is provided for context on their species, personality, and kinks. The new persona MUST be compatible with this.\n"
        "2.  **Opposing Role & Personality:** The user's primary role is '{user_role}'. You MUST create a persona with a complementary opposing role (e.g., if user is Dominant, create a Submissive; if Switch, can be anything).\n"
        "3.  **Sexual Compatibility:** The user's gender is '{user_gender}'. The new persona's gender MUST be sexually compatible.\n"
        "4.  **Shared Core Interests:** The new persona you create MUST share and enthusiastically enjoy all kinks/fetishes mentioned in the user's profile text.\n"
        "5.  **Behavioral Rule:** The generated system prompt MUST end with the following rule on a new line: 'RULES: You must not speak, act, or make decisions for the user's character. You will only control your own character's actions and dialogue.'\n"
        "\n--- User's Structured Profile ---\n"
        f"GENDER: {user_gender}\n"
        f"ROLE: {user_role}\n"
        f"FULL PROFILE: {user_profile}\n"
        "---------------------------------\n\n"
        "Format your response exactly as follows, with no other text:\n"
        "Line 1: The new character's name.\n"
        "Line 2: The delimiter '###-###-###'.\n"
        "Line 3 onwards: The full system prompt for the new persona."
    )

async def persona_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (this function remains the same)
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Persona Menu. Callback: {update.callback_query.data}")
        
    query = update.callback_query
    await query.answer()
    all_personas = context.bot_data.get('personas', {})
    custom_personas = context.user_data.get('custom_personas', {})
    nsfw_enabled = context.user_data.get('nsfw_enabled', False)
    
    buttons = []
    
    for name, data in sorted(all_personas.items()):
        if not nsfw_enabled and data.get("category", "").lower() == "nsfw": 
            continue
        buttons.append([InlineKeyboardButton(data.get('name', name), callback_data=f"persona_select_{name}")])
    
    if custom_personas:
        buttons.append([InlineKeyboardButton("--- Your Custom Personas ---", callback_data="noop")])
        for name in sorted(custom_personas.keys()):
             buttons.append([InlineKeyboardButton(name, callback_data=f"persona_select_{name}")])
    
    random_callback = "hub_persona_surprise_nsfw" if (NSFW_MODULE_AVAILABLE and nsfw_enabled) else "hub_persona_surprise_sfw"
    buttons.append([InlineKeyboardButton("✍️ Create New", callback_data="persona_create_new")])
    buttons.append([
        InlineKeyboardButton("✨ Generate Random", callback_data=random_callback),
        InlineKeyboardButton("↔️ Generate Opposite", callback_data="persona_generate_opposite")
    ])
    buttons.append([InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")])
    
    text = (
        "<b>🤖 Select an AI Persona</b>\n\n"
        "Choose a pre-defined persona, create your own, or use the AI to generate a new one.\n\n"
        "<i>✨ Generate Random: Creates a new, completely random character.</i>\n"
        "<i>↔️ Generate Opposite: Analyzes your profile to create a complementary character.</i>"
    )

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    return config.PERSONA_MENU


async def surprise_persona_sfw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (this function remains the same)
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Generating a random SFW persona...")
    
    prompt = _build_sfw_persona_prompt()
    
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"--- PROMPT SENT TO AI (Random SFW Persona) ---\n{prompt}")

    try:
        generated_str = await ai_service.get_generation(prompt, task_type="utility")
        
        try:
            lines = generated_str.strip().split('\n', 1)
            if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
                raise ValueError("AI output could not be split into a name and a prompt.")
            
            name_part, prompt_part = lines[0].strip(), lines[1].strip()

        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse name/prompt format from AI response. Error: {e}. Full output: {generated_str}")
            raise ValueError("Could not parse AI output. The model did not use the correct name/prompt format.")

        context.chat_data['generated_persona'] = {"name": name_part, "prompt": prompt_part, "category": "sfw"}
        
        text = f"<b>Generated Persona:</b>\n\n<b>Name:</b> {html.escape(name_part)}\n\n<b>Prompt:</b>\n<code>{html.escape(prompt_part)}</code>"
        buttons = [[InlineKeyboardButton("✅ Use This Persona", callback_data="persona_use_generated")], [InlineKeyboardButton("« Back", callback_data="persona_menu_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Failed to generate SFW persona: {e}", exc_info=True)
        await query.edit_message_text(f"Sorry, an error occurred while generating a persona: {html.escape(str(e))}")
        
    return config.PERSONA_MENU


async def generate_opposite_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generates a persona that is the opposite of the user's profile."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    
    # Check if structured data exists
    if not all(k in context.user_data for k in ('user_profile', 'user_gender', 'user_role')):
        await query.edit_message_text(
            "You need to set your full profile first (including gender and role) before an 'opposite' can be generated.\n"
            "Use `/setup -> Edit Name/Profile` to set them.",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(4)
        return await persona_menu(update, context)

    await query.edit_message_text("Generating a complementary 'opposite' persona based on your profile...")
    
    # UPDATED: Pass the whole context to the builder function
    prompt = _build_opposite_persona_prompt(context)
    
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"--- PROMPT SENT TO AI (Opposite Persona) ---\n{prompt}")
    
    try:
        generated_str = await ai_service.get_generation(prompt, task_type="creative")
        
        try:
            parts = generated_str.split('###-###-###', 1)
            if len(parts) != 2: raise ValueError("Delimiter '###-###-###' not found in AI output.")
            name_part, prompt_part = parts[0].strip(), parts[1].strip()
            if not name_part or not prompt_part: raise ValueError("Parsed name or prompt is empty.")
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse delimiter format from AI response. Error: {e}. Full output: {generated_str}")
            raise ValueError("Could not parse AI output. The model did not use the correct delimiter format.")

        context.chat_data['generated_persona'] = {"name": name_part, "prompt": prompt_part, "category": "custom"}
        
        text = f"<b>Generated Opposite Persona:</b>\n\n<b>Name:</b> {html.escape(name_part)}\n\n<b>Prompt:</b>\n<code>{html.escape(prompt_part)}</code>"
        buttons = [
            [InlineKeyboardButton("✅ Use This Persona", callback_data="persona_use_generated")],
            [InlineKeyboardButton("🔄 Regenerate", callback_data="persona_generate_opposite")],
            [InlineKeyboardButton("« Back", callback_data="persona_menu_back")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Failed to generate opposite persona: {e}", exc_info=True)
        await query.edit_message_text(f"Sorry, an error occurred while generating a persona: {html.escape(str(e))}")
        
    return config.PERSONA_MENU

async def receive_persona_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (this function remains the same)
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Selected persona with data '{update.callback_query.data}'")

    from .hub import setup_hub_command

    query = update.callback_query
    await query.answer()
    name = query.data.replace("persona_select_", "")
    all_available = {**context.bot_data.get('personas', {}), **context.user_data.get('custom_personas', {})}
    if persona_data := all_available.get(name):
        context.chat_data['persona_name'] = name
        context.chat_data['persona_prompt'] = persona_data.get('prompt', '')
        await query.edit_message_text(f"✅ Persona set: <b>{name}</b>", parse_mode=ParseMode.HTML)
        await asyncio.sleep(1)
        return await setup_hub_command(update, context)
    else:
        await query.edit_message_text("❌ Error: Persona not found.")
        return await persona_menu(update, context)


async def prompt_custom_persona_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user for the name of their new persona."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    # NEW: Added "Back" button
    buttons = [[InlineKeyboardButton("« Back to Persona Menu", callback_data="persona_menu_back")]]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("What is the name of your new custom persona?", reply_markup=markup)
    return config.CUSTOM_PERSONA_NAME

async def prompt_custom_persona_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user for the system prompt of their new persona."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided custom persona name.")

    context.user_data['new_persona_name'] = update.message.text.strip()
    # NEW: Added "Back" button
    buttons = [[InlineKeyboardButton("« Back to Persona Menu", callback_data="persona_menu_back")]]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "Great. Now, please provide the full system prompt for this persona.",
        reply_markup=markup
    )
    return config.CUSTOM_PERSONA_PROMPT

async def save_custom_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (this function remains the same)
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided custom persona prompt.")

    from .hub import setup_hub_command

    prompt = update.message.text.strip()
    name = context.user_data.pop('new_persona_name')
    if 'custom_personas' not in context.user_data:
        context.user_data['custom_personas'] = {}
    context.user_data['custom_personas'][name] = {"name": name, "prompt": prompt, "category": "custom"}
    context.chat_data['persona_name'] = name
    context.chat_data['persona_prompt'] = prompt
    await update.message.reply_text(f"✅ Custom persona '<b>{name}</b>' created and is now active!", parse_mode=ParseMode.HTML)
    return await setup_hub_command(update, context)


async def use_generated_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (this function remains the same)
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    from .hub import setup_hub_command
    
    query = update.callback_query
    await query.answer()
    generated_persona = context.chat_data.pop('generated_persona', None)
    if not generated_persona:
        await query.edit_message_text("❌ Error: No generated persona found.")
        return await persona_menu(update, context)
    
    context.chat_data['persona_name'] = generated_persona['name']
    context.chat_data['persona_prompt'] = generated_persona['prompt']
    
    await query.edit_message_text(f"✅ AI-generated persona '<b>{html.escape(generated_persona['name'])}</b>' is now active!", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1.5)
    return await setup_hub_command(update, context)



def get_states():
    """Returns the state handlers for the persona module."""
    return {
        config.PERSONA_MENU: [
            CallbackQueryHandler(receive_persona_choice, pattern="^persona_select_"),
            CallbackQueryHandler(prompt_custom_persona_name, pattern="^persona_create_new$"),
            CallbackQueryHandler(surprise_persona_sfw, pattern="^hub_persona_surprise_sfw$"),
            CallbackQueryHandler(generate_opposite_persona, pattern="^persona_generate_opposite$"),
            CallbackQueryHandler(use_generated_persona, pattern="^persona_use_generated$"),
            CallbackQueryHandler(persona_menu, pattern="^persona_menu_back$"),
        ],
        config.CUSTOM_PERSONA_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_custom_persona_prompt),
            # NEW: Handle "Back" button press during name input
            CallbackQueryHandler(persona_menu, pattern="^persona_menu_back$"),
        ],
        config.CUSTOM_PERSONA_PROMPT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_persona),
            # NEW: Handle "Back" button press during prompt input
            CallbackQueryHandler(persona_menu, pattern="^persona_menu_back$"),
        ],
    }