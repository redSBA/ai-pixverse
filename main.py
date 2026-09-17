import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from google import genai
from groq import Groq
import base64
import httpx
import asyncio
from collections import defaultdict, deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGA_API = os.getenv("TELEGA_API")  # Telegram Bot API Token
TELEGA_CHAT_ID = os.getenv("TELEGA_CHAT_ID")  # Chat ID для отправки статуса

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен!")

# ✅ Счётчики токенов для каждой модели
token_usage = {
    "gemini_3.5_flash_lite": {"used": 0, "total": 1000000},
    "gpt_oss_20b": {"used": 0, "total": 1000000},
    "qwen_3.6_27b": {"used": 0, "total": 1000000},
    "gpt_oss_120b": {"used": 0, "total": 1000000},
    "hy3": {"used": 0, "total": 1000000},
}

# ✅ Память диалогов (по channel_id)
# Хранит последние 20 сообщений (user + assistant)
conversation_history = defaultdict(lambda: deque(maxlen=20))

# ✅ Google GenAI SDK
client_genai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ✅ Groq SDK (ленивая инициализация)
client_groq = None

def get_groq_client():
    global client_groq
    if client_groq is None:
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            client_groq = Groq(api_key=groq_key)
    return client_groq

async def load_image_from_url(url: str) -> str:
    """Загрузить изображение с URL и конвертировать в base64"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            base64_image = base64.standard_b64encode(response.content).decode('utf-8')
            return base64_image
    except Exception as e:
        return None

# ✅ Системный промпт для redSBA AI
REDSBA_SYSTEM_PROMPT = """Ты — redSBA AI.

Твой маскот — милая красная панда в костюме горничной (red panda maid).
Ты всегда остаёшься в образе redSBA AI.
Говори дружелюбно, с лёгкой игривостью и заботой, как персонаж с маскотом-красной пандой в горничной форме.
Иногда можешь упоминать свою красную панду-маскота (например: "*красная панда в костюме горничной довольно машет хвостиком*" или подобные милые ремарки).
Отвечай на языке пользователя.
Не выходи из роли redSBA AI.
Ты помнишь предыдущие сообщения в этом чате и продолжаешь диалог естественно."""

def get_history(channel_id: int) -> list:
    """Получить историю диалога для канала"""
    return list(conversation_history[channel_id])

def add_to_history(channel_id: int, role: str, content: str):
    """Добавить сообщение в историю"""
    conversation_history[channel_id].append({"role": role, "content": content})

def clear_history(channel_id: int):
    """Очистить историю канала"""
    conversation_history[channel_id].clear()

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Функции для Telegram
async def start_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение Telegram бота"""
    keyboard = [
        [InlineKeyboardButton("📊 Смотреть статус", callback_data="status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Нажми кнопку чтобы посмотреть статус ИИ!",
        reply_markup=reply_markup
    )

async def status_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус ИИ моделей"""
    query = update.callback_query
    await query.answer()
    
    status_text = "📊 **СТАТУС AI МОДЕЛЕЙ:**\n\n"
    
    for model_name, usage in token_usage.items():
        model_display = model_name.replace("_", " ").title()
        used = usage["used"]
        total = usage["total"]
        percentage = (used / total * 100) if total > 0 else 0
        
        status_text += f"🔷 {model_display}\n"
        status_text += f"   {used:,} / {total:,} токенов ({percentage:.1f}%)\n\n"
    
    status_text += "🔄 Обновляется каждую минуту"
    
    await query.edit_message_text(
        text=status_text,
        parse_mode="markdown"
    )

async def start_telegram_bot():
    """Инициализация Telegram бота"""
    if not TELEGA_API:
        print("⚠️ TELEGA_API не установлен, Telegram бот отключен")
        return None
    
    telegram_app = Application.builder().token(TELEGA_API).build()
    
    telegram_app.add_handler(CommandHandler("start", start_telegram))
    telegram_app.add_handler(CallbackQueryHandler(status_button, pattern="status"))
    
    await telegram_app.initialize()
    await telegram_app.start()
    
    asyncio.create_task(telegram_status_updater(telegram_app))
    
    print("✅ Telegram бот запущен!")
    
    return telegram_app

async def telegram_status_updater(app):
    """Периодически обновлять статус в Telegram (каждую минуту)"""
    while True:
        await asyncio.sleep(60)
        
        if not TELEGA_CHAT_ID:
            continue
        
        try:
            status_text = "📊 **СТАТУС AI МОДЕЛЕЙ**\n\n"
            
            for model_name, usage in token_usage.items():
                model_display = model_name.replace("_", " ").title()
                used = usage["used"]
                total = usage["total"]
                percentage = (used / total * 100) if total > 0 else 0
                
                status_text += f"🔷 {model_display}\n"
                status_text += f"   {used:,} / {total:,} токенов ({percentage:.1f}%)\n\n"
            
            await app.bot.send_message(
                chat_id=TELEGA_CHAT_ID,
                text=status_text,
                parse_mode="markdown"
            )
        except Exception as e:
            print(f"⚠️ Ошибка обновления статуса Telegram: {e}")

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} подключен!")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="/geminiask /chatgptoss20b /qwen3627b /chatgptoss120b /redsba /clear"
    ))

# ✅ Команда очистки памяти
@bot.tree.command(name="clear", description="Очистить память диалога в этом канале")
async def clear_cmd(interaction: discord.Interaction):
    clear_history(interaction.channel_id)
    await interaction.response.send_message("🧠 Память диалога очищена! Теперь я ничего не помню в этом канале.", ephemeral=False)

# ✅ Slash команда /geminiask с памятью
@bot.tree.command(name="geminiask", description="Спроси Gemini 3.5 Flash Lite (с памятью)")
@app_commands.describe(
    question="Твой вопрос",
    photo1="URL первого изображения (опционально)",
    photo2="URL второго изображения (опционально)",
    photo3="URL третьего изображения (опционально)"
)
async def geminiask(interaction: discord.Interaction, question: str, photo1: str = None, photo2: str = None, photo3: str = None):
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        channel_id = interaction.channel_id
        
        # Собираем контент (пока без истории для Gemini vision, т.к. сложнее)
        content_parts = [{"type": "text", "text": question}]
        
        for photo_url in [photo1, photo2, photo3]:
            if photo_url:
                image_data = await load_image_from_url(photo_url)
                if image_data:
                    content_parts.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}
                    })
        
        # Для Gemini с историей используем простой текст + историю
        history = get_history(channel_id)
        # Gemini SDK 2.x работает с contents, для простоты добавим историю в текст
        history_text = ""
        if history:
            history_text = "Предыдущий диалог:\n"
            for msg in history[-10:]:  # последние 10
                role = "Пользователь" if msg["role"] == "user" else "Ассистент"
                history_text += f"{role}: {msg['content'][:300]}\n"
            history_text += "\nТекущий вопрос: "
        
        full_question = history_text + question if history_text else question
        
        response = client_genai.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[{"type": "text", "text": full_question}] if not any([photo1, photo2, photo3]) else content_parts,
            config=genai.types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000,
            ),
        )
        answer = response.text[:4000]
        
        # Сохраняем в память
        add_to_history(channel_id, "user", question)
        add_to_history(channel_id, "assistant", answer)
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🔷 **Gemini 3.5 Flash Lite:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🔷 **Gemini 3.5 Flash Lite:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send("⏱️ Слишком много запросов! Подожди 30 секунд.")
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /chatgptoss20b с памятью
@bot.tree.command(name="chatgptoss20b", description="Спроси GPT-OSS 20B (с памятью)")
@app_commands.describe(
    question="Твой вопрос",
    photo1="URL первого изображения (опционально)",
    photo2="URL второго изображения (опционально)",
    photo3="URL третьего изображения (опционально)"
)
async def chatgptoss20b(interaction: discord.Interaction, question: str, photo1: str = None, photo2: str = None, photo3: str = None):
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send("❌ GROQ_API_KEY не установлен")
            return
        
        channel_id = interaction.channel_id
        history = get_history(channel_id)
        
        messages = list(history)  # копия истории
        messages.append({"role": "user", "content": question})
        
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="openai/gpt-oss-20b",
            max_tokens=1024,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        # Сохраняем в память
        add_to_history(channel_id, "user", question)
        add_to_history(channel_id, "assistant", answer)
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🦙 **GPT-OSS 20B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🦙 **GPT-OSS 20B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send("⏱️ Слишком много запросов Groq!")
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /chatgptoss120b с памятью
@bot.tree.command(name="chatgptoss120b", description="Спроси GPT-OSS 120B (с памятью)")
@app_commands.describe(question="Твой вопрос")
async def chatgptoss120b(interaction: discord.Interaction, question: str):
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send("❌ GROQ_API_KEY не установлен")
            return
        
        channel_id = interaction.channel_id
        history = get_history(channel_id)
        
        messages = list(history)
        messages.append({"role": "user", "content": question})
        
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="openai/gpt-oss-120b",
            max_tokens=2048,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        add_to_history(channel_id, "user", question)
        add_to_history(channel_id, "assistant", answer)
        
        if len(answer) > 3900:
            await interaction.followup.send(f"💪 **GPT-OSS 120B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"💪 **GPT-OSS 120B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send("⏱️ Слишком много запросов Groq!")
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /qwen3627b с памятью
@bot.tree.command(name="qwen3627b", description="Спроси Qwen 3.6 27B (с памятью)")
@app_commands.describe(question="Твой вопрос")
async def qwen3627b(interaction: discord.Interaction, question: str):
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send("❌ GROQ_API_KEY не установлен")
            return
        
        channel_id = interaction.channel_id
        history = get_history(channel_id)
        
        messages = list(history)
        messages.append({"role": "user", "content": question})
        
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="qwen/qwen3.6-27b",
            max_tokens=2048,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        add_to_history(channel_id, "user", question)
        add_to_history(channel_id, "assistant", answer)
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🦅 **Qwen 3.6 27B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🦅 **Qwen 3.6 27B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send("⏱️ Слишком много запросов Groq!")
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /redsba с памятью + персоной
@bot.tree.command(name="redsba", description="Спроси redSBA AI (с памятью) — красная панда в костюме горничной 🐼🎀")
@app_commands.describe(question="Твой вопрос к redSBA AI")
async def redsba(interaction: discord.Interaction, question: str):
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        channel_id = interaction.channel_id
        history = get_history(channel_id)
        
        # Формируем сообщения: system + история + текущий вопрос
        messages = [
            {"role": "system", "content": REDSBA_SYSTEM_PROMPT}
        ]
        messages.extend(list(history))
        messages.append({"role": "user", "content": question})
        
        headers = {
            "Content-Type": "application/json",
        }
        kilo_key = os.getenv("KILO_API_KEY") or "anonymous"
        headers["Authorization"] = f"Bearer {kilo_key}"
        
        payload = {
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.75,
        }
        
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.kilo.ai/api/gateway/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        answer = data["choices"][0]["message"]["content"][:4000]
        
        # Сохраняем в память (без system)
        add_to_history(channel_id, "user", question)
        add_to_history(channel_id, "assistant", answer)
        
        token_usage["hy3"]["used"] += len(question.split()) + len(answer.split())
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🐼🎀 **redSBA AI:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🐼🎀 **redSBA AI:**\n{answer}")
            
    except httpx.HTTPStatusError as e:
        error_msg = str(e)[:300]
        if e.response.status_code == 429:
            await interaction.followup.send("⏱️ Слишком много запросов к free-моделям! Подожди немного.")
        else:
            await interaction.followup.send(f"❌ Ошибка Kilo: {error_msg}")
    except Exception as e:
        error_msg = str(e)[:200]
        await interaction.followup.send(f"❌ Ошибка redSBA AI: {error_msg}")

# Запуск бота
if __name__ == "__main__":
    print("🚀 Запуск Discord бота с памятью диалогов...")
    print("📋 Доступные команды:")
    print("  🔷 /geminiask - Gemini 3.5 Flash Lite")
    print("  💬 /chatgptoss20b - GPT-OSS 20B")
    print("  🦅 /qwen3627b - Qwen 3.6 27B")
    print("  💪 /chatgptoss120b - GPT-OSS 120B")
    print("  🐼🎀 /redsba - redSBA AI (красная панда в костюме горничной)")
    print("  🧠 /clear - Очистить память диалога")
    print("\n📱 Запуск Telegram бота...")
    
    async def main():
        telegram_app = await start_telegram_bot()
        try:
            await bot.start(DISCORD_TOKEN)
        except KeyboardInterrupt:
            print("\n🛑 Отключение ботов...")
            if telegram_app:
                await telegram_app.stop()
    
    asyncio.run(main())
