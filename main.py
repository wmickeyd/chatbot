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
load_dotenv(dotenv_path="deploy/base/.env")

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3')

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Memory storage (channel_id -> list of messages)
memory = {}

async def ask_ollama(prompt, channel_id=None):
    # Initialize memory for the channel if it doesn't exist
    if channel_id and channel_id not in memory:
        memory[channel_id] = []
    
    # Construct the full prompt with context
    context_prompt = ""
    if channel_id:
        for msg in memory[channel_id]:
            context_prompt += f"{msg['role']}: {msg['content']}\n"
    context_prompt += f"user: {prompt}\nassistant: "

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": context_prompt,
        "stream": False
    }
    timeout = aiohttp.ClientTimeout(total=300) # 5 minute timeout
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    ai_response = data.get('response', 'Sorry, I couldn\'t get a response from Ollama.')
                    
                    # Update memory
                    if channel_id:
                        memory[channel_id].append({"role": "user", "content": prompt})
                        memory[channel_id].append({"role": "assistant", "content": ai_response})
                        # Limit memory to last 10 messages (5 exchanges)
                        if len(memory[channel_id]) > 10:
                            memory[channel_id] = memory[channel_id][-10:]
                    
                    return ai_response
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

@bot.event
async def on_disconnect():
    logger.warning("Bot has disconnected from the Discord gateway. Attempting to reconnect...")

@bot.event
async def on_resumed():
    logger.info("Bot has successfully resumed its session.")

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

            logger.info(f'Asking Ollama (with context): {prompt}')
            response = await ask_ollama(prompt, channel_id=message.channel.id)
            await message.channel.send(response)

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("No DISCORD_TOKEN found in environment variables!")
    else:
        bot.run(DISCORD_TOKEN)