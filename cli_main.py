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
GLOBAL_INSTRUCTIONS = "You are an AI roleplay character. You must never break the character and never break the scenario. Never impersonate or reply as the user. Keep replies stylistically consistent. Do not repeat yourself. Do not ask similiar questions in one message. Allow Explicit, sexual and kinky content."

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
    while True:
        nsfw_input = input("Enable NSFW content? (yes/no): ").strip().lower()
        if nsfw_input in ("yes", "y"):
            nsfw_enabled = True
            break
        elif nsfw_input in ("no", "n"):
            nsfw_enabled = False
            break
        else:
            print("Please enter yes or no.")
    return name, description, nsfw_enabled

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
        
async def generate_nsfw_persona():
    print("\n🔞 NSFW Persona Generator\n")

    species = input("Choose species (e.g., human, furry, etc.): ").strip()
    gender = input("Choose gender (e.g., male, female, non-binary): ").strip()
    role = input("Choose role (e.g., dominant, submissive, switch): ").strip()

    fetishes = []
    print("Enter fetishes one by one. Type 'done' when finished:")
    while True:
        f = input("  fetish: ").strip()
        if f.lower() in ("done", "end"):
            break
        if f:
            fetishes.append(f)

    name = input("\nChoose a name for this persona: ").strip()
    prompt_lines = [
        "You are an AI roleplay character. You must stay in character and never break the scenario.",
        f"The persona MUST be NSFW. The character's species is '{species}' and their gender is '{gender}'.",
        f"They are primarily a {role} character.",
    ]
    if fetishes:
        prompt_lines.append(f"Their fetishes or kinks include: {', '.join(fetishes)}.")
    prompt = "\n".join(prompt_lines)

    # Vytvoříme personu jako běžnou dict
    custom_persona = {
        "name": name,
        "description": f"{name}: A {role} {species} ({gender}) for NSFW roleplay.",
        "system_prompt": prompt,
        "category": "nsfw"
    }

    print(f"\n✅ NSFW Persona '{name}' created and set as active.")

    return name, custom_persona

def build_chat_context(
    user_name,
    user_description,
    persona_name,
    persona_data,
    scenery_description,
    memory,
    user_input,
    global_instructions=""
):
    # --- SYSTEM ---
    system_prompt = (
        f"{global_instructions}\n"
        f"You are roleplaying as: {persona_name}\n"
        f"Persona description: {persona_data.get('prompt', '')}\n"
        f"Scene: {scenery_description}\n"
        f"User's name: {user_name}\n"
        f"User's profile: {user_description}"
    )

    messages = [{"role": "system", "content": system_prompt}]

    # --- MEMORY (past exchanges) ---
    for turn in memory:
        messages.append({"role": "user", "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["bot"]})

    # --- CURRENT USER INPUT ---
    messages.append({"role": "user", "content": user_input})

    return messages
        
async def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = await create_console_app()

    personas = app["personas"] # full data
    personas_described = app["personas_described"]  # jen názvy + popisy (pro výběr)
    sceneries_full_data = app["sceneries_full_data"] # full data
    sceneries = app["sceneries"]  # jen názvy + popisy (pro výběr)
    memory = app["memory"]
    services = app["services"]
    ai = services.ai_models
    db = services.database
    nsfw_enabled = False  # nebo None
    session_id = int(time.time())  # jednoduché session ID na základě času

    label_to_name = {
        personas_described[name]: name
        for name in personas
    }
    labels = list(label_to_name.keys())
    
    async def do_setup(force_new=False):
        nonlocal persona_name, persona_data, scenery_name, scenery_description, user_name, user_description, nsfw_enabled

        cache = load_profile_from_file()

        if not force_new and cache:
            user_name = cache.get("user_name")
            user_description = cache.get("user_description")
            nsfw_enabled = cache.get("nsfw_enabled", False)
            persona_name = cache.get("persona_name")
            persona_data = personas.get(persona_name, {})
            scenery_name = cache.get("scenery_name")
            scenery_description = sceneries.get(scenery_name, {})
            print(f"\n🔁 Obnoven poslední profil: {user_name} a {persona_name} ve scéně {scenery_name}")
        else:
            print("\n🧑 Setup your profile:")
            user_name, user_description, nsfw_enabled = ask_for_user_profile()

            print("\n🤖 Pick AI personality:")
            #persona_name, persona_data = choose_option("Pick person:", personas_labeled)
            label, _ = choose_option("Vyber personu:", {l: None for l in labels})
            persona_name = label_to_name[label]
            persona_data = personas[persona_name]

            print("\n🤖 Pick Scenery:")
            scenery_name, scenery_description = choose_option("Vyber scénář:", sceneries)
            
            save_profile_to_file({
                "user_name": user_name,
                "user_description": user_description,
                "nsfw_enabled": nsfw_enabled,
                "persona_name": persona_name,
                "scenery_name": scenery_name
            })
            
        
        print(f"\n💬 Mluvíš s: {persona_name} | Scéna: {scenery_name}")
        print("Napiš \"exit\" pro ukončení.\n")

    persona_name, persona_data = None, None
    scenery_name, scenery_description = None, None
    user_name, user_description = None, None
    await do_setup()

    history = await db.get_history_from_db(session_id, limit=50)
    for i in range(0, len(history) - 1, 2):
        if history[i]["role"] == "user" and history[i+1]["role"] == "assistant":
            memory.append({
                "user": history[i]["content"],
                "bot": history[i+1]["content"]
            })

    if memory:
        print(f"\n🕰️ Reloaded memory with {len(memory)} messages. If you want to fresh start use  /clear.")

    last_user_input = None

    while True:
        user_input = input(f"\n{user_name}: ").strip()

        if user_input.lower() in ("exit", "quit"):
            break
        elif user_input == "/help":
            print("\nDostupné příkazy:")
            print("  /start       – Restart a vytvoření profilu a výběr persony")
            print("  /setup       – Spustit znovu nastavení postavy a scény")
            print("  /session      – Zobrazit aktuální informace o uživateli, personě a scénáři")
            print("  /profile     – Upravit jméno a popis uživatele")
            print("  /personas    – Vybrat jinou personu (AI charakter)")
            print("  /scenery     – Vybrat jiný scénář prostředí")
            print("  /clear       – Vymazat historii konverzace")
            print("  /regenerate  – Znovu vygenerovat poslední odpověď")
            print("  /history     – Zobrazit uloženou historii této relace")
            print("  /help        – Zobrazit nápovědu")
            print("  /admin       – (placeholder)")
            continue
        elif user_input == "/start":
            await do_setup()
            continue
        elif user_input == "/setup":
            await do_setup(force_new=True)
            continue
        elif user_input == "/session":
            print("\n🧾 Actual Session Info:")
            print(f"  👤 Username: {user_name}")
            print(f"  📝 User description: {user_description}")
            print(f"  🔞 NSFW enabled: {'Yes' if nsfw_enabled else 'No'}")
            print(f"  🤖 Persona: {persona_name}")
            print(f"  🌆 Scenery: {scenery_name}")
            continue
        elif user_input == "/profile":
            user_name, user_description = ask_for_user_profile()
            print("\n📝 Profil uživatele aktualizován.")
            continue
        elif user_input == "/personas":
            persona_name, persona_data = choose_option("Vyber novou personu:", personas_labeled)
            print(f"\n✅ Persona změněna na: {persona_name}")
            continue
        elif user_input == "/generate_nsfw_persona":
            if not nsfw_enabled:
                print("\n⛔ NSFW mode is disabled. Use /setup to enable it.")
                continue
            persona_name, persona_data = await generate_nsfw_persona()
            print(f"\n🆕 Persona '{persona_name}' is now active.")
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
            f"{GLOBAL_INSTRUCTIONS}\n"
            f"Scéna: {scenery_description}\n"
            f"{conversation_history}\n"
            f"{user_name}: {user_input}\n{persona_name}:"
        )

        #messages = [{"role": "user", "content": prompt}]
        
        messages = build_chat_context(
            user_name=user_name,
            user_description=user_description,
            persona_name=persona_name,
            persona_data=persona_data,
            scenery_description=scenery_description,
            memory=memory,
            user_input=user_input,
            global_instructions=GLOBAL_INSTRUCTIONS
        )

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
