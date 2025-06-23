# src/handlers/chat.py
"""
Handles incoming text messages for AI chat responses.
"""
import logging
import time
import html
import asyncio
import re
import tiktoken

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

def count_message_tokens(messages: list[dict], model: str = "gpt-3.5-turbo") -> int:
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except KeyError:
        encoding = tiktoken.get_encoding("p50k_base")

    num_tokens = 0
    for message in messages:
        num_tokens += 4
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens -= 1
    num_tokens += 2
    return num_tokens

async def build_chat_context(context: ContextTypes.DEFAULT_TYPE, user_text: str) -> list:
    """
    Constructs the message list for the AI, ensuring it fits within the token limit.
    """
    chat_id = context.chat_data.get('chat_id', context.user_data.get('user_id'))
    
    persona_prompt = context.chat_data.get('persona_prompt', "You are a helpful AI assistant.")
    user_name = context.user_data.get('user_display_name', 'user')
    user_profile = context.user_data.get('user_profile', 'not specified')
    
    base_system_rules = (
        "You are an engaging and descriptive role-playing companion and a master storyteller. "
        "When it is your turn, you will describe the scene, the actions of non-player characters, and any dialogue they speak. "
        "You MUST complete your narrative beat for your turn before ending. "
        "Do not describe the user's character's response or assume their actions, thoughts, or feelings. "
        f"You must always explicitly ask the user 'What does {user_name} do?' or 'How does {user_name} respond?' at the end of your turn, or a similar direct question prompting their next action. "
        "Wait for the user's input before continuing the narrative.\n\n"
        
        "--- CRITICAL BEHAVIORAL RULES ---\n"
        "1.  **Advance the Plot:** Your primary goal is to advance the story. In every response, you MUST introduce a new action, a new event, or a significant change in the scene. Do not get stuck in repetitive loops describing the same state. If the user's input is passive, you must take the initiative to move the plot forward.\n"
        "2.  **Use Original Language:** Always describe events and dialogue using your own creative language. DO NOT repeat the user's phrases or sentences back to them. Reinterpret their requests and describe the outcome with original descriptions."
    )
    system_prompt = (
        f"{persona_prompt}\n\n"
        f"{base_system_rules}\n\n"
        f"Context for the AI:\n"
        f"The user's character name is: {user_name}\n"
        f"The user's character profile: {user_profile}"
    )
    
    messages = [{"role": "system", "content": system_prompt}]

    if config.VECTOR_MEMORY_ENABLED:
        relevant_memories = await db_service.search_semantic_memory(chat_id, user_text)
        if relevant_memories:
            memory_prompt = "Relevant past events:\n- " + "\n- ".join(relevant_memories)
            messages.append({"role": "system", "content": memory_prompt})

    current_tokens = count_message_tokens(messages)
    # The get_history function now returns IDs, but we don't need them here.
    # We only need the content for the short-term context window.
    history_with_ids = await db_service.get_history_from_db(chat_id, limit=50)
    history_for_context = [{"role": msg["role"], "content": msg["content"]} for msg in history_with_ids]
    
    final_history = []
    for message in reversed(history_for_context):
        message_tokens = count_message_tokens([message])
        if current_tokens + message_tokens < config.MAX_PROMPT_TOKENS:
            final_history.insert(0, message)
            current_tokens += message_tokens
        else:
            logger.debug(f"Token limit reached. Truncating conversation history for chat {chat_id}.")
            break
            
    messages.extend(final_history)
    
    logger.debug(f"Final prompt for chat {chat_id} has {len(messages)} messages and {current_tokens} tokens.")
    return messages

def sanitize_html(text):
    """Escapes HTML special characters to prevent formatting errors."""
    return html.escape(text, quote=False)

# --- MODIFIED: This task now handles memory pruning ---
async def _run_summarization_task(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    A background task that generates a summary and prunes the original messages.
    """
    logger.info(f"Starting summarization task for chat {chat_id}...")
    
    if context.chat_data.get('is_summarizing', False):
        logger.warning(f"Summarization task for chat {chat_id} already in progress. Skipping.")
        return

    try:
        context.chat_data['is_summarizing'] = True
        
        # Fetch the last N messages with their IDs to be summarized
        messages_to_summarize_with_ids = await db_service.get_history_from_db(chat_id, limit=config.SUMMARY_THRESHOLD)

        if len(messages_to_summarize_with_ids) < config.SUMMARY_THRESHOLD:
            logger.info(f"Not enough history to summarize for chat {chat_id}. Need {config.SUMMARY_THRESHOLD}, have {len(messages_to_summarize_with_ids)}.")
            return
            
        # Create a clean list of messages for the AI (without IDs)
        messages_for_ai = [{"role": msg["role"], "content": msg["content"]} for msg in messages_to_summarize_with_ids]
        summary = await ai_service.get_summary(messages_for_ai)
        
        if summary:
            # Add the new summary to the database
            await db_service.add_summary_to_db(chat_id, summary)

            # Now that the summary is stored, prune the original messages
            ids_to_prune = [msg['id'] for msg in messages_to_summarize_with_ids]
            await db_service.delete_messages_by_ids(ids_to_prune)
            
            # Reset the counter after a successful summary and pruning
            context.chat_data['messages_since_last_summary'] = 0
        else:
            logger.warning(f"AI returned an empty summary for chat {chat_id}.")

    except Exception as e:
        logger.error(f"Error during background summarization for chat {chat_id}: {e}", exc_info=True)
    finally:
        # Always release the lock
        context.chat_data['is_summarizing'] = False

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The entry point for all user text messages for AI chat."""
    TELEGRAM_MAX_MESSAGE_LENGTH = 4096

    if not update.effective_message or not update.effective_message.text:
        logger.warning("Chat handler received an update with no effective message or text, ignoring.")
        return
    
    message = update.effective_message
    user = update.effective_user
    user_text = message.text
    user_name = context.user_data.get('user_display_name', 'user')

    if config.LOG_USER_CHAT_MESSAGES:
        user_logger = logging_utils.get_user_logger(user.id, user.username)
        user_logger.info(f"USER: {user_text}")

    request_id = monitoring_service.performance_monitor.start_request(user_id=user.id, request_type="chat_message")
    success = False

    try:
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
        
        messages = await build_chat_context(context, user_text)
        messages.append({"role": "user", "content": user_text})
        
        full_response_raw = ""
        
        if not context.bot_data.get('ai_service_online', True):
            await placeholder.edit_text("❌ The AI service is currently offline. Please try again later.")
            logger.warning(f"AI service reported offline, rejecting chat for user {user.id}.")
            return

        streaming_enabled = context.bot_data.get('streaming_enabled', False)
        if streaming_enabled:
            sanitized_response_buffer = ""
            last_edit_time = time.time()
            response_generator = ai_service.get_chat_response(messages, stream=True)
            async for chunk in response_generator:
                full_response_raw += chunk
                sanitized_response_buffer += sanitize_html(chunk)
                
                if time.time() - last_edit_time > config.STREAM_UPDATE_INTERVAL:
                    display_text = sanitized_response_buffer + " ▋"
                    if len(display_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
                        display_text = display_text[:TELEGRAM_MAX_MESSAGE_LENGTH - len("... ▋")] + "... ▋"
                    try:
                        await placeholder.edit_text(display_text, parse_mode=ParseMode.HTML)
                        last_edit_time = time.time()
                    except BadRequest as e:
                        logger.debug(f"BadRequest during message edit for user {user.id}: {e}")
        else:
            response_generator = ai_service.get_chat_response(messages, stream=False)
            async for chunk in response_generator:
                full_response_raw += chunk

        if not full_response_raw or not full_response_raw.strip():
            logger.warning("Final generated response was empty. Sending an error message to the user.")
            await placeholder.edit_text("😕 The AI model returned an empty response. Please try rephrasing your message or try again later.")
            return

        processed_response = full_response_raw
        
        expected_prompt_end = f"What does {user_name} do?"
        alt_prompt_end = f"How does {user_name} respond?"

        assumed_action_patterns = [
            re.compile(r"As \w+ complied", re.IGNORECASE), re.compile(r"Tursi complied", re.IGNORECASE),
            re.compile(r"Tursi obeyed", re.IGNORECASE), re.compile(r"He complied", re.IGNORECASE),
            re.compile(r"She obeyed", re.IGNORECASE),
            re.compile(r"(\bhe|\bshe|\bthey|\bTursi) (began to|started to|proceeded to|moved to|reached out to)", re.IGNORECASE),
        ]
        
        explicit_question_found = False
        if expected_prompt_end in processed_response:
            processed_response = processed_response.split(expected_prompt_end, 1)[0] + expected_prompt_end
            explicit_question_found = True
        elif alt_prompt_end in processed_response:
            processed_response = processed_response.split(alt_prompt_end, 1)[0] + alt_prompt_end
            explicit_question_found = True
        
        if not explicit_question_found:
            cutoff_index = len(processed_response)
            for pattern in assumed_action_patterns:
                match = pattern.search(processed_response)
                if match and match.start() < cutoff_index:
                    cutoff_index = match.start()
            processed_response = processed_response[:cutoff_index].strip()
            if not processed_response.strip().endswith(('?', '!', '.')):
                 processed_response += f" What does {user_name} do?"

        final_response_text = sanitize_html(processed_response)
        
        if len(final_response_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            final_response_text = final_response_text[:TELEGRAM_MAX_MESSAGE_LENGTH - len("...")] + "..."
        
        final_message = await placeholder.edit_text(final_response_text, parse_mode=ParseMode.HTML)
        context.chat_data['last_bot_message_id'] = final_message.message_id
        
        await db_service.add_message_to_db(user.id, "user", user_text)
        await db_service.add_message_to_db(user.id, "assistant", processed_response)

        count = context.chat_data.get('messages_since_last_summary', 0) + 2
        context.chat_data['messages_since_last_summary'] = count
        
        if count >= config.SUMMARY_THRESHOLD:
            logger.info(f"Message threshold reached for chat {user.id}. Scheduling summarization.")
            asyncio.create_task(_run_summarization_task(context, user.id))

        if config.LOG_USER_CHAT_MESSAGES:
            user_logger = logging_utils.get_user_logger(user.id, user.username)
            user_logger.info(f"ASSISTANT: {processed_response}")

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
        monitoring_service.performance_monitor.end_request(request_id=request_id, success=success)
        
def register(application: Application):
    """Registers the main chat handler. Should be added last."""
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))