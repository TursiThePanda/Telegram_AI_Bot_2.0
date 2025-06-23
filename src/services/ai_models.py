# src/services/ai_models.py
"""
Service module for all interactions with the AI model (LM Studio).
Handles API calls, prompt construction, and health checks.
"""
import logging
import httpx
import json
import asyncio
from typing import List, Dict, AsyncGenerator, Optional

from openai import OpenAI, APIConnectionError, APITimeoutError
import src.config as config

logger = logging.getLogger(__name__)

# Initialize the OpenAI client to connect to LM Studio
ai_client: Optional[OpenAI] = None

def init_ai_client():
    """Initializes the AI client once config is confirmed loaded."""
    global ai_client
    if ai_client is not None:
        return

    if not config.LM_STUDIO_API_BASE:
        logger.critical("LM_STUDIO_API_BASE is not configured. AI client cannot be initialized.")
        ai_client = None
        return

    try:
        ai_client = OpenAI(
            base_url=config.LM_STUDIO_API_BASE,
            api_key="lm-studio",
            timeout=config.AI_TIMEOUT,
        )
        logger.info(f"AI client initialized for LM Studio with base URL: {config.LM_STUDIO_API_BASE}")
    except Exception as e:
        logger.critical(f"Failed to initialize AI client: {e}", exc_info=True)
        ai_client = None

async def is_service_online() -> bool:
    """
    Checks if the LM Studio server is online and has at least one model loaded.
    """
    if ai_client is None:
        init_ai_client()
        if ai_client is None:
            return False

    if not config.LM_STUDIO_API_BASE:
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{config.LM_STUDIO_API_BASE}/v1/models", timeout=3.0)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Raw response from /v1/models: {data}")
            
            if data.get('data') and len(data['data']) > 0:
                logger.debug("AI service is online and a model is loaded.")
                return True
            else:
                logger.warning("AI service is reachable but no models are loaded. Status: OFFLINE")
                return False
            
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
        logger.debug(f"AI service health check failed (server unreachable): {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during AI service health check: {e}", exc_info=True)
        return False


async def get_chat_response(messages: list[dict[str, str]], task_type: str = "chat", stream: bool = False) -> AsyncGenerator[str, None]:
    """
    [PERMANENT HTTPX VERSION] Calls the AI model and streams the response.
    Bypasses the openai library for chat completions to ensure compatibility.
    """
    params = config.AI_PARAMS.get(task_type, config.AI_PARAMS["chat"])
    model_name = params.get("model")

    if not model_name or model_name.startswith("lm-studio-"):
        logger.error(f"No model specified for task type '{task_type}' in config. Please configure AI_PARAMS.")
        raise ValueError(f"No model specified for task type '{task_type}' in config.")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": params.get("temperature", 0.7),
        "max_tokens": config.MAX_RESPONSE_TOKENS,
        "stream": stream
    }
    url = f"{config.LM_STUDIO_API_BASE}/v1/chat/completions"
    logger.debug(f"Sending POST request to {url}")

    try:
        async with httpx.AsyncClient(timeout=config.AI_TIMEOUT) as client:
            if stream:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            line_data = line[6:]
                            if line_data.strip() == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(line_data)
                                if chunk_data['choices'] and chunk_data['choices'][0].get('delta', {}).get('content'):
                                    yield chunk_data['choices'][0]['delta']['content']
                            except json.JSONDecodeError:
                                logger.warning(f"Could not decode JSON from stream line: {line_data}")
                                continue
            else:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if data.get('choices') and len(data['choices']) > 0:
                    content = data['choices'][0].get('message', {}).get('content')
                    if content:
                        yield content.strip()
                    else:
                        yield ""
                else:
                    logger.warning(f"AI response received, but it contained no choices. Full data: {data}")
                    yield ""

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}", exc_info=True)
        raise ConnectionError(f"AI service returned an error: {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"Request to AI service failed: {e}", exc_info=True)
        raise ConnectionError("Failed to connect to AI service.") from e
    except Exception as e:
        logger.critical(f"Unexpected AI error during chat completion: {e}", exc_info=True)
        raise e

async def get_generation(prompt: str, task_type: str = "creative") -> str:
    """Gets a single, non-streamed response for generation tasks."""
    messages = [{"role": "user", "content": prompt}]
    full_response = ""
    async for chunk in get_chat_response(messages, task_type, stream=False):
        full_response += chunk
    return full_response

# --- NEW: Function to generate a conversation summary ---
async def get_summary(messages_to_summarize: list[dict]) -> str:
    """
    Calls the AI with a specific prompt to summarize a chunk of conversation.
    """
    # Format the conversation for the summarizer prompt
    formatted_chat = "\n".join(f"{msg['role']}: {msg['content']}" for msg in messages_to_summarize)

    prompt = (
        "You are a memory archival system. Your task is to create a concise, third-person summary of the following role-play conversation. "
        "Focus on key events, character actions, important decisions, and significant emotional shifts. "
        "This summary will be used as a long-term memory for the AI, so it must be dense with information.\n\n"
        "--- Conversation Chunk to Summarize ---\n"
        f"{formatted_chat}\n"
        "--- End of Chunk ---\n\n"
        "Now, provide the summary."
    )
    
    # Use the 'utility' model as it's typically faster and cheaper
    summary = await get_generation(prompt, task_type="utility")
    return summary.strip()