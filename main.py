import os
import discord
from discord.ext import commands
from discord import app_commands
from google import genai

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен!")

# ✅ Google GenAI SDK 2.23.0
client_genai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
        name="/geminiask для вопросов"
    ))

# ✅ Slash команда /geminiask
@bot.tree.command(name="geminiask", description="Спроси что-нибудь у Gemini")
@app_commands.describe(question="Твой вопрос")
async def geminiask(interaction: discord.Interaction, question: str):
    """Спроси Gemini 3.5 Flash через slash команду"""
    
    if not question.strip():
        await interaction.response.send_message("❌ Введи вопрос!", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # ✅ Новый API 2.23.0 (Trial tier compatible)
        # gemini-3.5-flash-lite - самая экономная модель
        response = client_genai.models.generate_content(
            model="gemini-3.5-flash-lite",  # Самая дешёвая Flash модель
            contents=question,
            config=genai.types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000,
            ),
        )
        
        answer = response.text[:4000]  # Discord лимит для обычных сообщений
        
        if len(answer) > 3900:
            await interaction.followup.send(answer[:3900] + "\n...")
        else:
            await interaction.followup.send(answer)
            
    except Exception as e:
        error_msg = str(e)[:200]
        
        # Trial tier specific error handling
        if "429" in error_msg or "rate" in error_msg.lower():
            await interaction.followup.send(
                "⏱️ Слишком много запросов! Trial tier имеет лимит.\n"
                "Подожди 30 секунд и попробуй снова."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            await interaction.followup.send(
                "❌ Ошибка доступа! Проверь API ключ и что Trial tier активен."
            )
        else:
            await interaction.followup.send(f"❌ Ошибка: {error_msg}")

# Запуск бота
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
    
