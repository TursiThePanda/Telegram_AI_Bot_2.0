    We've fully refactored the bot into a new, clean, and modular architecture.
    We've fixed all the startup and handler bugs that arose during the process.
    We've implemented a robust, pluggable system for your NSFW features.
    We've added a global error handler for stability.
    We've refined the admin and user command interfaces based on your feedback.

The bot should now be fully functional and stable.

The final step is for you to perform a comprehensive test of all features to ensure everything works exactly as you expect.
Final Test Checklist

Please take your time to go through these actions to verify that everything is working correctly:

    [ ] Onboarding: Delete the persistent_data.pickle file one last time to simulate a new user, then use /start and complete the full setup process.
    [ ] Setup Hub (/setup):
        Test every button: "Persona", "Scene", "View Current Setup", and "Delete Data".
        Test the "Back" buttons in each sub-menu.
    [ ] Persona & Scenery Menus:
        Select a pre-made Persona and a Scene to ensure they apply correctly.
        Use the "Create New" persona feature.
        Test the "Surprise Me!" feature with both NSFW enabled and disabled to see that you get the correct generation flow.
    [ ] Admin Panel (/admin):
        Test each toggle button and confirm the text updates.
        Use the "Manage MOTD" feature to set, view, and disable a message.
        Test the /reload button.
    [ ] Chat & Commands:
        Have a short conversation with the bot to ensure the AI responds.
        Test the /regenerate and /clear commands.
		
		
===============================================================================================================================================================

Comprehensive Setup Guide for Your AI Bot

This guide covers the essential steps to configure and run your newly refactored Telegram bot.

Section 1: Prerequisites

Before you begin, ensure you have the following software installed and ready:

1. Python: Version 3.10 or newer is recommended.
2. LM Studio: You must have LM Studio installed. Before running the bot, start LM Studio, load a model, and start the local server from the "↔️" tab.
3. Telegram Account: You need a Telegram account to get your API token and user ID.

Section 2: Installation and Configuration

Step 1: Install Dependencies

Open your terminal or command prompt in the project's root directory and run the following command. This will install all the necessary Python libraries for the bot to function.

pip install -r requirements.txt

Step 2: Configure LM Studio

Open the LM Studio application on your computer, load the AI model you wish to use, and then navigate to the local server tab (icon looks like "↔️") and click "Start Server".

Step 3: Create and Populate the .env File

This is the most important configuration step. In the root directory of your project, create a file named exactly ".env" and paste the following content into it. You must fill in your own values.

# .env

# --- Core Bot Credentials (Required) ---
# Get this from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN_HERE

# Get this from @userinfobot on Telegram
BOT_OWNER_ID=YOUR_TELEGRAM_ID_HERE
TELEGRAM_BOT_USERNAME=YOUR_BOTS_USERNAME_HERE

# --- AI Model Server Configuration (Required) ---
# This should match the server address shown in LM Studio
LM_STUDIO_API_BASE=http://localhost:1234/v1

# --- AI Model Naming (Optional) ---
# Leave blank to auto-detect from LM Studio.
LM_STUDIO_CHAT_MODEL=
LM_STUDIO_CREATIVE_MODEL=

# --- Feature Toggles ---
# Set to "1" to enable, "0" to disable.
VECTOR_MEMORY_ENABLED=1
DEBUG_LOGGING=0


How to get your credentials:
- TELEGRAM_BOT_TOKEN: Talk to @BotFather on Telegram. Use /newbot or /mybots to get your token.
- BOT_OWNER_ID: Send a message to @userinfobot on Telegram. It will reply instantly with your numeric User ID.

Step 4: Add Initial Content

Your bot needs at least one persona and one scenery file to load correctly on startup.

1. Inside your "personas" directory, create a file named "assistant.json":
    {
      "name": "Helpful Assistant",
      "prompt": "You are a helpful AI assistant. You are knowledgeable, friendly, and concise.",
      "description": "A polite and informative AI.",
      "category": "sfw"
    }

2. Inside your "sceneries" directory, create a file named "default.json":
    {
      "name": "Neutral Room",
      "description": "You are in a plain, neutrally-lit room. There is nothing of note here.",
      "category": "sfw"
    }

Section 3: Running the Bot

Step 5: Run the Bot

You are now ready to launch. Open your terminal in the project's root directory and run the main script:

python main.py

You should see a series of log messages in your console, ending with "Application started". The bot is now running.

Section 4: Using the Bot

1. First-Time Use: Open a chat with your bot on Telegram and send the /start command. It will guide you through the initial character setup.

2. Main Commands:
    - /setup: Access the main menu to change your persona, scene, and other settings.
    - /help: View a list of available user commands.
    - /admin: (Bot Owner Only) Access the admin panel to manage the bot.