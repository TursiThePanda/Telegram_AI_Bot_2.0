# src/config.py
"""
Defines application-wide settings, constants, and conversation states.
This module loads its values from environment variables.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Core Credentials & Bot Identity ---
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_OWNER_ID: Optional[int] = None
try:
    BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID"))
except (ValueError, TypeError):
    logger.error("BOT_OWNER_ID is missing or invalid. Admin features will be disabled.")

# --- Directory Paths ---
DATA_DIR = "data"
LOGS_DIR = os.path.join(DATA_DIR, "logs")
USER_LOGS_DIR = os.path.join(LOGS_DIR, "user_logs")
PERSISTENCE_DIR = os.path.join(DATA_DIR, "persistence")
DB_DIR = os.path.join(DATA_DIR, "database")
PERSONAS_PATH = os.getenv("PERSONAS_PATH", "personas")
SCENERIES_PATH = os.getenv("SCENERIES_PATH", "sceneries")

# --- Database & Vector Memory Configuration ---
CONVERSATION_DB_FILE = os.path.join(DB_DIR, "conversation_history.db")
VECTOR_DB_PATH = os.path.join(DB_DIR, "vector_memory")
VECTOR_DB_COLLECTION = "memory_collection"
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
SEMANTIC_SEARCH_K_RESULTS = 3
VECTOR_MEMORY_ENABLED = os.getenv("VECTOR_MEMORY_ENABLED", "1") == "1"

# --- AI Model & API Configuration ---
LM_STUDIO_API_BASE: Optional[str] = os.getenv("LM_STUDIO_API_BASE")
AI_TIMEOUT = 300.0
MAX_RESPONSE_TOKENS = 2048
AI_PARAMS = {
    "chat": {"model": os.getenv("LM_STUDIO_CHAT_MODEL", "lm-studio-chat-default"), "temperature": 0.7},
    "creative": {"model": os.getenv("LM_STUDIO_CREATIVE_MODEL", "lm-studio-creative-default"), "temperature": 1.1},
    "utility": {"model": os.getenv("LM_STUDIO_UTILITY_MODEL", "lm-studio-utility-default"), "temperature": 0.5},
}

# --- Performance & Rate Limiting ---
STREAM_UPDATE_INTERVAL = 1.5
USER_RATE_LIMIT = 1.0
PERFORMANCE_REPORTING_ENABLED = os.getenv("PERFORMANCE_REPORTING_ENABLED", "0") == "1"
# --- User chat logging ---
LOG_USER_CHAT_MESSAGES = os.getenv("LOG_USER_CHAT_MESSAGES", "0") == "1"
LOG_USER_COMMANDS = os.getenv("LOG_USER_COMMANDS", "0") == "1"
LOG_USER_UI_INTERACTIONS = os.getenv("LOG_USER_UI_INTERACTIONS", "0") == "1"


# --- Debugging Configuration ---
DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "0") == "1"

# --- Conversation Handler States ---
(
    # === Main Conversation Flow ===
    START_SETUP_NAME,         # 0
    ASK_PROFILE,              # 1
    ASK_NSFW_ONBOARDING,      # 2
    SETUP_HUB,                # 3

    # === Profile Editing Flow ===
    PROFILE_HUB,              # 4
    EDIT_NAME_PROMPT,         # 5
    EDIT_PROFILE_PROMPT,      # 6

    # === Persona Management Flow ===
    PERSONA_MENU,             # 7
    CUSTOM_PERSONA_NAME,      # 8
    CUSTOM_PERSONA_PROMPT,    # 9
    
    # === Scenery Management Flow ===
    SCENERY_MENU,             # 10
    SCENE_GENRE_SELECT,       # 11

    # === Data Management Flow ===
    DELETE_MENU,              # 12
    DELETE_CUSTOM_PERSONA_SELECT, # 13

    # === Nested NSFW Persona Generation States ===
    NSFW_GEN_START,           # 14
    NSFW_GEN_SPECIES,         # 15
    NSFW_GEN_GENDER,          # 16
    NSFW_GEN_ROLE,            # 17
    NSFW_GEN_FETISHES,        # 18
    NSFW_GEN_CONFIRM,         # 19

) = range(20)