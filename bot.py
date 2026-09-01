import os
import json
import time
import uuid
import logging
import asyncio
import tempfile
import subprocess
import itertools
import requests
import discord
from discord import app_commands
from discord.errors import NotFound
from dotenv import load_dotenv

logging.getLogger("discord").setLevel(logging.WARNING)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
WATERMARK_URL = (
    "https://raw.githubusercontent.com/redSBA/Ai/refs/heads/main/"
    "%D0%91%D0%B5%D0%B7%20%D0%BD%D0%B0%D0%B7%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F1_20260901175659.png"
)

if "?" not in WEBHOOK_URL:
    WEBHOOK_URL = WEBHOOK_URL + "?wait=true"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

PIXVERSE_KEYS = [k for k in [
    os.getenv("PIXVERSE_API_KEY_1"),
    os.getenv("PIXVERSE_API_KEY_2"),
] if k]
if not PIXVERSE_KEYS:
    raise ValueError("Нет ключей PixVerse! Добавь PIXVERSE_API_KEY_1 и/или PIXVERSE_API_KEY_2")

_key_cycle = itertools.cycle(PIXVERSE_KEYS)
WATERMARK_PATH = "/tmp/watermark.png"


def _get_key() -> str:
    return next(_key_cycle)


def _download_watermark():
    if not os.path.exists(WATERMARK_PATH):
        r = requests.get(WATERMARK_URL, timeout=30)
        r.raise_for_status()
        with open(WATERMARK_PATH, "wb") as f:
            f.write(r.content)
        print("[+] Watermark downloaded")


def _add_watermark(video_path: str, out_path: str):
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-i", video_path,
        "-i", WATERMARK_PATH,
        "-filter_complex", "overlay=W-w-10:H-h-10",
        "-c:a", "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pixverse_generate(prompt: str, negative: str = "blurry, low quality, text, watermark") -> str:
    base = "https://app-api.pixverse.ai"
    headers = {
        "API-KEY": _get_key(),
        "Ai-trace-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    payload = {
        "aspect_ratio": "16:9",
        "duration": 5,
        "model": "v6",
        "quality": "720p",
        "prompt": prompt,
        "negative_prompt": negative,
        "seed": 0,
        "water_mark": False,
    }
    r = requests.post(f"{base}/openapi/v2/video/text/generate", headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["Resp"]["video_id"]


def _pixverse_status(video_id: str) -> dict:
    base = "https://app-api.pixverse.ai"
    headers = {
        "API-KEY": _get_key(),
        "Ai-trace-id": str(uuid.uuid4()),
    }
    r = requests.get(f"{base}/openapi/v2/video/result/{video_id}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["Resp"]


def _poll_video(video_id: str, timeout: int = 300) -> str:
    start = time.time()
    while time.time() - start < timeout:
        resp = _pixverse_status(video_id)
        st = resp["status"]
        if st == 1:
            return resp["url"]
        if st in (7, 8):
            raise RuntimeError(f"PixVerse failed (status={st})")
        time.sleep(5)
    raise TimeoutError("PixVerse timeout")


@tree.command(name="pixverse", description="Сгенерировать видео через PixVerse V6")
@app_commands.describe(prompt="Описание видео")
async def pixverse_cmd(interaction: discord.Interaction, prompt: str):
    try:
        await interaction.response.defer(ephemeral=True)
    except NotFound:
        return
    except Exception as e:
        print(f"[!] defer: {e}")
        return

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
        await interaction.followup.send(f"❌ Webhook: `{e}`", ephemeral=True)
        return

    video_url = None
    try:
        vid = await asyncio.to_thread(_pixverse_generate, prompt)
        video_url = await asyncio.to_thread(_poll_video, vid)
    except Exception as e:
        patch = WEBHOOK_URL.replace("?wait=true", "")
        if wait_msg_id:
            requests.patch(f"{patch}/messages/{wait_msg_id}", json={"content": f"❌ Ошибка: `{e}`"})
        await interaction.followup.send("❌ Не удалось сгенерировать.", ephemeral=True)
        return

    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw.mp4")
            out = os.path.join(tmp, "out.mp4")

            r = requests.get(video_url, timeout=60)
            r.raise_for_status()
            with open(raw, "wb") as f:
                f.write(r.content)

            await asyncio.to_thread(_add_watermark, raw, out)

            patch = WEBHOOK_URL.replace("?wait=true", "")
            if wait_msg_id:
                requests.delete(f"{patch}/messages/{wait_msg_id}")

            with open(out, "rb") as f:
                files = {"file": ("video.mp4", f, "video/mp4")}
                payload = {
                    "payload_json": json.dumps({
                        "content": f"🎬 **{interaction.user.display_name}**\n> {prompt}"
                    })
                }
                requests.post(WEBHOOK_URL, data=payload, files=files)

        await interaction.followup.send("✅ Видео отправлено!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Обработка видео: `{e}`", ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Бот {client.user} запущен! Команда: /pixverse")
    _download_watermark()


if __name__ == "__main__":
    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"[!] Перезапуск через 5 сек... ({e})")
            time.sleep(5)
