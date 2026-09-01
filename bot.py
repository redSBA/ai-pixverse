import os
import time
import logging
import asyncio
import requests
import discord
from discord import app_commands
from discord.errors import NotFound
from dotenv import load_dotenv

logging.getLogger("discord").setLevel(logging.WARNING)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = "AQ.Ab8RN6KZ1WESbbGrGkvNvHdjs1LY1VJnDAxMtOlulU4ajzNVMQ"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

if "?" not in WEBHOOK_URL:
    WEBHOOK_URL = WEBHOOK_URL + "?wait=true"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def split_message(text, limit=1900):
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def gemini_chat(prompt: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 0.9,
        },
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Ты — полезный ИИ-ассистент. Отвечай на русском языке. "
                    "Не используй HTML/XML-теги, markdown-списки с угловыми скобками. "
                    "Отвечай простым текстом, по существу, кратко."
                )
            }]
        }
    }

    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Пустой ответ от Gemini")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("Нет текста в ответе")

    return parts[0].get("text", "").strip()


# 🔥 КОМАНДА ПЕРЕИМЕНОВАНА В /gemini
@tree.command(name="gemini", description="Спросить ИИ (Gemini)")
@app_commands.describe(prompt="Ваш вопрос для ИИ")
async def gemini_command(interaction: discord.Interaction, prompt: str):
    try:
        await interaction.response.defer(ephemeral=True)
    except NotFound:
        print("[!] Interaction протух, пропускаем")
        return
    except Exception as e:
        print(f"[!] Ошибка defer: {e}")
        return

    # 1. Webhook "подождите"
    wait_payload = {
        "content": (
            f"⏳ **{interaction.user.display_name}** спрашивает:\n"
            f"> {prompt}\n\n"
            f"*Генерация ответа, подождите...*"
        )
    }

    wait_msg_id = None
    try:
        r = requests.post(WEBHOOK_URL, json=wait_payload, timeout=10)
        r.raise_for_status()
        wait_msg_id = r.json().get("id")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка webhook: `{e}`", ephemeral=True)
        return

    # 2. Gemini в отдельном потоке
    try:
        answer = await asyncio.to_thread(gemini_chat, prompt)
    except Exception as e:
        patch_url = WEBHOOK_URL.replace("?wait=true", "")
        if wait_msg_id:
            requests.patch(
                f"{patch_url}/messages/{wait_msg_id}",
                json={"content": f"❌ Ошибка Gemini: `{e}`"},
            )
        await interaction.followup.send("❌ Не удалось получить ответ.", ephemeral=True)
        return

    # 3. Редактируем на ответ
    full_text = (
        f"🤖 **{interaction.user.display_name}** спрашивает:\n"
        f"> {prompt}\n\n"
        f"{answer}"
    )
    chunks = split_message(full_text)

    patch_url = WEBHOOK_URL.replace("?wait=true", "")
    try:
        requests.patch(
            f"{patch_url}/messages/{wait_msg_id}",
            json={"content": chunks[0]},
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка редактирования: `{e}`", ephemeral=True)
        return

    for chunk in chunks[1:]:
        try:
            requests.post(WEBHOOK_URL, json={"content": chunk})
        except Exception as e:
            print(f"[ERROR] Follow-up: {e}")

    await interaction.followup.send("✅ Ответ отправлен!", ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Бот {client.user} запущен! Команда: /gemini")


if __name__ == "__main__":
    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"[!] Перезапуск через 5 сек... ({e})")
            time.sleep(5)

