# src/services/ai_models.py
"""
Service module for all interactions with the AI model (LM Studio).
Handles API calls, prompt construction, and health checks.
"""
import logging
import httpx
import asyncio
from typing import List, Dict, AsyncGenerator, Optional

from openai import OpenAI, APIConnectionError, APITimeoutError #, default_headers # default_headers not used, can be removed
import src.config as config

logger = logging.getLogger(__name__)

# Initialize the OpenAI client to connect to LM Studio
# Moved initialization into a function to be called explicitly after config is loaded
ai_client: Optional[OpenAI] = None

def init_ai_client():
    """Initializes the AI client once config is confirmed loaded."""
    global ai_client
    if ai_client is not None: # Already initialized
        return

    if not config.LM_STUDIO_API_BASE:
        logger.critical("LM_STUDIO_API_BASE is not configured. AI client cannot be initialized.")
        ai_client = None # Ensure it's None if base_url is missing
        return

    try:
        # It's common for LM Studio to expect an API key, even if it's a dummy value.
        # Added a default_headers parameter for potential custom headers if needed.
        ai_client = OpenAI(
            base_url=config.LM_STUDIO_API_BASE,
            api_key="lm-studio", # This is often a dummy key for LM Studio
            timeout=config.AI_TIMEOUT,
            # default_headers={"x-api-key": "lm-studio"} # Example if custom headers are needed
        )
        logger.info(f"AI client initialized for LM Studio with base URL: {config.LM_STUDIO_API_BASE}")
    except Exception as e:
        logger.critical(f"Failed to initialize AI client: {e}", exc_info=True)
        ai_client = None

async def is_service_online() -> bool:
    """Checks if the LM Studio server is online and reachable by calling its /v1/models endpoint."""
    # Ensure client is initialized before checking
    if ai_client is None:
        init_ai_client() # Attempt to initialize if not already
        if ai_client is None: # Still None after attempt
            return False

    if not config.LM_STUDIO_API_BASE:
        return False # Should be caught by init_ai_client, but good as a fail-safe

    try:
        # Use a short timeout for health check and call /v1/models endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{config.LM_STUDIO_API_BASE}/v1/models", timeout=3.0)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx, 5xx)
            # Optionally, check if any models are actually loaded:
            # data = response.json()
            # if not data.get('data'):
            #     logger.warning("AI service is online but no models appear to be loaded.")
            return True
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
        logger.debug(f"AI service health check failed: {e}") # Log as debug unless critical
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during AI service health check: {e}", exc_info=True)
        return False


async def get_chat_response(messages: List[Dict[str, str]], task_type: str = "chat", stream: bool = False) -> AsyncGenerator[str, None]:
    """
    Calls the AI model and streams the response using the model specified in the config.

    Args:
        messages (List[Dict[str, str]]): The list of messages for the prompt.
        task_type (str): The type of task ('chat', 'creative', 'utility').
        stream (bool): Whether to stream the response.

    Yields:
        str: Chunks of the AI's response if streaming.
    
    Raises:
        ConnectionError: If the AI service is unavailable or client not initialized.
        APITimeoutError: If the request times out.
        ValueError: If no model is specified in the config for the given task type.
    """
    if ai_client is None: #
        init_ai_client() #
        if ai_client is None: #
            logger.error("AI client is not initialized and cannot be. Cannot get chat response.") #
            raise ConnectionError("AI client is not initialized. Check LM_STUDIO_API_BASE configuration.") #
    
    params = config.AI_PARAMS.get(task_type, config.AI_PARAMS["chat"]) #
    model_name = params.get("model") #

    # --- MODIFICATION START ---
    # Removed the auto-detection logic. Now we strictly require a model from config.
    if not model_name or model_name.startswith("lm-studio-"):
        logger.error(f"No model specified for task type '{task_type}' in config. Please configure AI_PARAMS.")
        raise ValueError(f"No model specified for task type '{task_type}' in config.")
    # --- MODIFICATION END ---
    
    logger.debug(f"Calling AI with model: {model_name}, task_type: {task_type}, stream: {stream}") #
    try:
        # Using asyncio.to_thread as client.chat.completions.create is typically blocking
        response_stream = await asyncio.to_thread( #
            ai_client.chat.completions.create, #
            model=model_name, #
            messages=messages, #
            stream=stream, #
            max_tokens=config.MAX_RESPONSE_TOKENS, #
            temperature=params.get("temperature", 0.7), #
        )

        if stream: #
            for chunk in response_stream: #
                if chunk.choices and chunk.choices[0].delta.content: #
                    yield chunk.choices[0].delta.content #
        else: #
            # If not streaming, yield the whole message at once.
            # Ensure content is always a string.
            content = response_stream.choices[0].message.content #
            if content is not None: #
                yield content.strip() #
            else: #
                yield "" #

    except APITimeoutError as e: #
        logger.warning(f"AI request timed out for task '{task_type}': {e}.") #
        raise e #
    except APIConnectionError as e: #
        logger.error(f"AI connection error for task '{task_type}': {e}. Check LM Studio server status and configuration.") #
        raise ConnectionError("Failed to connect to AI service. It might be offline or misconfigured.") from e #
    except Exception as e: #
        logger.critical(f"Unexpected AI error during '{task_type}' task: {e}", exc_info=True) #
        raise e #

async def get_generation(prompt: str, task_type: str = "creative") -> str:
    """Gets a single, non-streamed response for generation tasks."""
    messages = [{"role": "user", "content": prompt}]
    full_response = ""
    # The get_chat_response function is designed to yield, even for non-streaming.
    # So async for is still appropriate, even if it's just one chunk.
    async for chunk in get_chat_response(messages, task_type, stream=False):
        full_response += chunk
    return full_response