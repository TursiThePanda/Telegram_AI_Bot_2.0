# src/handlers/conversation/scenery.py
"""
Handles all conversation flows related to selecting and generating Sceneries.
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import html

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service
# --- MODIFICATION START: Added import for logging utils ---
from src.utils import logging as logging_utils
# --- MODIFICATION END ---

logger = logging.getLogger(__name__)

def _build_scene_generation_prompt(genre: str) -> str:
    """Builds the prompt for the AI to generate a scene."""
    clean_genre = genre.replace("NSFW - ", "")
    base = "Describe a unique and evocative environment for a role-play scene. Focus on the physical place, its atmosphere, sights, sounds, and smells. Do NOT include any people, characters, or ongoing events. The description should be a single, detailed paragraph."
    requirement = f"The genre must be: **{clean_genre}**."
    return f"{base}\n\n**Requirement:**\n{requirement}"

async def scenery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main scenery selection menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Entered Scenery Menu. Callback: {update.callback_query.data}")
        
    query = update.callback_query
    await query.answer()
    all_sceneries = context.bot_data.get('sceneries', {})
    nsfw_enabled = context.user_data.get('nsfw_enabled', False)
    full_scenery_data = context.bot_data.get('sceneries_full_data', {})
    buttons = []
    for name in sorted(all_sceneries.keys()):
        if not nsfw_enabled and full_scenery_data.get(name, {}).get("category", "").lower() == "nsfw":
            continue
        buttons.append([InlineKeyboardButton(name, callback_data=f"scenery_select_{name}")])
    buttons.append([InlineKeyboardButton("✨ Generate New Scene", callback_data="scenery_generate_new")])
    buttons.append([InlineKeyboardButton("« Back to Setup Hub", callback_data="hub_back")])
    await query.edit_message_text(
        "<b>🏞️ Select a Scene</b>",
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
    name = query.data.replace("scenery_select_", "")
    scenery_desc = context.bot_data.get('sceneries', {}).get(name)
    if scenery_desc:
        context.chat_data['scenery_name'] = name
        context.chat_data['scenery'] = scenery_desc
        buttons = [
            [InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(f"✅ Scene set: <b>{name}</b>", parse_mode=ParseMode.HTML, reply_markup=markup)
        return config.SCENERY_MENU
    else:
        await query.edit_message_text("❌ Error: Scenery not found.")
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
    await query.edit_message_text(f"⏳ Generating '{genre}' scene...")
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
        await query.edit_message_text("Sorry, failed to generate a scene.")
    return config.SCENERY_MENU

async def use_generated_scene(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Applies a scene that was generated by the AI and provides navigation back to the scenery menu."""
    if config.LOG_USER_UI_INTERACTIONS:
        user_logger = logging_utils.get_user_logger(update.effective_user.id, update.effective_user.username)
        user_logger.info(f"UI_INTERACTION: Pressed button with data '{update.callback_query.data}'")

    query = update.callback_query
    await query.answer()

    generated_data = context.chat_data.pop('generated_scene_data', None)
    if not generated_data:
        await query.edit_message_text("❌ Error: No generated scene found.")
        return await scenery_menu(update, context)
    
    generated_scene = generated_data.get('description', 'Error: Scene description not found.')

    scene_name = f"AI Scene ({generated_scene[:15]}...)"
    context.chat_data['scenery_name'] = scene_name
    context.chat_data['scenery'] = generated_scene
    buttons = [
        [InlineKeyboardButton("« Back to Scenery Menu", callback_data="scenery_menu_back")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("✅ AI-generated scene has been set!", parse_mode=ParseMode.HTML, reply_markup=markup)
    return config.SCENERY_MENU

def get_states():
    """Returns the state handlers for the scenery module."""
    return {
        config.SCENERY_MENU: [ 
            CallbackQueryHandler(receive_scenery_choice, pattern="^scenery_select_"), 
            CallbackQueryHandler(prompt_scene_genre, pattern="^scenery_generate_new$"), 
            CallbackQueryHandler(use_generated_scene, pattern="^scenery_use_generated$"), 
            CallbackQueryHandler(scenery_menu, pattern="^scenery_menu_back$"), 
        ],
        config.SCENE_GENRE_SELECT: [ 
            CallbackQueryHandler(generate_new_scene, pattern="^scene_gen_"), 
            CallbackQueryHandler(scenery_menu, pattern="^scenery_menu_back$"),
        ],
    }