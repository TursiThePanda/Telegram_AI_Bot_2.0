# src/handlers/chat.py
"""
Handles incoming text messages for AI chat responses.
"""
import logging
import time
import html
import asyncio
from telegram import Update, Message
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

import src.config as config
from src.services import database as db_service
from src.services import ai_models as ai_service
from src.services import monitoring as monitoring_service
from src.utils import logging as logging_utils

logger = logging.getLogger(__name__)

async def build_chat_context(context: ContextTypes.DEFAULT_TYPE, user_text: str) -> list:
    """Constructs the message list for the AI."""
    # This now correctly gets the chat_id from chat_data, which is set by the /start command
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
    """Escapes HTML special characters to prevent formatting errors."""
    return html.escape(text, quote=False)

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The entry point for all user text messages for AI chat."""
    TELEGRAM_MAX_MESSAGE_LENGTH = 4096

    if not update.effective_message or not update.effective_message.text:
        logger.warning("Chat handler received an update with no effective message or text, ignoring.")
        return
    
    message = update.effective_message
    user = update.effective_user
    user_text = message.text

    if config.LOG_USER_CHAT_MESSAGES:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"USER: {user_text}")

    request_id = monitoring_service.performance_monitor.start_request(
        user_id=user.id,
        request_type="chat_message"
    )
    success = False

    try:
        # This is now safe because the /start command ensures user_data is populated
        # before this handler can be effectively used.
        context.chat_data['chat_id'] = update.effective_chat.id

        last_message_time = await db_service.get_user_timestamp(user.id)
        if time.time() - last_message_time < config.USER_RATE_LIMIT:
            await message.reply_text("⏱️ Please wait a moment before sending another message.")
            return

        await db_service.update_user_timestamp(user.id, time.time())

        if 'user_display_name' not in context.user_data:
            await message.reply_text("Please run /start to set up your character profile first.")
            return
            
        placeholder = await message.reply_text("✍️...")
        
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
        
        # --- FIX: Reverted the function call to use the correct 2 arguments ---
        messages = await build_chat_context(context, user_text)
        messages.append({"role": "user", "content": user_text})
        
        full_response = ""
        
        if not context.bot_data.get('ai_service_online', True):
            await placeholder.edit_text("❌ The AI service is currently offline. Please try again later.")
            logger.warning(f"AI service reported offline, rejecting chat for user {user.id}.")
            return

        streaming_enabled = context.bot_data.get('streaming_enabled', False)
        if streaming_enabled:
            sanitized_response = ""
            last_edit_time = time.time()
            response_generator = ai_service.get_chat_response(messages, stream=True)
            async for chunk in response_generator:
                full_response += chunk
                sanitized_response += sanitize_html(chunk)
                if time.time() - last_edit_time > config.STREAM_UPDATE_INTERVAL:
                    try:
                        display_text = sanitized_response + " ▋"
                        if len(display_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
                            display_text = display_text[:TELEGRAM_MAX_MESSAGE_LENGTH - len("... ▋")] + "... ▋"
                        await placeholder.edit_text(display_text, parse_mode=ParseMode.HTML)
                        last_edit_time = time.time()
                    except BadRequest as e:
                        logger.debug(f"BadRequest during message edit for user {user.id}: {e}")
            final_response_text = sanitized_response
        else:
            response_generator = ai_service.get_chat_response(messages, stream=False)
            async for chunk in response_generator:
                full_response += chunk
            final_response_text = sanitize_html(full_response)

        if not final_response_text or not final_response_text.strip():
            logger.warning("Final generated response was empty. Sending an error message to the user.")
            await placeholder.edit_text("😕 The AI model returned an empty response. Please try rephrasing your message or try again later.")
            return
        
        if len(final_response_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            final_response_text = final_response_text[:TELEGRAM_MAX_MESSAGE_LENGTH - len("...")] + "..."
        await placeholder.edit_text(final_response_text, parse_mode=ParseMode.HTML)
        
        await db_service.add_message_to_db(user.id, "user", user_text)
        await db_service.add_message_to_db(user.id, "assistant", full_response)

        if config.LOG_USER_CHAT_MESSAGES:
            user_logger = logging_utils.get_user_logger(user.id, user.username)
            user_logger.info(f"ASSISTANT: {full_response}")

        success = True

    except Exception as e:
        logger.error(f"Error in chat_handler for user {user.id}: {e}", exc_info=True)
        reply_target = placeholder if 'placeholder' in locals() else message
        if isinstance(reply_target, Message):
            try:
                await reply_target.edit_text("❌ An unexpected error occurred while processing your request. Please try again later.")
            except Exception as edit_e:
                logger.error(f"Failed to even edit placeholder with error message: {edit_e}")
    finally:
        monitoring_service.performance_monitor.end_request(
            request_id=request_id, 
            success=success
        )
        
def register(application: Application):
    """Registers the main chat handler. Should be added last."""
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))