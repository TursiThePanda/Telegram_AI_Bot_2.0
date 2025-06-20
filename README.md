# Telegram AI Role-Playing Bot 2.0

Welcome to the home of a sophisticated, feature-rich AI companion designed for immersive and persistent role-playing experiences on Telegram. This bot connects to a local Large Language Model (LLM) running on LM Studio, ensuring privacy and high-performance, customizable interactions.

## Key Features

This bot is built with a robust, modular architecture and includes a wide array of advanced features:

* **Local LLM Connection**: Connects directly to your own self-hosted language model via an OpenAI-compatible API (e.g., LM Studio), keeping your conversations private and giving you full control over the AI's personality.
* **Advanced Dual-Memory System**:
    * **Short-Term Memory**: Uses an SQLite database to maintain turn-by-turn conversation flow accurately.
    * **Long-Term Semantic Memory**: Integrates with ChromaDB to create a vector-based memory, allowing the bot to recall thematically relevant events and information from the distant past.
* **Dynamic Persona & Scenery System**:
    * Choose from a list of pre-defined characters and scenes.
    * Create, save, and use your own custom personas.
    * Use the AI to generate entirely new, unique personas and environments on the fly.
* **Secure Admin Panel**: A comprehensive, owner-only admin panel (`/admin`) allows for real-time monitoring, system status checks, and runtime toggling of core features.
* **Persistent & Resilient**: User data, custom personas, and conversation states are persisted across bot restarts. Background tasks ensure stable operation.
* **[Optional & Pluggable NSFW Module](#content-moderation--nsfw-features)**: Includes a self-contained module for NSFW content that is designed for complete user and admin control.

---

## Content Moderation & NSFW Features

This bot includes optional **NSFW (Not Safe For Work) capabilities**, designed with user control and administrative flexibility as the highest priorities.

### For Users

* **Disabled by Default**: All NSFW features are **OFF** by default for every user.
* **Explicit Opt-In**: During the initial `/start` setup, new users will be explicitly asked via a button prompt if they wish to enable NSFW content.
* **Toggle Anytime**: Users can enable or disable the NSFW features at any time from the `/setup` menu. The menu will show the current status (ON/OFF).

### For Administrators (Self-Hosting)

The entire NSFW feature set is built as a self-contained "plug-in". If you wish to guarantee a 100% SFW environment on your instance of the bot, you can **completely remove all NSFW functionality** simply by deleting the **`nsfw.py`** file from the `src/handlers/` directory. The bot will detect that the file is missing and will not display any NSFW-related options.

---

## Installation & Setup

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/TursiThePanda/Telegram_AI_Bot_2.0.git](https://github.com/TursiThePanda/Telegram_AI_Bot_2.0.git)
    cd Telegram_AI_Bot_2.0
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Your Environment**
    * Rename the `.env.example` file (if provided) to `.env` or create a new `.env` file in the project's root directory.
    * Fill in the required values:
        ```env
        # --- Core Bot Credentials (Required) ---
        TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
        BOT_OWNER_ID=YOUR_TELEGRAM_USER_ID
        TELEGRAM_BOT_USERNAME=YourBotUsername

        # --- AI Model Server Configuration (Required) ---
        LM_STUDIO_API_BASE=http://localhost:1234/v1

        # --- AI Model Naming (Required) ---
        LM_STUDIO_CHAT_MODEL=repository/your-model-name-gguf
        LM_STUDIO_CREATIVE_MODEL=repository/your-model-name-gguf

        # --- Feature Toggles (Optional) ---
        VECTOR_MEMORY_ENABLED=1
        DEBUG_LOGGING=0
        ```

4.  **Run the Bot**
    * Ensure your LM Studio server is running with the specified model loaded.
    * Start the bot:
        ```bash
        python main.py
        ```

## Usage

* **`/start`**: The first command to run. It will guide new users through the character setup process.
* **`/setup`**: Access the main hub to change your persona, the scene, edit your profile, or manage your data.
* **`/regenerate`**: Redo the bot's last response.
* **`/clear`**: Wipes the current conversation history to start fresh.
* **`/admin`**: Access the owner-only administration panel.