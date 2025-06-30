# src/handlers/nsfw.py
"""
This module is a self-contained "plug-in" for all NSFW functionality.
If this file is removed, the bot will fall back to SFW-only mode.
"""
import logging
import time
import html
import asyncio
import re
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
)
from telegram.constants import ParseMode

import src.config as config
from src.services import ai_models as ai_service
from src.handlers.conversation.persona import use_generated_persona # Moved import to top-level

logger = logging.getLogger(__name__)

# --- Constants for the Menu ---
FETISH_OPTIONS = [
    'bondage', 'exhibitionism', 'foot fetish', 'hypnosis', 'latex', 'leather',
    'lingerie', 'musk', 'oral fixation', 'pet play', 'praise', 'public risk',
    'roughness', 'size difference', 'uniforms', 'voyeurism', 'watersports'
]
MAX_FETISHES = 5

NSFW_PERSONA_RATELIMIT_SECONDS = 30
NSFW_PERSONA_LAST_TIME = {}
NSFW_RATELIMIT_LOCK = asyncio.Lock()

# --- Helper Functions ---
def _build_nsfw_prompt(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Builds the prompt for the AI to generate an NSFW persona."""
    species = context.chat_data.get('nsfw_gen_species', 'any')
    gender = context.chat_data.get('nsfw_gen_gender', 'any')
    role = context.chat_data.get('nsfw_gen_role', 'any')
    fetishes = context.chat_data.get('nsfw_gen_fetishes', [])

    prompt_parts = [
        "You are an expert character writer specializing in adult themes. Generate a complete AI persona prompt for a role-playing bot.",
        f"The persona MUST be NSFW. The character's species should be '{species}' and their gender '{gender}'.",
        f"Their primary sexual role is '{role}'.",
    ]
    if fetishes:
        prompt_parts.append(f"You must explicitly incorporate these themes/fetishes into their personality and background: {', '.join(fetishes)}.")

    prompt_parts.extend([
        "The persona prompt must be very detailed, describing their personality, background, appearance, and how they should interact with the user in an erotic or dominant/submissive manner.",
        "Your response MUST be formatted as follows:",
        "The first line must contain ONLY the character's name.",
        # Removed the explicit instruction for '###-###-###' delimiter here, as parsing now relies on simple newline split.
        "All subsequent lines will be the character's detailed system prompt.",
        "The generated system prompt MUST end with the following rule on a new line: 'RULES: You must not speak, act, or make decisions for the user's character. You will only control your own character's actions and dialogue.'"
    ])
    return "\n".join(prompt_parts)

def _build_fetish_markup(selected_fetishes: list) -> InlineKeyboardMarkup:
    """Creates the keyboard for the multi-select fetish menu."""
    buttons = []
    for fetish in FETISH_OPTIONS:
        text = f"✅ {fetish.capitalize()}" if fetish in selected_fetishes else fetish.capitalize()
        buttons.append([InlineKeyboardButton(text, callback_data=f"nsfw_fetish_{fetish}")])

    buttons.append([InlineKeyboardButton("➡️ Done Selecting ⬅️", callback_data="nsfw_fetish_done")])
    return InlineKeyboardMarkup(buttons)

# --- Onboarding and Toggle Handlers ---
async def nsfw_onboarding_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's response to the NSFW onboarding question."""
    query = update.callback_query
    await query.answer()
    context.user_data['nsfw_enabled'] = (query.data == 'onboard_nsfw_yes')
    await query.edit_message_text("✅ Setup complete! You can now start chatting. Use /setup to change settings later.")
    return ConversationHandler.END

async def toggle_nsfw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.handlers.conversation.hub import setup_hub_command
    query = update.callback_query
    await query.answer()
    context.user_data["nsfw_enabled"] = not context.user_data.get("nsfw_enabled", False)
    return await setup_hub_command(update, context)

# --- NSFW Persona Generation Conversation ---
async def start_nsfw_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the NSFW persona generation flow."""
    query = update.callback_query
    user_id = update.effective_user.id

    async with NSFW_RATELIMIT_LOCK:
        now = time.time()
        last = NSFW_PERSONA_LAST_TIME.get(user_id, 0)
        if now - last < NSFW_PERSONA_RATELIMIT_SECONDS:
            await query.answer(f"⚠️ Please wait {int(NSFW_PERSONA_RATELIMIT_SECONDS - (now - last))}s before generating another NSFW persona.", show_alert=True)
            return ConversationHandler.END

        NSFW_PERSONA_LAST_TIME[user_id] = now

    await query.answer()

    buttons = [[InlineKeyboardButton("Human", callback_data="nsfw_species_human"), InlineKeyboardButton("Furry/Anthro", callback_data="nsfw_species_furry")]]

    try:
        logger.debug(f"start_nsfw_generation: Attempting to edit message with species options. Query message: {query.message}")
        await query.message.edit_text(
            "Let's create an NSFW persona. First, choose a species:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error sending species selection in start_nsfw_generation: {e}", exc_info=True)
        # Fallback to sending a new message if editing fails (e.g., message too old, network issue)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, I couldn't update the message. Please choose a species for your NSFW persona:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    return config.NSFW_GEN_SPECIES

async def ask_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.chat_data['nsfw_gen_species'] = query.data.replace("nsfw_species_", "")
    buttons = [[InlineKeyboardButton("Male", callback_data="nsfw_gender_male"), InlineKeyboardButton("Female", callback_data="nsfw_gender_female")], [InlineKeyboardButton("Non-binary", callback_data="nsfw_gender_non-binary")]]
    await query.edit_message_text("Choose a gender:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.NSFW_GEN_GENDER

async def ask_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.chat_data['nsfw_gen_gender'] = query.data.replace("nsfw_gender_", "")
    buttons = [[InlineKeyboardButton("Dominant", callback_data="nsfw_role_dominant")], [InlineKeyboardButton("Submissive", callback_data="nsfw_role_submissive")], [InlineKeyboardButton("Switch", callback_data="nsfw_role_switch")]]
    await query.edit_message_text("Choose a sexual role:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.NSFW_GEN_ROLE

async def ask_fetishes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.chat_data['nsfw_gen_role'] = query.data.replace("nsfw_role_", "")
    context.chat_data['nsfw_gen_fetishes'] = []
    markup = _build_fetish_markup(selected_fetishes=[])
    await query.edit_message_text(f"Select up to {MAX_FETISHES} fetishes, then press 'Done'.", reply_markup=markup)
    return config.NSFW_GEN_FETISHES

async def handle_fetish_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    choice = query.data.replace("nsfw_fetish_", "")
    if choice == "done":
        return await generate_and_confirm(update, context)
    selected = context.chat_data.get('nsfw_gen_fetishes', [])
    if choice in selected:
        selected.remove(choice)
    else:
        if len(selected) >= MAX_FETISHES:
            await query.answer(f"You can select a maximum of {MAX_FETISHES}.", show_alert=True)
            return config.NSFW_GEN_FETISHES
        selected.append(choice)
    context.chat_data['nsfw_gen_fetishes'] = selected
    await query.edit_message_reply_markup(reply_markup=_build_fetish_markup(selected))
    return config.NSFW_GEN_FETISHES

async def generate_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generates and confirms an NSFW persona using newline parsing."""
    logger.debug("Entering generate_and_confirm function.")

    query = update.callback_query
    if query:
        await query.answer()

    message_to_edit = query.message
    await message_to_edit.edit_text("⏳ Generating NSFW persona...")

    prompt = _build_nsfw_prompt(context)
    try:
        generated_str = await ai_service.get_generation(prompt, task_type="creative")

        try:
            lines = generated_str.strip().split('\n', 1)
            if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
                raise ValueError("AI output could not be split into a name and a prompt.")

            name = lines[0].strip()
            prompt_text = lines[1].strip()

        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse name/prompt format from AI response. Error: {e}. Full output: {generated_str}")
            raise ValueError(f"Could not parse AI output. The model did not use the correct name/prompt format. Error: {html.escape(str(e))}")

        context.chat_data['generated_persona'] = {"name": name, "prompt": prompt_text, "category": "nsfw"}

        text = f"<b>Generated NSFW Persona:</b>\n\n<b>Name:</b> {html.escape(name)}\n\n<b>Prompt:</b>\n<code>{html.escape(prompt_text)}</code>"
        buttons = [
            [InlineKeyboardButton("✅ Use This Persona", callback_data="persona_use_generated")],
            [InlineKeyboardButton("🔄 Regenerate", callback_data="hub_persona_surprise_nsfw")],
            [InlineKeyboardButton("« Cancel", callback_data="persona_menu_back")]
        ]
        await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        return config.NSFW_GEN_CONFIRM
    except Exception as e:
        logger.error(f"Failed to generate NSFW persona: {e}", exc_info=True)
        await message_to_edit.edit_text(f"Sorry, the AI failed to generate a persona. Error: {html.escape(str(e))}")
        return ConversationHandler.END

# --- Exported Functions for the Assembler ---
def get_states():
    """Returns the state handlers for the NSFW module."""
    nsfw_persona_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_nsfw_generation, pattern="^hub_persona_surprise_nsfw$")],
        states={
            config.NSFW_GEN_SPECIES: [CallbackQueryHandler(ask_gender, pattern="^nsfw_species_")],
            config.NSFW_GEN_GENDER: [CallbackQueryHandler(ask_role, pattern="^nsfw_gender_")],
            config.NSFW_GEN_ROLE: [CallbackQueryHandler(ask_fetishes, pattern="^nsfw_role_")],
            config.NSFW_GEN_FETISHES: [CallbackQueryHandler(handle_fetish_selection, pattern="^nsfw_fetish_")],
            config.NSFW_GEN_CONFIRM: [
                CallbackQueryHandler(generate_and_confirm, pattern="^hub_persona_surprise_nsfw$"),
                CallbackQueryHandler(use_generated_persona, pattern="^persona_use_generated$"),
                CallbackQueryHandler(lambda u,c: config.PERSONA_MENU, pattern="^persona_menu_back$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(start_nsfw_generation, pattern="^hub_persona_surprise_nsfw$"),
            CallbackQueryHandler(lambda u,c: config.PERSONA_MENU, pattern="^persona_menu_back$"),
            CommandHandler('cancel', lambda u,c: config.PERSONA_MENU)
        ],
        map_to_parent={
            ConversationHandler.END: config.PERSONA_MENU,
            config.NSFW_GEN_CONFIRM: config.PERSONA_MENU,
        },
        per_user=True,
        per_chat=True,
        persistent=True,
        name="nsfw_persona_conversation_handler",
        allow_reentry=True
    )

    return {
        config.PERSONA_MENU: [
            nsfw_persona_conv,
        ]
    }