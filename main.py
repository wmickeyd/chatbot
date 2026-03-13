import discord
from discord.ext import commands
import os
import logging
import aiohttp
import json
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3')

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents)

async def ask_ollama(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    timeout = aiohttp.ClientTimeout(total=300) # 5 minute timeout
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('response', 'Sorry, I couldn\'t get a response from Ollama.')
                else:
                    logger.error(f"Ollama error: {response.status}")
                    return f"Error: Ollama returned status {response.status}"
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return "Sorry, I'm having trouble connecting to my brain right now."

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'Using Ollama model: {OLLAMA_MODEL} at {OLLAMA_URL}')
    logger.info('------')

@bot.command()
async def ping(ctx):
    logger.info(f'Ping command received from {ctx.author}')
    await ctx.send('Pong!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check if the bot is mentioned or if it's a DM
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
            if not prompt:
                prompt = "Hello!"

            logger.info(f'Asking Ollama: {prompt}')
            response = await ask_ollama(prompt)
            await message.channel.send(response)

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("No DISCORD_TOKEN found in environment variables!")
    else:
        bot.run(DISCORD_TOKEN)