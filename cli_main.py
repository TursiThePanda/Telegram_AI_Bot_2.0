# cli_main.py
"""
Console-based version of the AI Role-Playing Bot.
Allows interaction via CLI instead of Telegram.
"""
import os
import asyncio
import logging
import time
import json

from src.utils import files as file_utils
from src.config import PERSONAS_PATH, SCENERIES_PATH

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_NO_TQDM"] = "1"

# CLI version of app initializer
from src.core.cli_application import create_console_app

CONFIG_CACHE_FILE = ".cli_profile.json"

def choose_option(title, options):
    print(f"\n{title}")
    for idx, name in enumerate(options, 1):
        print(f"  {idx}. {name}")
    while True:
        try:
            choice = int(input("Zadej číslo volby: "))
            if 1 <= choice <= len(options):
                return list(options.items())[choice - 1]  # (name, data)
        except ValueError:
            pass
        print("Neplatná volba, zkus to znovu.")


def ask_for_user_profile():
    name = input("\nWhat is Your name? ").strip()
    description = input("Who are you (about you, personality, traits, description...): ").strip()
    return name, description

def save_profile_to_file(data):
    with open(CONFIG_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_profile_from_file():
    if not os.path.exists(CONFIG_CACHE_FILE):
        return None
    try:
        with open(CONFIG_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
        
async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = await create_console_app()

    personas = app["personas"]
    sceneries = app["sceneries"]
    memory = app["memory"]
    services = app["services"]
    ai = services.ai_models
    db = services.database

    session_id = int(time.time())  # jednoduché session ID na základě času

    async def do_setup(force_new=False):
        nonlocal persona_name, persona_data, scenery_name, scenery_description, user_name, user_description

        cache = load_profile_from_file()

        if not force_new and cache:
            user_name = cache.get("user_name")
            user_description = cache.get("user_description")
            persona_name = cache.get("persona_name")
            persona_data = personas.get(persona_name, {})
            scenery_name = cache.get("scenery_name")
            scenery_description = sceneries.get(scenery_name, {})
            print(f"\n🔁 Obnoven poslední profil: {user_name} jako {persona_name} ve scéně {scenery_name}")
        else:
            print("\n🧑 Setup your profile:")
            user_name, user_description = ask_for_user_profile()

            print("\n🤖 Pick AI personality:")
            persona_name, persona_data = choose_option("Pick person:", personas)

            print("\n🤖 Pick Scenery:")
            scenery_name, scenery_description = choose_option("Vyber scénář:", sceneries)
            
            save_profile_to_file({
                "user_name": user_name,
                "user_description": user_description,
                "persona_name": persona_name,
                "scenery_name": scenery_name
            })
            
        
        print(f"\n💬 Mluvíš s: {persona_name} | Scéna: {scenery_name}")
        print("Napiš \"exit\" pro ukončení.\n")

    persona_name, persona_data = None, None
    scenery_name, scenery_description = None, None
    user_name, user_description = None, None
    await do_setup()

    last_user_input = None

    while True:
        user_input = input(f"\n{user_name}: ").strip()

        if user_input.lower() in ("exit", "quit"):
            break
        elif user_input == "/help":
            print("\nDostupné příkazy:")
            print("  /start       – Restart a vytvoření profilu a výběr persony")
            print("  /setup       – Spustit znovu nastavení postavy a scény")
            print("  /whoami      – Zobrazit aktuální informace o uživateli, personě a scénáři")
            print("  /profile     – Upravit jméno a popis uživatele")
            print("  /personas    – Vybrat jinou personu (AI charakter)")
            print("  /scenery     – Vybrat jiný scénář prostředí")
            print("  /clear       – Vymazat historii konverzace")
            print("  /regenerate  – Znovu vygenerovat poslední odpověď")
            print("  /history     – Zobrazit uloženou historii této relace")
            print("  /help        – Zobrazit nápovědu")
            print("  /admin       – (placeholder)")
            continue
        elif user_input == "/start" or user_input == "/setup":
            do_setup()
            continue
        elif user_input == "/whoami":
            print("\n🧾 Aktuální informace:")
            print(f"  👤 Uživatelské jméno: {user_name}")
            print(f"  📝 Popis uživatele: {user_description}")
            continue
        elif user_input == "/profile":
            user_name, user_description = ask_for_user_profile()
            print("\n📝 Profil uživatele aktualizován.")
            continue
        elif user_input == "/personas":
            persona_name, persona_data = choose_option("Vyber novou personu:", personas)
            print(f"\n✅ Persona změněna na: {persona_name}")
            continue
        elif user_input == "/scenery":
            scenery_name, scenery_description = choose_option("Vyber nové prostředí:", sceneries)
            print(f"\n🌆 Scéna změněna na: {scenery_name}")
            continue
        elif user_input == "/clear":
            memory.clear()
            await db.clear_history(session_id)
            print("\n🧹 Historie byla vymazána.")
            continue
        elif user_input == "/history":
            history = await db.get_history_from_db(session_id, limit=50)
            if not history:
                print("\n🕳️ Žádná historie nenalezena.")
            else:
                print("\n🕰️ Poslední zprávy:")
                for row in history:
                    timestamp = row["timestamp"]
                    role = row["role"]
                    content = row["content"]
                    print(f"[{role}] {content}")
            continue
        elif user_input == "/regenerate":
            if not last_user_input:
                print("\n⚠️ Není co znovu generovat.")
                continue
            user_input = last_user_input
        elif user_input == "/undo":
            await db.delete_last_interaction(session_id)
            print("\n↩️ Poslední interakce byla smazána.")
            continue
        elif user_input == "/admin":
            print("\n🔒 Admin funkce nejsou v CLI implementovány.")
            continue

        last_user_input = user_input

        conversation_history = "\n".join([
            f"{user_name}: {entry['user']}\n{persona_name}: {entry['bot']}" for entry in memory
        ])
        prompt = (
            f"Uživatel: {user_name}\nPopis uživatele: {user_description}\n"
            f"Persona: {persona_name}\nPopis persony: {persona_data.get('description', '')}\n"
            f"Scéna: {scenery_description}\n"
            f"{conversation_history}\n"
            f"{user_name}: {user_input}\n{persona_name}:"
        )

        messages = [{"role": "user", "content": prompt}]

        print(f"{persona_name}: ", end="", flush=True)
        response = ""
        async for chunk in ai.get_chat_response(messages=messages, task_type="chat", stream=True):
            print(chunk, end="", flush=True)
            response += chunk
        print()

        memory.append({"user": user_input, "bot": response})
        await db.add_message_to_db(session_id, "user", user_input)
        await db.add_message_to_db(session_id, "assistant", response)

        # print(f"{persona_name}: {response}")


if __name__ == "__main__":
    asyncio.run(main())
