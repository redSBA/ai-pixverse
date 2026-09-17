import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from google import genai
from groq import Groq
import base64
import httpx
import asyncio
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
}

# ✅ Google GenAI SDK 2.23.0
client_genai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ✅ Groq SDK для Llama (ленивая инициализация)
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

# ✅ Запуск Telegram бота
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
    
    # Запуск фонового обновления статуса
    asyncio.create_task(telegram_status_updater(telegram_app))
    
    print("✅ Telegram бот запущен!")
    
    return telegram_app

async def telegram_status_updater(app):
    """Периодически обновлять статус в Telegram (каждую минуту)"""
    while True:
        await asyncio.sleep(60)  # Обновляем каждую минуту
        
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

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
        name="/geminiask /chatgptoss20b /qwen3627b /chatgptoss120b"
    ))

# ✅ Slash команда /geminiask с поддержкой фото
@bot.tree.command(name="geminiask", description="Спроси Gemini 3.5 Flash Lite")
@app_commands.describe(
    question="Твой вопрос",
    photo1="URL первого изображения (опционально)",
    photo2="URL второго изображения (опционально)",
    photo3="URL третьего изображения (опционально)"
)
async def geminiask(interaction: discord.Interaction, question: str, photo1: str = None, photo2: str = None, photo3: str = None):
    """Спроси Gemini 3.5 Flash Lite"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Gemini через Google GenAI SDK с поддержкой фото
        content_parts = [{"type": "text", "text": question}]
        
        # Добавляем фото если указаны
        for photo_url in [photo1, photo2, photo3]:
            if photo_url:
                image_data = await load_image_from_url(photo_url)
                if image_data:
                    content_parts.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}
                    })
        
        response = client_genai.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=content_parts,
            config=genai.types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000,
            ),
        )
        answer = response.text[:4000]
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🔷 **Gemini 3.5 Flash Lite:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🔷 **Gemini 3.5 Flash Lite:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send(
                "⏱️ Слишком много запросов! Подожди 30 секунд."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            await interaction.followup.send(
                "❌ Ошибка доступа! Проверь API ключ."
            )
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /chatgptoss20b с поддержкой фото
@bot.tree.command(name="chatgptoss20b", description="Спроси GPT-OSS 20B")
@app_commands.describe(
    question="Твой вопрос",
    photo1="URL первого изображения (опционально)",
    photo2="URL второго изображения (опционально)",
    photo3="URL третьего изображения (опционально)"
)
async def chatgptoss20b(interaction: discord.Interaction, question: str, photo1: str = None, photo2: str = None, photo3: str = None):
    """Спроси GPT-OSS 20B через Groq"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ GPT-OSS 20B через Groq с поддержкой фото
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send(
                "❌ GPT-OSS 20B недоступна - не установлен GROQ_API_KEY в переменных окружения\n"
                "Добавь его в Railway → Variables"
            )
            return
        
        # Загружаем фото если есть
        image_data_list = []
        for photo_url in [photo1, photo2, photo3]:
            if photo_url:
                img_data = await load_image_from_url(photo_url)
                if img_data:
                    image_data_list.append(img_data)
        
        # Формируем контент с фото
        content = question
        if image_data_list:
            # GPT-OSS 20B поддерживает изображения через vision
            content = f"{question}\n[Прикреплено {len(image_data_list)} изображение(й)]"
        
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            model="openai/gpt-oss-20b",
            max_tokens=1024,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🦙 **GPT-OSS 20B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🦙 **GPT-OSS 20B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send(
                "⏱️ Слишком много запросов Groq! Подожди немного."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            await interaction.followup.send(
                "❌ Ошибка доступа Groq! Проверь GROQ_API_KEY."
            )
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /chatgptoss120b
@bot.tree.command(name="chatgptoss120b", description="Спроси GPT-OSS 120B (Мощный)")
@app_commands.describe(question="Твой вопрос")
async def chatgptoss120b(interaction: discord.Interaction, question: str):
    """Спроси GPT-OSS 120B через Groq (мощная модель)"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ GPT-OSS 120B через Groq (очень мощная)
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send(
                "❌ GPT-OSS 120B недоступна - не установлен GROQ_API_KEY в переменных окружения\n"
                "Добавь его в Railway → Variables"
            )
            return
        
        # GPT-OSS 120B - мощная модель для сложных задач
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model="openai/gpt-oss-120b",  # Мощная модель (Mixtral закрыта)
            max_tokens=2048,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        if len(answer) > 3900:
            await interaction.followup.send(f"💪 **GPT-OSS 120B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"💪 **GPT-OSS 120B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send(
                "⏱️ Слишком много запросов Groq! Подожди немного."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            await interaction.followup.send(
                "❌ Ошибка доступа Groq! Проверь GROQ_API_KEY."
            )
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# ✅ Slash команда /qwen3627b
@bot.tree.command(name="qwen3627b", description="Спроси Qwen 3.6 27B")
@app_commands.describe(question="Твой вопрос")
async def qwen3627b(interaction: discord.Interaction, question: str):
    """Спроси Qwen 3.6 27B через Groq (замена Llama 4 Scout)"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Qwen 3.6 27B через Groq (замена Llama 4 Scout)
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send(
                "❌ Qwen 3.6 27B недоступна - не установлен GROQ_API_KEY в переменных окружения\n"
                "Добавь его в Railway → Variables"
            )
            return
        
        # Qwen 3.6 27B - мощная модель
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model="qwen/qwen3.6-27b",  # Правильное имя модели с точкой
            max_tokens=2048,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🦅 **Qwen 3.6 27B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🦅 **Qwen 3.6 27B:**\n{answer}")
            
    except Exception as e:
        error_msg = str(e)[:200]
        
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send(
                "⏱️ Слишком много запросов Groq! Подожди немного."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            await interaction.followup.send(
                "❌ Ошибка доступа Groq! Проверь GROQ_API_KEY."
            )
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# Запуск бота
if __name__ == "__main__":
    print("🚀 Запуск Discord бота с четырьмя AI моделями...")
    print("📋 Доступные команды:")
    print("  🔷 /geminiask - Gemini 3.5 Flash Lite")
    print("  💬 /chatgptoss20b - GPT-OSS 20B")
    print("  🦅 /qwen3627b - Qwen 3.6 27B")
    print("  💪 /chatgptoss120b - GPT-OSS 120B")
    print("\n📱 Запуск Telegram бота...")
    
    # Запускаем оба бота параллельно
    import asyncio
    
    async def main():
        # Запуск Telegram бота в отдельной задаче
        telegram_app = await start_telegram_bot()
        
        # Запуск Discord бота (блокирующий вызов)
        try:
            await bot.start(DISCORD_TOKEN)
        except KeyboardInterrupt:
            print("\n🛑 Отключение ботов...")
            if telegram_app:
                await telegram_app.stop()
    
    asyncio.run(main())
