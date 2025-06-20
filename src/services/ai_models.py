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
    Calls the AI model and streams the response.

    Args:
        messages (List[Dict[str, str]]): The list of messages for the prompt.
        task_type (str): The type of task ('chat', 'creative', 'utility').
        stream (bool): Whether to stream the response.

    Yields:
        str: Chunks of the AI's response if streaming.
    
    Raises:
        ConnectionError: If the AI service is unavailable or client not initialized.
        APITimeoutError: If the request times out.
        ValueError: If no model can be found or auto-detected.
    """
    if ai_client is None:
        init_ai_client() # Attempt to initialize if not already
        if ai_client is None:
            logger.error("AI client is not initialized and cannot be. Cannot get chat response.")
            raise ConnectionError("AI client is not initialized. Check LM_STUDIO_API_BASE configuration.")
    
    params = config.AI_PARAMS.get(task_type, config.AI_PARAMS["chat"])
    model_name = params.get("model")

    if not model_name or model_name.startswith("lm-studio-"): # Check if it's a default placeholder or None
        # Auto-detect model if not specified in config or is a placeholder default
        try:
            # Using asyncio.to_thread as client.models.list is typically blocking
            loaded_models = await asyncio.to_thread(ai_client.models.list)
            # Ensure there's at least one model
            if loaded_models.data:
                model_name = loaded_models.data[0].id
                logger.info(f"Auto-detected AI model for '{task_type}' task: {model_name}")
            else:
                raise ValueError("No models found on LM Studio server. Cannot auto-detect.")
        except Exception as e:
            logger.error(f"Could not auto-detect a model for task '{task_type}' from LM Studio: {e}", exc_info=True)
            raise ConnectionError(f"Could not find or auto-detect a model for task '{task_type}'. Ensure a model is loaded in LM Studio and config is correct.") from e
    
    logger.debug(f"Calling AI with model: {model_name}, task_type: {task_type}, stream: {stream}")
    try:
        # Using asyncio.to_thread as client.chat.completions.create is typically blocking
        response_stream = await asyncio.to_thread(
            ai_client.chat.completions.create,
            model=model_name,
            messages=messages,
            stream=stream,
            max_tokens=config.MAX_RESPONSE_TOKENS,
            temperature=params.get("temperature", 0.7),
        )

        if stream:
            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            # If not streaming, yield the whole message at once.
            # Ensure content is always a string.
            content = response_stream.choices[0].message.content
            if content is not None:
                yield content.strip()
            else:
                yield "" # Yield empty string if content is None

    except APITimeoutError as e:
        logger.warning(f"AI request timed out for task '{task_type}': {e}.")
        raise e
    except APIConnectionError as e:
        logger.error(f"AI connection error for task '{task_type}': {e}. Check LM Studio server status and configuration.")
        raise ConnectionError("Failed to connect to AI service. It might be offline or misconfigured.") from e
    except Exception as e:
        logger.critical(f"Unexpected AI error during '{task_type}' task: {e}", exc_info=True)
        raise e

async def get_generation(prompt: str, task_type: str = "creative") -> str:
    """Gets a single, non-streamed response for generation tasks."""
    messages = [{"role": "user", "content": prompt}]
    full_response = ""
    # The get_chat_response function is designed to yield, even for non-streaming.
    # So async for is still appropriate, even if it's just one chunk.
    async for chunk in get_chat_response(messages, task_type, stream=False):
        full_response += chunk
    return full_response