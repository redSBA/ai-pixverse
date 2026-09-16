import os
import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from groq import Groq

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен!")

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

# ✅ Slash команда /geminiask
@bot.tree.command(name="geminiask", description="Спроси Gemini 3.5 Flash Lite")
@app_commands.describe(question="Твой вопрос")
async def geminiask(interaction: discord.Interaction, question: str):
    """Спроси Gemini 3.5 Flash Lite"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Gemini через Google GenAI SDK
        response = client_genai.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=question,
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

# ✅ Slash команда /chatgptoss20b
@bot.tree.command(name="chatgptoss20b", description="Спроси GPT-OSS 20B")
@app_commands.describe(question="Твой вопрос")
async def chatgptoss20b(interaction: discord.Interaction, question: str):
    """Спроси GPT-OSS 20B через Groq"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Llama через Groq (самый быстрый вариант)
        groq_client = get_groq_client()
        if not groq_client:
            await interaction.followup.send(
                "❌ Llama недоступна - не установлен GROQ_API_KEY в переменных окружения\n"
                "Добавь его в Railway → Variables"
            )
            return
        
        # Groq очень быстрый для Llama 3.1 8B
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model="openai/gpt-oss-20b",  # llama-3.1-8b-instant закрыта, используем GPT-OSS 20B
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
        
        # Qwen 3.6 27B - мощная модель (замена для Llama 4 Scout)
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model="qwen/qwen3.6-27b",  # Qwen 3.6 27B (Llama 4 Scout закрыта)
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
    print("🚀 Запуск Discord бота с тремя AI моделями...")
    print("📋 Доступные команды:")
    print("  🔷 /geminiask - Gemini 3.5 Flash Lite")
    print("  🦙 /lamaask - GPT-OSS 20B")
    print("  🎯 /mixtralask - Mixtral 8x7B")
    bot.run(DISCORD_TOKEN)
        
