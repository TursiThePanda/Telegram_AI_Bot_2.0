# main.py
"""
The main entry point for the Telegram AI Role-Playing Bot.

This script is responsible for loading environment variables and starting
the bot application.
"""
import logging
from dotenv import load_dotenv

# Load environment variables from the .env file at the very beginning.
load_dotenv()

# We now import a synchronous version of 'create_app'.
from src.core.application import create_app

def main():
    """Initializes and runs the bot application."""
    try:
        app = create_app()
        
        logging.info("Bot application created. Starting polling...")
        # run_polling() is a blocking call that starts the asyncio event loop.
        # It will run forever until the process is stopped.
        app.run_polling()

    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot shutdown initiated by user.")
    except Exception as e:
        # Use root logger for critical startup errors as custom logging might not be fully configured yet.
        logging.getLogger().critical(f"Bot failed to start or crashed: {e}", exc_info=True)


if __name__ == '__main__':
    main()