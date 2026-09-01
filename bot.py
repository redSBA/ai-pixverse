import os
import json
import time
import uuid
import logging
import asyncio
import tempfile
import subprocess
import requests
import discord
from discord import app_commands
from discord.errors import NotFound
from dotenv import load_dotenv

logging.getLogger("discord").setLevel(logging.WARNING)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PIXVERSE_API_KEY = os.getenv("PIXVERSE_API_KEY")
WATERMARK_URL = (
    "https://raw.githubusercontent.com/redSBA/Ai/refs/heads/main/"
    "%D0%91%D0%B5%D0%B7%20%D0%BD%D0%B0%D0%B7%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F1_20260901175659.png"
)

if "?" not in WEBHOOK_URL:
    WEBHOOK_URL = WEBHOOK_URL + "?wait=true"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

WATERMARK_PATH = "/tmp/watermark.png"


def download_watermark():
    if not os.path.exists(WATERMARK_PATH):
        r = requests.get(WATERMARK_URL, timeout=30)
        r.raise_for_status()
        with open(WATERMARK_PATH, "wb") as f:
            f.write(r.content)
        print("[+] Watermark downloaded")


download_watermark()

import imageio_ffmpeg


def add_watermark(video_path: str, output_path: str):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-i", video_path,
        "-i", WATERMARK_PATH,
        "-filter_complex", "overlay=W-w-10:H-h-10",
        "-c:a", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pixverse_generate(prompt: str, negative_prompt: str = "blurry, low quality, text, watermark") -> str:
    base = "https://app-api.pixverse.ai"
    headers = {
        "API-KEY": PIXVERSE_API_KEY,
        "Ai-trace-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    payload = {
        "aspect_ratio": "16:9",
        "duration": 5,
        "model": "v6",
        "quality": "720p",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": 0,
        "water_mark": False,
    }
    r = requests.post(f"{base}/openapi/v2/video/text/generate", headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["Resp"]["video_id"]


def pixverse_status(video_id: str) -> dict:
    base = "https://app-api.pixverse.ai"
    headers = {
        "API-KEY": PIXVERSE_API_KEY,
        "Ai-trace-id": str(uuid.uuid4()),
    }
    r = requests.get(f"{base}/openapi/v2/video/result/{video_id}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["Resp"]


def poll_video(video_id: str, timeout: int = 300) -> str:
    start = time.time()
    while time.time() - start < timeout:
        resp = pixverse_status(video_id)
        status = resp["status"]
        if status == 1:
            return resp["url"]
        if status in (7, 8):
            raise RuntimeError(f"PixVerse generation failed (status={status})")
        time.sleep(5)
    raise TimeoutError("PixVerse generation timeout")


@tree.command(name="pixverse", description="Сгенерировать видео через PixVerse V6")
@app_commands.describe(prompt="Описание видео")
async def pixverse_command(interaction: discord.Interaction, prompt: str):
    try:
        await interaction.response.defer(ephemeral=True)
    except NotFound:
        return
    except Exception as e:
        print(f"[!] defer error: {e}")
        return

    # 1. Webhook "подождите"
    wait_payload = {
        "content": (
            f"⏳ **{interaction.user.display_name}** генерирует видео:\n"
            f"> {prompt}\n\n"
            f"*Ожидание PixVerse V6...*"
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

    # 2. Генерация в отдельном потоке
    video_url = None
    try:
        video_id = await asyncio.to_thread(pixverse_generate, prompt)
        video_url = await asyncio.to_thread(poll_video, video_id)
    except Exception as e:
        patch_url = WEBHOOK_URL.replace("?wait=true", "")
        if wait_msg_id:
            requests.patch(
                f"{patch_url}/messages/{wait_msg_id}",
                json={"content": f"❌ Ошибка генерации: `{e}`"},
            )
        await interaction.followup.send("❌ Не удалось сгенерировать видео.", ephemeral=True)
        return

    # 3. Скачать, наложить watermark, отправить
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "raw.mp4")
            out_path = os.path.join(tmpdir, "out.mp4")

            # Скачать видео
            r = requests.get(video_url, timeout=60)
            r.raise_for_status()
            with open(raw_path, "wb") as f:
                f.write(r.content)

            # Watermark
            await asyncio.to_thread(add_watermark, raw_path, out_path)

            # Удаляем "подождите"
            patch_url = WEBHOOK_URL.replace("?wait=true", "")
            if wait_msg_id:
                requests.delete(f"{patch_url}/messages/{wait_msg_id}")

            # Отправляем новое сообщение с файлом через webhook
            with open(out_path, "rb") as f:
                files = {"file": ("video.mp4", f, "video/mp4")}
                payload = {
                    "payload_json": json.dumps({
                        "content": f"🎬 **{interaction.user.display_name}**\n> {prompt}"
                    })
                }
                requests.post(WEBHOOK_URL, data=payload, files=files)

        await interaction.followup.send("✅ Видео отправлено!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка обработки видео: `{e}`", ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Бот {client.user} запущен! Команда: /pixverse")


if __name__ == "__main__":
    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"[!] Перезапуск через 5 сек... ({e})")
            time.sleep(5)
