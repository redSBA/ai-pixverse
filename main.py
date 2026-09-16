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

# ✅ Groq SDK для Llama
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
        name="/lamaask и /geminiask"
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

# ✅ Slash команда /lamaask
@bot.tree.command(name="lamaask", description="Спроси Llama 3.1 8B")
@app_commands.describe(question="Твой вопрос")
async def lamaask(interaction: discord.Interaction, question: str):
    """Спроси Llama 3.1 8B через Groq"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Llama через Groq (самый быстрый вариант)
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            await interaction.followup.send(
                "❌ Llama недоступна - не установлен GROQ_API_KEY в переменных окружения\n"
                "Добавь его в Railway → Variables"
            )
            return
        
        # Groq очень быстрый для Llama 3.1 8B
        chat_completion = client_groq.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model="llama-3.1-8b-instant",
            max_tokens=1024,
            temperature=0.7,
        )
        
        answer = chat_completion.choices[0].message.content[:4000]
        
        if len(answer) > 3900:
            await interaction.followup.send(f"🦙 **Llama 3.1 8B:**\n{answer[:3900]}\n...")
        else:
            await interaction.followup.send(f"🦙 **Llama 3.1 8B:**\n{answer}")
            
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
    print("🚀 Запуск Discord бота с поддержкой Gemini и Llama...")
    bot.run(DISCORD_TOKEN)
        
