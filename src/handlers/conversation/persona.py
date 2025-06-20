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

logger = logging.getLogger(__name__)
NSFW_MODULE_AVAILABLE = module_loader.is_module_available("src.handlers.nsfw")

def _build_sfw_persona_prompt() -> str:
    """Builds the prompt for the AI to generate a persona in JSON format."""
    return (
        "Generate a simple, safe-for-work fantasy character persona. "
        "Your response MUST be a single, valid JSON object. Do not include any text before or after the JSON object. "
        "The JSON object must have exactly two keys: "
        '1. "name": A string for the character\'s name. '
        '2. "prompt": A string for the character\'s detailed system prompt.'
    )

# --- Menu and Action Functions ---
async def persona_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main persona selection menu."""
    query = update.callback_query
    await query.answer()
    all_personas = context.bot_data.get('personas', {})
    custom_personas = context.user_data.get('custom_personas', {})
    nsfw_enabled = context.user_data.get('nsfw_enabled', False)
    
    buttons = []
    
    # Add SFW default personas
    for name, data in sorted(all_personas.items()):
        if not nsfw_enabled and data.get("category", "").lower() == "nsfw": 
            continue
        buttons.append([InlineKeyboardButton(data.get('name', name), callback_data=f"persona_select_{name}")])
    
    # Add custom personas
    if custom_personas:
        buttons.append([InlineKeyboardButton("--- Your Custom Personas ---", callback_data="noop")])
        for name in sorted(custom_personas.keys()):
             buttons.append([InlineKeyboardButton(name, callback_data=f"persona_select_{name}")])
    
    # Correctly determines callback for Surprise Me button based on NSFW status
    surprise_callback = "hub_persona_surprise_nsfw" if (NSFW_MODULE_AVAILABLE and nsfw_enabled) else "hub_persona_surprise_sfw"
    
    buttons.append([
        InlineKeyboardButton("✍️ Create New", callback_data="persona_create_new"),
        InlineKeyboardButton("✨ Surprise Me!", callback_data=surprise_callback)
    ])
    buttons.append([InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")])
    
    await query.edit_message_text("<b>🤖 Select an AI Persona</b>", reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    return config.PERSONA_MENU

async def surprise_persona_sfw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generates a new SFW persona by parsing a JSON response from the AI."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Generating a SFW persona...")
    
    prompt = _build_sfw_persona_prompt()
    
    try:
        generated_str = await ai_service.get_generation(prompt, task_type="utility")
        
        try:
            cleaned_str = re.sub(r'```json\s*|\s*```', '', generated_str, flags=re.DOTALL).strip()
            # --- FIX: Added strict=False to allow for newlines in the prompt string ---
            persona_data = json.loads(cleaned_str, strict=False)
            name_part = persona_data.get("name", "Unnamed Persona")
            prompt_part = persona_data.get("prompt", "No prompt provided by AI.")
            
            if not isinstance(name_part, str) or not isinstance(prompt_part, str):
                raise ValueError("JSON keys 'name' and 'prompt' must be strings.")

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON from AI response. Error: {e}. Full output: {generated_str}")
            raise ValueError(f"Could not parse AI output. The model did not return valid JSON. Response: {generated_str[:200]}...")

        context.chat_data['generated_persona'] = {"name": name_part, "prompt": prompt_part, "category": "sfw"}
        
        text = f"<b>Generated Persona:</b>\n\n<b>Name:</b> {html.escape(name_part)}\n\n<b>Prompt:</b>\n<code>{html.escape(prompt_part)}</code>"
        buttons = [[InlineKeyboardButton("✅ Use This Persona", callback_data="persona_use_generated")], [InlineKeyboardButton("« Back", callback_data="persona_menu_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Failed to generate SFW persona: {e}", exc_info=True)
        await query.edit_message_text(f"Sorry, an error occurred while generating a persona: {html.escape(str(e))}")
        
    return config.PERSONA_MENU

async def receive_persona_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the chosen persona and returns to the setup hub."""
    # --- FIX: Local import to prevent circular dependency ---
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
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("What is the name of your new custom persona?")
    return config.CUSTOM_PERSONA_NAME

async def prompt_custom_persona_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user for the system prompt of their new persona."""
    context.user_data['new_persona_name'] = update.message.text.strip()
    await update.message.reply_text("Great. Now, please provide the full system prompt for this persona.")
    return config.CUSTOM_PERSONA_PROMPT

async def save_custom_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the completed custom persona and returns to the setup hub."""
    # --- FIX: Local import to prevent circular dependency ---
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
    """Applies the generated persona and returns to the setup hub."""
    # --- FIX: Local import to prevent circular dependency ---
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
            CallbackQueryHandler(use_generated_persona, pattern="^persona_use_generated$"),
            CallbackQueryHandler(persona_menu, pattern="^persona_menu_back$"),
        ],
        config.CUSTOM_PERSONA_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_custom_persona_prompt)],
        config.CUSTOM_PERSONA_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_persona)],
    }