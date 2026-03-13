import discord
from discord.ext import commands
import os
import logging
import aiohttp
import json
from gtts import gTTS
import asyncio
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
    
    # Check for voice support
    try:
        import nacl
        logger.info("PyNaCl is installed and available.")
    except ImportError:
        logger.error("PyNaCl is NOT installed correctly!")

    try:
        if not discord.opus.is_loaded():
            discord.opus.load_opus('libopus.so.0')
        logger.info(f"Opus is loaded: {discord.opus.is_loaded()}")
    except Exception as e:
        logger.error(f"Failed to load Opus: {e}")

    logger.info('------')

@bot.event
async def on_disconnect():
    logger.warning("Bot has disconnected from the Discord gateway. Attempting to reconnect...")

@bot.event
async def on_resumed():
    logger.info("Bot has successfully resumed its session.")

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        logger.info(f"Joined voice channel: {channel}")
    else:
        await ctx.send("You need to be in a voice channel first!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        logger.info("Left voice channel.")
    else:
        await ctx.send("I'm not in a voice channel!")

@bot.command()
async def speak(ctx, *, text=None):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            return await ctx.send("You need to be in a voice channel first!")

    if not text:
        return await ctx.send("Please provide some text for me to say.")

    async with ctx.typing():
        # Turn text into audio
        tts = gTTS(text=text, lang='en')
        tts.save("speech.mp3")

        # Play audio
        source = discord.FFmpegPCMAudio("speech.mp3")
        ctx.voice_client.play(source, after=lambda e: os.remove("speech.mp3") if os.path.exists("speech.mp3") else None)
        logger.info(f"Speaking: {text}")

@bot.command()
async def ping(ctx):
    logger.info(f'Ping command received from {ctx.author}')
    await ctx.send('Pong!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Don't process AI responses for commands
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # Check if the bot is mentioned or if it's a DM
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
            if not prompt:
                prompt = "Hello!"

            logger.info(f'Asking Ollama (with context): {prompt}')
            response = await ask_ollama(prompt, channel_id=message.channel.id)
            
            # If bot is in a voice channel, speak the response too
            if message.guild.voice_client:
                # Use a separate task for TTS to not block message sending
                tts = gTTS(text=response, lang='en')
                filename = f"speech_{message.id}.mp3"
                tts.save(filename)
                source = discord.FFmpegPCMAudio(filename)
                message.guild.voice_client.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
            
            await message.channel.send(response)

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("No DISCORD_TOKEN found in environment variables!")
    else:
        bot.run(DISCORD_TOKEN)
