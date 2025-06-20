# src/handlers/chat.py
"""
Handles incoming text messages for AI chat responses.
"""
import logging
import time
import html
import asyncio # Import asyncio for Lock
from telegram import Update, Message
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service

logger = logging.getLogger(__name__)

USER_RATE_LIMITS = {}
USER_RATE_LIMIT_LOCK = asyncio.Lock() # Add a lock for thread-safe access to USER_RATE_LIMITS

async def build_chat_context(context: ContextTypes.DEFAULT_TYPE, user_text: str) -> list:
    """Constructs the message list for the AI."""
    # Ensure chat_id is properly set, especially for group chats
    # It's expected that entry.py's start_command (or similar) will set context.chat_data['chat_id']
    chat_id = context.chat_data.get('chat_id', context.user_data.get('user_id'))
    
    persona_prompt = context.chat_data.get('persona_prompt', "You are a helpful AI assistant.")
    user_name = context.user_data.get('user_display_name', 'user')
    user_profile = context.user_data.get('user_profile', 'not specified')
    
    system_prompt = f"{persona_prompt}\nUser's name: {user_name}\nUser's profile: {user_profile}"
    messages = [{"role": "system", "content": system_prompt}]

    if config.VECTOR_MEMORY_ENABLED:
        relevant_memories = await db_service.search_semantic_memory(chat_id, user_text)
        if relevant_memories:
            memory_prompt = "Relevant past events:\n- " + "\n- ".join(relevant_memories)
            messages.append({"role": "system", "content": memory_prompt})

    history = await db_service.get_history_from_db(chat_id)
    messages.extend(history)
    return messages

def sanitize_html(text):
    """Simple but robust HTML sanitizer for AI output."""
    return html.escape(text, quote=False).replace('\n', '<br>')

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The entry point for all user text messages for AI chat."""
    user = update.effective_user
    user_text = update.message.text
    
    # Pre-flight checks with lock for rate limiting
    async with USER_RATE_LIMIT_LOCK:
        if time.time() - USER_RATE_LIMITS.get(user.id, 0) < config.USER_RATE_LIMIT:
            await update.message.reply_text("⏱️ Please wait a moment before sending another message.")
            return
        USER_RATE_LIMITS[user.id] = time.time() # Update last request time within the lock

    if 'user_display_name' not in context.user_data:
        await update.message.reply_text("Please run /start to set up your character profile first.")
        return
        
    placeholder = await update.message.reply_text("✍️...")
    
    try:
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
        
        # 1. Build context
        messages = await build_chat_context(context, user_text)
        messages.append({"role": "user", "content": user_text})
        
        # 2. Stream response from AI service
        full_response = ""
        last_edit_time = time.time()
        
        # Ensure AI service is online before attempting to get response
        if not context.bot_data.get('ai_service_online', True): # ai_service_online is set by health_check_task
            await placeholder.edit_text("❌ The AI service is currently offline. Please try again later.")
            logger.warning(f"AI service reported offline, rejecting chat for user {user.id}.")
            return
            
        response_generator = ai_service.get_chat_response(messages, stream=True)
        
        async for chunk in response_generator:
            full_response += chunk
            if time.time() - last_edit_time > config.STREAM_UPDATE_INTERVAL:
                try:
                    # Append a typing indicator (e.g., a block cursor)
                    display_text = sanitize_html(full_response) + " ▋"
                    # Ensure message doesn't exceed Telegram's length limits before editing
                    if len(display_text) > ParseMode.HTML.MAX_MESSAGE_LENGTH:
                        display_text = display_text[:ParseMode.HTML.MAX_MESSAGE_LENGTH - len("... ▋")] + "... ▋"
                    await placeholder.edit_text(display_text, parse_mode=ParseMode.HTML)
                    last_edit_time = time.time()
                except BadRequest as e:
                    # Log BadRequest errors at debug level to avoid excessive logs for common edit failures
                    logger.debug(f"BadRequest during message edit for user {user.id}: {e}")
                except Exception as e:
                    logger.error(f"Error during message edit for user {user.id}: {e}", exc_info=True)


        # Final edit to remove typing indicator and ensure full response
        final_response_text = sanitize_html(full_response)
        if len(final_response_text) > ParseMode.HTML.MAX_MESSAGE_LENGTH:
            final_response_text = final_response_text[:ParseMode.HTML.MAX_MESSAGE_LENGTH - len("...")] + "..."
        await placeholder.edit_text(final_response_text, parse_mode=ParseMode.HTML)
        
        # 3. Save to database
        await db_service.add_message_to_db(user.id, "user", user_text)
        await db_service.add_message_to_db(user.id, "assistant", full_response)

    except ConnectionError: # Catch specific connection errors from ai_models.py
        await placeholder.edit_text("❌ Failed to connect to the AI service. It might be offline or misconfigured.")
        logger.error(f"AI connection error in chat_handler for user {user.id}.")
    except Exception as e:
        logger.error(f"Error in chat_handler for user {user.id}: {e}", exc_info=True)
        # Provide a generic user-friendly error message
        await placeholder.edit_text("❌ An unexpected error occurred while processing your request. Please try again later.")


def register(application: Application):
    """Registers the main chat handler. Should be added last."""
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))