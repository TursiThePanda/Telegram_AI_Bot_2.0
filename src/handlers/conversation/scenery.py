# src/handlers/conversation/scenery.py
"""
Handles all conversation flows related to selecting and generating Sceneries.
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import html
import uuid

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service
from src.utils import logging as logging_utils

logger = logging.getLogger(__name__)

def _build_scene_generation_prompt(genre: str) -> str:
    """Builds the prompt for the AI to generate a scene."""
    clean_genre = genre.replace("NSFW - ", "")
    base = "Describe a unique and evocative environment for a role-play scene. Focus on the physical place, its atmosphere, sights, sounds, and smells. Do NOT include any people, characters, or ongoing events. The description should be a single, detailed paragraph."
    requirement = f"The genre must be: **{clean_genre}**."
    return f"{base}\n\n**Requirement:**\n{requirement}"

async def scenery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main scenery selection menu."""
    if config.LOG_USER_UI_INTERACTIONS and update.callback_query:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Scenery Menu. Callback: {update.callback_query.data}")

    query = update.callback_query
    await query.answer()
    all_sceneries = context.bot_data.get('sceneries', {})
    custom_sceneries = context.user_data.get('custom_sceneries', {})
    nsfw_enabled = context.user_data.get('nsfw_enabled', False)
    full_scenery_data = context.bot_data.get('sceneries_full_data', {})
    buttons = []

    # Clear temporary map before populating to avoid stale data
    context.user_data.pop('temp_custom_scenery_data_map', None) # <<< NEW LINE: Clear map on entry
    context.user_data['temp_custom_scenery_data_map'] = {}
    temp_idx = 0

    for name in sorted(all_sceneries.keys()):
        if not nsfw_enabled and full_scenery_data.get(name, {}).get("category", "").lower() == "nsfw":
            continue
        buttons.append([InlineKeyboardButton(name, callback_data=f"scenery_select_builtin_{name}")])
    
    if custom_sceneries:
        buttons.append([InlineKeyboardButton("--- Your Custom Sceneries ---", callback_data="noop")])
        for name, data in sorted(custom_sceneries.items()):
            context.user_data['temp_custom_scenery_data_map'][str(temp_idx)] = data
            buttons.append([InlineKeyboardButton(name, callback_data=f"scenery_select_custom_{temp_idx}")])
            temp_idx += 1


    buttons.append([
        InlineKeyboardButton("✍️ Define Custom", callback_data="scenery_create_new"),
        InlineKeyboardButton("✨ Generate New Scene", callback_data="scenery_generate_new")
    ])
    buttons.append([InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")])
    await query.edit_message_text(
        "<b>🏞️ Select a Scene</b>\n\n"
        "Choose a pre-defined scene, define your own, or use the AI to generate a new one.",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )
    return config.SCENERY_MENU

async def receive_scenery_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Applies a chosen scenery and provides navigation back to the scenery menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Selected scenery with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    
    callback_data_parts = query.data.split('_', 2)
    
    if len(callback_data_parts) < 3 or callback_data_parts[0] != "scenery" or callback_data_parts[1] != "select":
        logger.error(f"Invalid scenery_select callback data: {query.data}")
        await query.edit_message_text("❌ Error: Invalid scenery selection data.")
        return await scenery_menu(update, context)
        
    source_type_and_value = callback_data_parts[2]

    scenery_name = None
    scenery_description = None

    if source_type_and_value.startswith("builtin_"):
        name = source_type_and_value.replace("builtin_", "")
        scenery_description = context.bot_data.get('sceneries', {}).get(name)
        scenery_name = name
    elif source_type_and_value.startswith("custom_"):
        index = source_type_and_value.replace("custom_", "")
        custom_data = context.user_data.get('temp_custom_scenery_data_map', {}).get(index)
        if custom_data:
            scenery_name = custom_data.get('name')
            scenery_description = custom_data.get('description')
    
    context.user_data.pop('temp_custom_scenery_data_map', None)

    if scenery_name and scenery_description:
        context.chat_data['scenery_name'] = scenery_name
        context.chat_data['scenery'] = scenery_description

        buttons = [
            [InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(f"✅ Scene set: <b>{html.escape(scenery_name)}</b>", parse_mode=ParseMode.HTML, reply_markup=markup)
        return config.SCENERY_MENU
    else:
        await query.edit_message_text(f"❌ Error: Scenery not found or invalid selection.")
        return await scenery_menu(update, context)

async def prompt_scene_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for a genre for the AI-generated scene."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("Fantasy", callback_data="scene_gen_Fantasy"), InlineKeyboardButton("Sci-Fi", callback_data="scene_gen_Sci-Fi")],
        [InlineKeyboardButton("Modern", callback_data="scene_gen_Modern"), InlineKeyboardButton("Horror", callback_data="scene_gen_Horror")],
        [InlineKeyboardButton("Post-Apocalyptic", callback_data="scene_gen_Post-Apocalyptic"), InlineKeyboardButton("Cyberpunk", callback_data="scene_gen_Cyberpunk")],
        [InlineKeyboardButton("Victorian", callback_data="scene_gen_Victorian"), InlineKeyboardButton("Noir / Mystery", callback_data="scene_gen_Noir / Mystery")]
    ]

    if context.user_data.get('nsfw_enabled', False):
        buttons.extend([
            [InlineKeyboardButton("--- NSFW Genres ---", callback_data="noop")],
            [InlineKeyboardButton("BDSM / Dungeon", callback_data="scene_gen_NSFW - BDSM / Dungeon"), InlineKeyboardButton("Intimate / Romantic", callback_data="scene_gen_NSFW - Intimate / Romantic")],
            [InlineKeyboardButton("Decadent / Opulent", callback_data="scene_gen_NSFW - Decadent / Opulent"), InlineKeyboardButton("Public / Risky", callback_data="scene_gen_NSFW - Public / Risky")]
        ])

    buttons.append([InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")])

    await query.edit_message_text("Choose a genre for the generated scene:", reply_markup=InlineKeyboardMarkup(buttons))
    return config.SCENE_GENRE_SELECT

async def generate_new_scene(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generates a new scene based on genre and shows it for confirmation."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Selected scene genre with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    genre = query.data.replace("scene_gen_", "")
    await query.edit_message_text(f"⏳ Generating '{html.escape(genre)}' scene...")
    prompt = _build_scene_generation_prompt(genre)
    try:
        generated_scene = await ai_service.get_generation(prompt, task_type="creative")
        if not generated_scene: raise ValueError("AI returned an empty response.")

        scene_data = {
            "description": generated_scene,
            "category": "nsfw" if genre.startswith("NSFW") else "sfw"
        }
        context.chat_data['generated_scene_data'] = scene_data

        text = f"<b>Generated Scene:</b>\n\n<i>{html.escape(generated_scene)}</i>"
        buttons = [
            [InlineKeyboardButton("✅ Use This Scene", callback_data="scenery_use_generated")],
            [InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to generate scene: {e}", exc_info=True)
        await query.edit_message_text(f"Sorry, failed to generate a scene: {html.escape(str(e))}")
    return config.SCENERY_MENU

async def use_generated_scene(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Applies a scene that was generated by the AI and provides navigation back to the scenery menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer("Using generated scene...") # Shortened message for query.answer

    generated_data = context.chat_data.pop('generated_scene_data', None)
    if not generated_data:
        await query.edit_message_text("❌ Error: No generated scene found.")
        return await scenery_menu(update, context)

    generated_scene_description = generated_data.get('description', 'Error: Scene description not found.')

    scene_name = f"AI Generated ({generated_scene_description[:30].strip()}...)"
    context.chat_data['scenery_name'] = scene_name
    context.chat_data['scenery'] = generated_scene_description
    buttons = [
        [InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(f"✅ AI-generated scene '<b>{html.escape(scene_name)}</b>' has been set!", parse_mode=ParseMode.HTML, reply_markup=markup)
    return config.SCENERY_MENU

# --- New Custom Scenery Functions ---

async def prompt_custom_scenery_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user for the name of their new custom scenery."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]]
    markup = InlineKeyboardMarkup(buttons)
    await query.message.edit_text("What is the name of your new custom scenery? (Max 60 characters)", reply_markup=markup)
    return config.CUSTOM_SCENERY_NAME

async def prompt_custom_scenery_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the scenery name and asks for the detailed description/prompt."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided custom scenery name.")

    name = update.message.text.strip()
    if not name or len(name) > 60:
        await update.message.reply_text(
            "❌ Scenery name must be between 1 and 60 characters. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]])
        )
        return config.CUSTOM_SCENERY_NAME

    context.user_data['new_scenery_name'] = name
    buttons = [[InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "Great. Now, please provide the full description/prompt for this scenery.",
        reply_markup=markup
    )
    return config.CUSTOM_SCENERY_PROMPT

async def save_custom_scenery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the completed custom scenery and sets it as active."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INPUT: Provided custom scenery prompt.")

    from .hub import setup_hub_command

    description = update.message.text.strip()
    name = context.user_data.pop('new_scenery_name')

    if 'custom_sceneries' not in context.user_data:
        context.user_data['custom_sceneries'] = {}
    context.user_data['custom_sceneries'][name] = {"name": name, "description": description, "category": "custom"}
    context.chat_data['scenery_name'] = name
    context.chat_data['scenery'] = description
    await update.message.reply_text(f"✅ Custom scenery '<b>{html.escape(name)}</b>' created and is now active!", parse_mode=ParseMode.HTML)
    return await setup_hub_command(update, context)


def get_states():
    """Returns the state handlers for the scenery module."""
    return {
        config.SCENERY_MENU: [
            CallbackQueryHandler(receive_scenery_choice, pattern="^scenery_select_(builtin_|custom_)"),
            CallbackQueryHandler(prompt_scene_genre, pattern="^scenery_generate_new$"),
            CallbackQueryHandler(use_generated_scene, pattern="^scenery_use_generated$"),
            CallbackQueryHandler(prompt_custom_scenery_name, pattern="^scenery_create_new$"),
            CallbackQueryHandler(scenery_menu, pattern="^scenery_menu_back$"),
        ],
        config.SCENE_GENRE_SELECT: [
            CallbackQueryHandler(generate_new_scene, pattern="^scene_gen_"),
            CallbackQueryHandler(scenery_menu, pattern="^scenery_menu_back$"),
        ],
        config.CUSTOM_SCENERY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_custom_scenery_prompt)],
        config.CUSTOM_SCENERY_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_scenery)],
    }