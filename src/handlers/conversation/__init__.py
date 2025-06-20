# src/handlers/conversation/__init__.py
"""
Assembles the main ConversationHandler from modular parts.
"""
import logging
from telegram.ext import Application, ConversationHandler

from . import entry, hub, profile, persona, scenery, data_management
from src.utils import module_loader
import src.config as config

logger = logging.getLogger(__name__)

def register(application: Application):
    """Builds and registers the main conversation handler."""

    # 1. Collect all states from submodules
    all_states = {
        **entry.get_states(),
        **hub.get_states(),
        **profile.get_states(),
        **persona.get_states(),
        **scenery.get_states(),
        **data_management.get_states(),
    }

    # 2. Dynamically plug in NSFW states if the module exists
    if module_loader.is_module_available("src.handlers.nsfw"):
        # Corrected import: Changed from relative '. import nsfw' to absolute 'src.handlers import nsfw'
        from src.handlers import nsfw 
        nsfw_states = nsfw.get_states()
        for state, handlers in nsfw_states.items():
            if state in all_states:
                all_states[state].extend(handlers)
            else:
                all_states[state] = handlers
        logger.info("Successfully plugged in NSFW module handlers.")

    conv_handler = ConversationHandler(
        entry_points=entry.get_entry_points(),
        states=all_states,
        fallbacks=entry.get_fallbacks(),
        per_user=True,
        per_chat=True,
        allow_reentry=True,
        persistent=True,
        name="main_setup_conversation"
    )

    application.add_handler(conv_handler)