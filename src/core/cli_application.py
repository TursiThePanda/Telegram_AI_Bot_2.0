# cli_application.py
"""
CLI-adapted application initializer that mirrors the Telegram bot's create_app,
including SQLite and ChromaDB initialization.
"""
import logging
from src.utils import files as file_utils
from src.config import PERSONAS_PATH, SCENERIES_PATH, AI_PARAMS
from src import services  # zahrnuje ai_models, database, monitoring, atd.
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

async def create_console_app():
    """
    Initializes the CLI app environment: loads personas, sceneries,
    database, vector memory, and services.
    Returns a dictionary representing the bot context.
    """
    logger.info("Inicializace CLI aplikace...")
    
    # ⬇️ Kontrola načteného modelu
    model_name = AI_PARAMS.get("chat", {}).get("model")
    if model_name:
        logger.info(f"✅ Model z .env: {model_name}")
    else:
        logger.warning("⚠️ LM_STUDIO_CHAT_MODEL není nastaven v .env – nebude fungovat AI.")

    # Inicializace SQLite a ChromaDB databází
    services.database.init_db()
    logger.info("✅ Databáze inicializovány (SQLite + ChromaDB)")
    
    
    # Načtení JSON souborů s personami a scénami
    personas = file_utils.load_from_directory(PERSONAS_PATH, key_name="name")
    personas_described = {name: f"{name} – {data.get('description', '')}" for name, data in personas.items()}
    sceneries_full_data = file_utils.load_from_directory(SCENERIES_PATH, key_name="name")
    sceneries = { name: data.get("description", "") for name, data in sceneries_full_data.items() }

    logger.info(f"Načteno {len(personas)} person a {len(sceneries)} scénářů.")

    return {
        "personas": personas,
        "personas_described" : personas_described,
        "sceneries_full_data": sceneries_full_data,
        "sceneries": sceneries,
        "memory": [],
        "services": services,  # obsahuje ai_models, database, chromadb...
    }
