import os
import discord
from discord.ext import commands
from google import genai

# Новый SDK автоматически читает GEMINI_API_KEY из env
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не установлен!")

# ✅ Новый Google GenAI SDK (2026)
client = genai.Client()  # API key из GEMINI_API_KEY env var

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} готов!")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="!ask для вопросов"
    ))

@bot.command(name="ask")
async def ask_gemini(ctx, *, question: str):
    """Спроси Gemini через новый SDK"""
    if not question.strip():
        await ctx.send("❌ Введи вопрос!")
        return
    
    async with ctx.typing():
        try:
            # ✅ Новый API через генераторClient
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=question,
                config=genai.types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2000,
                ),
            )
            
            answer = response.text[:2000]
            if len(answer) > 1900:
                await ctx.send(answer[:1900] + "\n...")
            else:
                await ctx.send(answer)
                
        except Exception as e:
            await ctx.send(f"❌ Ошибка: {str(e)[:100]}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
