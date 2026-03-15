import discord
from discord.ext import commands
import os
import logging
import aiohttp
import json
import re
import base64
import wikipediaapi
from gtts import gTTS
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv(dotenv_path="deploy/base/.env")

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3')
OLLAMA_VISION_MODEL = os.getenv('OLLAMA_VISION_MODEL', 'llava')
SCRAPER_URL = os.getenv('SCRAPER_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local/read')
SEARCH_URL = os.getenv('SEARCH_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local/search')
TRACK_URL = os.getenv('TRACK_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local/track')

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Memory storage (channel_id -> list of messages)
memory = {}

async def search_web(query):
    """Calls the webscraper API to search the web for a query."""
    params = {"q": query}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    # Format results for the LLM
                    formatted_results = "\n".join([f"- {r['title']}: {r['body']} (Link: {r['href']})" for r in results[:3]])
                    return formatted_results
                else:
                    return f"Error from search: {response.status}"
    except Exception as e:
        logger.error(f"Error calling search: {e}")
        return f"Could not search right now. (Error: {e})"

async def read_url(url):
    """Calls the webscraper API to read a URL's text content."""
    params = {"url": url}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SCRAPER_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('content', 'No content found.')
                else:
                    return f"Error from scraper: {response.status}"
    except Exception as e:
        logger.error(f"Error calling scraper: {e}")
        return f"Could not reach my browser right now. (Error: {e})"

async def ask_ollama(prompt, channel_id=None, images=None):
    # Initialize memory for the channel if it doesn't exist
    if channel_id and channel_id not in memory:
        memory[channel_id] = []
    
    # Use vision model if images are provided, otherwise use text model
    model = OLLAMA_VISION_MODEL if images else OLLAMA_MODEL

    # Construct the full prompt with context
    system_instruction = "You are Kelor, a helpful AI assistant with REAL-TIME access to the internet via search tools. Never say you don't have internet access. If search results are provided, use them to answer directly. Be concise and conversational."
    context_prompt = f"SYSTEM: {system_instruction}\n"
    if channel_id and not images: # History is mostly useful for text chat
        for msg in memory[channel_id]:
            context_prompt += f"{msg['role']}: {msg['content']}\n"
    context_prompt += f"user: {prompt}\nassistant: "

    payload = {
        "model": model,
        "prompt": context_prompt,
        "stream": False
    }
    
    if images:
        payload["images"] = images

    timeout = aiohttp.ClientTimeout(total=60) # 1 minute timeout
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    ai_response = data.get('response', 'Sorry, I couldn\'t get a response from Ollama.')
                    
                    # Update memory (only for text chat)
                    if channel_id and not images:
                        memory[channel_id].append({"role": "user", "content": prompt})
                        memory[channel_id].append({"role": "assistant", "content": ai_response})
                        if len(memory[channel_id]) > 10:
                            memory[channel_id] = memory[channel_id][-10:]
                    
                    return ai_response
                else:
                    logger.error(f"Ollama error: {response.status}")
                    return f"Error: Ollama returned status {response.status}"
    except asyncio.TimeoutError:
        logger.error("Ollama request timed out after 60 seconds.")
        return "Ollama is taking too long to respond. Please try again in a moment."
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return "Sorry, I'm having trouble connecting to my brain right now."

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'Using Ollama models: {OLLAMA_MODEL} (Text) and {OLLAMA_VISION_MODEL} (Vision)')
    
    # Start health check background task
    bot.loop.create_task(update_health_check())

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

async def update_health_check():
    """Background task to update a health check file while the bot is alive."""
    while not bot.is_closed():
        try:
            with open("/tmp/health", "w") as f:
                f.write(str(datetime.now()))
        except Exception as e:
            logger.error(f"Error updating health check: {e}")
        await asyncio.sleep(30)

@bot.event
async def on_disconnect():
    logger.warning("Bot has disconnected from the Discord gateway. Attempting to reconnect...")

@bot.event
async def on_resumed():
    logger.info("Bot has successfully resumed its session.")

@bot.command()
async def wiki(ctx, *, query: str):
    """Searches Wikipedia for a summary of a topic."""
    async with ctx.typing():
        logger.info(f"Wikipedia search for: {query}")
        wiki_wiki = wikipediaapi.Wikipedia(
            user_agent="KelorBot/1.0 (wmcdonald@example.com)",
            language='en'
        )
        page = wiki_wiki.page(query)
        
        if page.exists():
            summary = page.summary[:1500] + "..." if len(page.summary) > 1500 else page.summary
            embed = discord.Embed(title=page.title, url=page.fullurl, color=discord.Color.green())
            embed.description = summary
            embed.set_footer(text="Source: Wikipedia")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"I couldn't find a Wikipedia page for '{query}'.")

@bot.command()
async def track(ctx, url: str):
    """Tracks the price of a LEGO set from a URL."""
    if "lego.com" not in url.lower():
        return await ctx.send("Please provide a valid LEGO.com URL.")

    async with ctx.typing():
        params = {"url": url}
        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(os.getenv('SCRAPER_BASE_URL', 'http://webscraper.webscraper-dev.svc.cluster.local') + '/scrape', params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        name = data.get('name', 'Unknown Set')
                        prod_num = data.get('product_number', 'N/A')
                        price = data.get('price', 'Price not found')
                        embed = discord.Embed(title=f"LEGO Tracking: {name}", color=discord.Color.blue())
                        embed.add_field(name="Product Number", value=prod_num, inline=True)
                        embed.add_field(name="Current Price", value=f"${price}" if price != 'Price not found' else price, inline=True)
                        embed.set_footer(text=f"URL: {url}")
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"Error from scraper: {response.status}")
        except Exception as e:
            logger.error(f"Error tracking LEGO: {e}")
            await ctx.send(f"Could not reach my tracking tool right now. (Error: {e})")

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        try:
            await asyncio.wait_for(channel.connect(), timeout=10.0)
            logger.info(f"Joined voice channel: {channel}")
        except asyncio.TimeoutError:
            await ctx.send("Connection to voice channel timed out.")
        except Exception as e:
            await ctx.send(f"Failed to join voice channel: {e}")
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
        tts = gTTS(text=text, lang='en')
        filename = f"speech_{ctx.message.id}.mp3"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, tts.save, filename)
        source = discord.FFmpegPCMAudio(filename)
        ctx.voice_client.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            # 1. Image Detection
            images = []
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    logger.info(f"Image found: {attachment.filename}")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            if resp.status == 200:
                                img_data = await resp.read()
                                images.append(base64.b64encode(img_data).decode('utf-8'))

            # 2. Extract URLs and clean prompt
            urls = re.findall(r'(https?://\S+)', message.content)
            prompt = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
            logger.info(f"Processing prompt: '{prompt}'")
            
            # 3. Decision Logic (Image > Search > URL > Text)
            response = ""
            if images:
                logger.info("Using Vision Model")
                response = await ask_ollama(prompt or "What is in this image?", channel_id=message.channel.id, images=images)
            elif any(word in prompt.lower() for word in ["weather", "search", "who is", "what is", "how is", "current"]):
                logger.info(f"Triggering web search for: {prompt}")
                search_results_raw = await search_web(prompt)
                
                # If it's a weather search, try to 'read' the first result for better data
                deep_context = ""
                urls_found = re.findall(r'Link: (https?://\S+)', search_results_raw)
                if urls_found and ("weather" in prompt.lower() or "how is" in prompt.lower()):
                    logger.info(f"Deep scraping the first search result: {urls_found[0]}")
                    deep_context = await read_url(urls_found[0])
                
                if "Error from search" in search_results_raw or "Could not search right now" in search_results_raw:
                    response = f"I'm sorry, I tried to search for that but I'm having trouble connecting to my web browser right now. {search_results_raw}"
                else:
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    prompt = f"SYSTEM: Use the following search results and deep scrape data to answer. \n\nCurrent Time: {current_time}\n\nSearch Snippets:\n{search_results_raw}\n\nDeep Scrape Data:\n{deep_context[:2000]}\n\nUser Question: {prompt}"
                    logger.info("Sending enriched search results to Ollama")
                    response = await ask_ollama(prompt, channel_id=message.channel.id)
            elif urls:
                url_content = await read_url(urls[0])
                prompt = f"URL content from {urls[0]}:\n\n{url_content}\n\nUser Instruction: {prompt or 'Summarize this page.'}"
                response = await ask_ollama(prompt, channel_id=message.channel.id)
            else:
                response = await ask_ollama(prompt or "Hello!", channel_id=message.channel.id)
            
            # 4. Handle Voice/TTS
            if message.guild and message.guild.voice_client:
                try:
                    tts_text = response[:1000]
                    tts = gTTS(text=tts_text, lang='en')
                    filename = f"speech_{message.id}.mp3"
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, tts.save, filename)
                    source = discord.FFmpegPCMAudio(filename)
                    message.guild.voice_client.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
                except Exception as e:
                    logger.error(f"TTS Error: {e}")
            
            # 5. Split and Send
            if len(response) > 2000:
                for i in range(0, len(response), 2000):
                    await message.channel.send(response[i:i+2000])
            else:
                await message.channel.send(response)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("No DISCORD_TOKEN found in environment variables!")
    else:
        bot.run(DISCORD_TOKEN)
