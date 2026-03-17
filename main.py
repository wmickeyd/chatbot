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
import PyPDF2
import docx
from deep_translator import GoogleTranslator
from RestrictedPython import compile_restricted, safe_builtins
import asyncio
import numexpr
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv(dotenv_path="deploy/base/.env")

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'gemma')
OLLAMA_VISION_MODEL = os.getenv('OLLAMA_VISION_MODEL', 'llava')
SCRAPER_BASE_URL = os.getenv('SCRAPER_BASE_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local')
SCRAPER_URL = f"{SCRAPER_BASE_URL}/read"
SEARCH_URL = f"{SCRAPER_BASE_URL}/search"
TRACK_URL = f"{SCRAPER_BASE_URL}/track"
SCRAPE_URL = f"{SCRAPER_BASE_URL}/scrape"
FINANCE_URL = f"{SCRAPER_BASE_URL}/finance"
IMAGE_SEARCH_URL = f"{SCRAPER_BASE_URL}/image_search"
WEATHER_URL = f"{SCRAPER_BASE_URL}/weather"
NEWS_URL = f"{SCRAPER_BASE_URL}/news"
REDDIT_URL = f"{SCRAPER_BASE_URL}/reddit"

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents, heartbeat_timeout=120.0)

# Memory storage (channel_id -> list of messages)
memory = {}

async def search_web(query):
    """Calls the webscraper API to search the web for a query with domain filtering."""
    params = {"q": query}
    timeout = aiohttp.ClientTimeout(total=60)
    blacklist = ["grokipedia.com", "pinterest.com", "facebook.com", "instagram.com", "twitter.com", "tiktok.com"]
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    
                    # Filter out blacklisted domains
                    filtered = []
                    for r in results:
                        if not any(domain in r['href'].lower() for domain in blacklist):
                            filtered.append(r)
                    
                    # Format top 4 filtered results
                    formatted_results = "\n".join([f"- {r['title']}: {r['body']} (Link: {r['href']})" for r in filtered[:4]])
                    return formatted_results or "No reputable results found."
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
                    content = data.get('content', 'No content found.')
                    # Prepend URL to content so LLM knows where it came from
                    return f"SOURCE URL: {url}\n\nCONTENT:\n{content}"
                else:
                    return f"Error from scraper: {response.status}"
    except Exception as e:
        logger.error(f"Error calling scraper: {e}")
        return f"Could not reach my browser right now. (Error: {e})"

async def track_lego_logic(url):
    """Internal logic to track a LEGO set, reusable by commands and LLM tools."""
    if "lego.com" not in url.lower():
        return "Please provide a valid LEGO.com URL."
    
    params = {"url": url}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Use TRACK_URL (which is a POST request in the scraper)
            async with session.post(TRACK_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    message = data.get('message', 'Successfully updated tracking.')
                    price = data.get('price', 'N/A')
                    return f"{message}. Current price: ${price}. URL: {url}"
                else:
                    return f"Error from scraper: {response.status}"
    except Exception as e:
        logger.error(f"Error tracking LEGO: {e}")
        return f"Could not reach tracking tool. Error: {e}"

async def get_finance_data(symbol):
    """Calls the webscraper API to get stock or crypto prices."""
    params = {"symbol": symbol}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(FINANCE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return f"Ticker: {data['symbol']}, Name: {data['name']}, Price: {data['price']} {data['currency']}"
                else:
                    return f"Error from finance tool: {response.status}"
    except Exception as e:
        logger.error(f"Error calling finance: {e}")
        return f"Could not get financial data. (Error: {e})"

async def search_images(query):
    """Calls the webscraper API to search for images."""
    params = {"q": query}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(IMAGE_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    formatted = "\n".join([f"- {r['title']}: {r['image']}" for r in results])
                    return formatted or "No images found."
                else:
                    return f"Error from image search: {response.status}"
    except Exception as e:
        logger.error(f"Error calling image search: {e}")
        return f"Could not search for images. (Error: {e})"

async def get_weather(location):
    """Calls the webscraper API to get weather data."""
    params = {"location": location}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(WEATHER_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return f"Weather for {data['location']}: {data['condition']}, Temperature: {data['temp']}, Feels like: {data['feels_like']}, Humidity: {data['humidity']}"
                else:
                    return f"Error from weather tool: {response.status}"
    except Exception as e:
        logger.error(f"Error calling weather: {e}")
        return f"Could not get weather data. (Error: {e})"

async def get_news(query):
    """Calls the webscraper API to get the latest news on a topic."""
    params = {"q": query}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(NEWS_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    formatted = "\n".join([f"- {r['title']}: {r['body']} (Link: {r['url']})" for r in results])
                    return formatted or "No news found for this topic."
                else:
                    return f"Error from news tool: {response.status}"
    except Exception as e:
        logger.error(f"Error calling news: {e}")
        return f"Could not get news. (Error: {e})"

async def read_reddit(url):
    """Calls the webscraper API to read a Reddit thread."""
    params = {"url": url}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(REDDIT_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    content = f"Title: {data['title']}\n\nContent:\n{data['content']}\n\nTop Comments:\n"
                    for comment in data.get('comments', []):
                        content += f"- {comment['author']}: {comment['body'][:200]}...\n"
                    return content
                else:
                    return f"Error from Reddit tool: {response.status}"
    except Exception as e:
        logger.error(f"Error calling Reddit tool: {e}")
        return f"Could not read Reddit thread. (Error: {e})"

async def read_document(url):
    """Downloads and extracts text from PDF or DOCX files."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    import io
                    text = ""
                    if url.lower().endswith('.pdf'):
                        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                        for page in pdf_reader.pages:
                            text += page.extract_text() or ""
                    elif url.lower().endswith('.docx'):
                        doc = docx.Document(io.BytesIO(content))
                        text = "\n".join([para.text for para in doc.paragraphs])
                    else:
                        return "Unsupported document format. Only PDF and DOCX are supported."
                    
                    return f"DOCUMENT CONTENT (from {url}):\n\n{text[:5000]}" # Limit to 5000 chars for context
                else:
                    return f"Error downloading document: {response.status}"
    except Exception as e:
        logger.error(f"Error reading document: {e}")
        return f"Could not read the document. (Error: {e})"

async def translate_text(text, target_lang='en'):
    """Translates text to a target language."""
    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return f"Translated text ({target_lang}): {translated}"
    except Exception as e:
        logger.error(f"Error translating text: {e}")
        return f"Could not translate. (Error: {e})"

async def execute_python(code):
    """Executes small Python snippets in a restricted sandbox."""
    try:
        # Prepare the restricted environment
        loc = {}
        # RestrictedPython.compile_restricted is used to compile the code
        byte_code = compile_restricted(code, filename='<string>', mode='exec')
        # We need to provide safe builtins
        exec(byte_code, {'__builtins__': safe_builtins}, loc)
        # Assuming the code might set a 'result' variable or we just return the local variables
        if 'result' in loc:
            return str(loc['result'])
        return str(loc)
    except Exception as e:
        logger.error(f"Error executing python: {e}")
        return f"Execution error: {e}"

async def calculate_logic(expression):
    """Evaluates a mathematical expression using numexpr safely."""
    try:
        # numexpr.evaluate is relatively safe for numerical expressions
        result = numexpr.evaluate(expression)
        # Convert result (which might be a numpy array or single value) to string
        return str(result)
    except Exception as e:
        logger.error(f"Error evaluating math: {e}")
        return f"Could not calculate '{expression}'. (Error: {e})"

# Tool Definitions for Ollama
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_images",
            "description": "Search the web for images and return their URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The image search query."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_crypto_price",
            "description": "Get the real-time price of a stock (e.g. AAPL, GOOGL) or crypto (e.g. BTC-USD, ETH-USD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "The ticker symbol."}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for real-time information, weather, news, or general knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Read and summarize the text content of a specific website URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL to read."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform advanced mathematical calculations or evaluate numerical expressions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16) * sin(pi/2)')."}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_lego_set",
            "description": "Start tracking the price of a LEGO set from a LEGO.com URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The LEGO.com product URL."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a specific location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city and country, e.g., 'London, UK'."}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get latest news headlines for a specific topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The news topic to search for."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_reddit",
            "description": "Read and summarize a Reddit thread and its top comments from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full Reddit thread URL."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read and extract text from an uploaded PDF or DOCX file URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the PDF or DOCX file."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "translate_text",
            "description": "Translate text into a target language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to translate."},
                    "target_lang": {"type": "string", "description": "Target language code (e.g., 'es' for Spanish, 'fr' for French, 'de' for German)."}
                },
                "required": ["text", "target_lang"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Execute a small Python script for complex logic or data processing in a sandbox. Result must be assigned to the variable 'result'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code to execute."}
                },
                "required": ["code"]
            }
        }
    }
]

async def ask_ollama(prompt, channel_id=None, images=None, system_override=None, current_messages=None):
    # Initialize memory for the channel if it doesn't exist
    if channel_id and channel_id not in memory:
        memory[channel_id] = []
    
    # Use vision model if images are provided, otherwise use text model
    model = OLLAMA_VISION_MODEL if images else OLLAMA_MODEL

    # Construct messages for /api/chat
    messages = []
    
    if current_messages:
        messages = current_messages
    else:
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
        system_instruction = system_override or (
            f"You are Kelor, a utility assistant with REAL-TIME access to the web. Current time is {current_time}. "
            "You MUST use tools for any factual query (population, weather, news, math). "
            "Call tools silently and then provide the final answer based on the results. "
            "Only mention a source if you include the actual URL in your response."
        )
        messages.append({"role": "system", "content": system_instruction})
        
        if channel_id and not images:
            for msg in memory[channel_id]:
                messages.append(msg)
        
        user_msg = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "tools": TOOLS if not images else [] 
    }

    # Switch to /api/chat for better tool support
    chat_url = OLLAMA_URL.replace("/generate", "/chat")
    
    timeout = aiohttp.ClientTimeout(total=120)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(chat_url, json=payload) as response:
                if response.status == 200:
                    full_response_content = ""
                    tool_calls = []
                    
                    async for line in response.content:
                        if not line: continue
                        try:
                            data = json.loads(line.decode('utf-8'))
                            msg_chunk = data.get('message', {})
                            
                            # Handle tool calls
                            if msg_chunk.get('tool_calls'):
                                tool_calls.extend(msg_chunk['tool_calls'])
                                continue
                                
                            chunk = msg_chunk.get('content', '')
                            full_response_content += chunk
                            if chunk:
                                yield {"type": "content", "content": chunk, "full_content": full_response_content}
                            
                            if data.get('done'):
                                break
                        except json.JSONDecodeError:
                            # Sometimes chunks are split or joined incorrectly
                            logger.warning(f"Failed to decode JSON line: {line}")
                            continue
                    
                    if tool_calls:
                        yield {"type": "tool_calls", "calls": tool_calls, "messages": messages}
                    else:
                        # Only update memory on final response
                        if channel_id and not images:
                            memory[channel_id].append({"role": "user", "content": prompt or "Follow-up"})
                            memory[channel_id].append({"role": "assistant", "content": full_response_content})
                            if len(memory[channel_id]) > 10:
                                memory[channel_id] = memory[channel_id][-10:]
                            logger.info(f"Memory updated for channel {channel_id}")
                else:
                    logger.error(f"Ollama error: {response.status}")
                    yield {"type": "content", "content": f"Error: Ollama returned status {response.status}"}
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        yield {"type": "content", "content": f"Error: {e}"}

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
    """Background task to update a health check file while the bot is connected and ready."""
    while not bot.is_closed():
        try:
            # Only touch the health file if the bot is actually connected AND ready
            if bot.is_ready():
                with open("/tmp/health", "w") as f:
                    f.write(str(datetime.now()))
            else:
                logger.warning("Bot is alive but not ready. Skipping health check update.")
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
        
        def fetch_wiki():
            wiki_wiki = wikipediaapi.Wikipedia(
                user_agent="KelorBot/1.0 (wmcdonald@example.com)",
                language='en'
            )
            page = wiki_wiki.page(query)
            if page.exists():
                return {"title": page.title, "url": page.fullurl, "summary": page.summary}
            return None

        # Run the blocking fetch in a thread
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fetch_wiki)
        
        if result:
            summary = result["summary"][:1500] + "..." if len(result["summary"]) > 1500 else result["summary"]
            embed = discord.Embed(title=result["title"], url=result["url"], color=discord.Color.green())
            embed.description = summary
            embed.set_footer(text="Source: Wikipedia")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"I couldn't find a Wikipedia page for '{query}'.")

@bot.command()
async def track(ctx, url: str):
    """Tracks the price of a LEGO set from a URL."""
    logger.info(f"Received !track command from {ctx.author}: {url}")
    async with ctx.typing():
        result = await track_lego_logic(url)
        logger.info(f"!track command completed for {ctx.author}: {result}")
        await ctx.send(result)

class TrackedSetsView(discord.ui.View):
    def __init__(self, sets, scraper_base_url):
        super().__init__(timeout=60)
        self.sets = sets
        self.scraper_base_url = scraper_base_url
        
        # Add a select menu for removal
        options = [
            discord.SelectOption(label=f"{s['name'][:25]} ({s['product_number']})", value=s['product_number'], description=f"Price: ${s['latest_price']}")
            for s in sets[:25] # Discord limit for select menus
        ]
        
        if options:
            self.add_item(TrackedSetSelect(options, scraper_base_url))

class TrackedSetSelect(discord.ui.Select):
    def __init__(self, options, scraper_base_url):
        super().__init__(placeholder="Select a set to remove...", min_values=1, max_values=1, options=options)
        self.scraper_base_url = scraper_base_url

    async def callback(self, interaction: discord.Interaction):
        product_number = self.values[0]
        # We need a way to delete a tracked set. Let's assume there's or we'll add a DELETE endpoint.
        # For now, I'll inform the user we're preparing the removal.
        await interaction.response.send_message(f"Attempting to remove LEGO set {product_number}...", ephemeral=True)
        
        try:
            async with aiohttp.ClientSession() as session:
                # Assuming the webscraper has or will have a DELETE /track/{product_number} endpoint
                # If it doesn't exist yet, we'll need to add it to the scraper.
                async with session.delete(f"{self.scraper_base_url}/track/{product_number}") as response:
                    if response.status == 200:
                        await interaction.edit_original_response(content=f"Successfully removed LEGO set {product_number}.")
                    else:
                        await interaction.edit_original_response(content=f"Error removing set: {response.status}")
        except Exception as e:
            await interaction.edit_original_response(content=f"Failed to reach scraper: {e}")

@bot.command()
async def tracked(ctx):
    """Lists all LEGO sets currently being tracked with interactive options."""
    logger.info(f"Received !tracked command from {ctx.author}")
    async with ctx.typing():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SCRAPER_BASE_URL}/tracked") as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data:
                            return await ctx.send("Not tracking any LEGO sets yet.")
                        
                        embed = discord.Embed(title="Currently Tracked LEGO Sets", color=discord.Color.gold())
                        for item in data:
                            price = f"${item['latest_price']}" if item['latest_price'] else "Unknown"
                            embed.add_field(
                                name=f"{item['name']} ({item['product_number']})",
                                value=f"Price: {price}\n[Link]({item['url']})",
                                inline=False
                            )
                        
                        view = TrackedSetsView(data, SCRAPER_BASE_URL)
                        await ctx.send(embed=embed, view=view)
                    else:
                        await ctx.send(f"Error fetching tracked sets: {response.status}")
        except Exception as e:
            logger.error(f"Error in !tracked command: {e}")
            await ctx.send("Could not reach the tracking database.")

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

@bot.command(aliases=['wolfram'])
async def calc(ctx, *, expression: str):
    """Evaluates a mathematical expression (Advanced Calculator)."""
    async with ctx.typing():
        logger.info(f"Calc command for: {expression}")
        result = await calculate_logic(expression)
        await ctx.send(f"**Result:** `{result}`")

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
            # 1. Attachment Detection (Images & Documents)
            images = []
            docs = []
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    logger.info(f"Image found: {attachment.filename}")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            if resp.status == 200:
                                img_data = await resp.read()
                                images.append(base64.b64encode(img_data).decode('utf-8'))
                elif any(attachment.filename.lower().endswith(ext) for ext in ['.pdf', '.docx']):
                    logger.info(f"Document found: {attachment.filename}")
                    docs.append(attachment.url)

            # 2. Extract clean prompt
            prompt = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
            
            # If documents were found, append their URLs to the prompt so the LLM knows it can read them
            if docs:
                prompt += "\n\nI have uploaded these documents, you can use the 'read_document' tool to read them if needed:\n" + "\n".join(docs)
            
            logger.info(f"Processing prompt: '{prompt}'")
            
            # 3. Decision Logic Loop (Multi-Turn Autonomous Loop)
            msg_to_edit = None
            response_text = ""
            last_update_time = 0
            
            try:
                # Use a loop to allow multiple tool calls in sequence
                active_prompt = prompt
                active_messages = None
                max_turns = 3 # Prevent infinite loops
                
                for turn in range(max_turns):
                    found_tool_call = False
                    # If it's the first turn, use prompt. If not, use None (asking Ollama to continue based on history)
                    current_prompt = prompt if turn == 0 else None
                    
                    async for chunk_data in ask_ollama(current_prompt, channel_id=message.channel.id, images=images if turn == 0 else None, current_messages=active_messages):
                        if chunk_data["type"] == "content":
                            chunk = chunk_data["content"]
                            response_text += chunk
                            
                            # Buffer first 100 chars to avoid "Edited" tag for short messages
                            if len(response_text) < 100:
                                continue

                            if chunk.strip(): # Only send if there's actual text
                                if not msg_to_edit:
                                    logger.info(f"Response exceeded buffer, starting stream for {message.author}")
                                    msg_to_edit = await message.channel.send(response_text[:2000])
                                elif (datetime.now().timestamp() - last_update_time) > 1.5:
                                    await msg_to_edit.edit(content=response_text[:2000])
                                    last_update_time = datetime.now().timestamp()
                        
                        elif chunk_data["type"] == "tool_calls":
                            found_tool_call = True
                            active_messages = chunk_data["messages"]
                            active_messages.append({"role": "assistant", "tool_calls": chunk_data["calls"]})

                            for call in chunk_data["calls"]:
                                func_name = call["function"]["name"]
                                args = call["function"]["arguments"]
                                logger.info(f"Turn {turn}: Bot calling tool {func_name} with {args}")

                                tool_result = ""
                                if func_name == "search_web":
                                    tool_result = await search_web(args.get("query"))
                                elif func_name == "read_url":
                                    tool_result = await read_url(args.get("url"))
                                elif func_name == "track_lego_set":
                                    tool_result = await track_lego_logic(args.get("url"))
                                elif func_name == "get_stock_crypto_price":
                                    tool_result = await get_finance_data(args.get("symbol"))
                                elif func_name == "calculate":
                                    tool_result = await calculate_logic(args.get("expression"))
                                elif func_name == "search_images":
                                    tool_result = await search_images(args.get("query"))
                                elif func_name == "get_weather":
                                    tool_result = await get_weather(args.get("location"))
                                elif func_name == "get_news":
                                    tool_result = await get_news(args.get("query"))
                                elif func_name == "read_reddit":
                                    tool_result = await read_reddit(args.get("url"))
                                elif func_name == "read_document":
                                    tool_result = await read_document(args.get("url"))
                                elif func_name == "translate_text":
                                    tool_result = await translate_text(args.get("text"), args.get("target_lang", "en"))
                                elif func_name == "execute_python":
                                    tool_result = await execute_python(args.get("code"))
                                
                                # Add tool result to history
                                active_messages.append({
                                    "role": "tool",
                                    "content": str(tool_result),
                                    "name": func_name
                                })
                                logger.info(f"Turn {turn}: Tool {func_name} result received.")

                                # Store URLs for final appending if needed
                                if func_name == "search_web":
                                    found_urls = re.findall(r'Link: (https?://\S+)', str(tool_result))
                                    if found_urls:
                                        response_text += f"\n\nSource:\n {found_urls[0]}"
                                elif func_name == "read_url" or func_name == "track_lego_set":
                                    found_urls = re.findall(r'https?://\S+', str(tool_result))
                                    if found_urls:
                                        response_text += f"\n\nSource:\n {found_urls[0]}"

                            # After processing tools, we loop back to ask_ollama
                            active_prompt = None
                            break                    
                    if not found_tool_call:
                        break # Bot is done thinking, move to final response
            except Exception as e:
                logger.error(f"Error in on_message turn loop: {e}")
                error_msg = f"Sorry, I encountered an error while thinking: {e}"
                if msg_to_edit:
                    await msg_to_edit.edit(content=error_msg)
                else:
                    await message.channel.send(error_msg)
            
            if msg_to_edit:
                # If we were already streaming, do one final edit to ensure it's complete
                await msg_to_edit.edit(content=response_text[:2000])
                logger.info(f"Streamed response completed for {message.author}")
            else:
                # If the message was small (under 100 chars), it never triggered msg_to_edit. 
                # Send it now as a fresh, single message.
                if response_text.strip():
                    await message.channel.send(response_text[:2000])
                    logger.info(f"Single response sent to {message.author}")
                else:
                    await message.channel.send("I couldn't find a clear answer.")
                    logger.warning(f"Empty response generated for {message.author}")
            
            # 4. Handle Voice/TTS
            if response_text and message.guild and message.guild.voice_client:
                try:
                    tts_text = response_text[:1000]
                    tts = gTTS(text=tts_text, lang='en')
                    filename = f"speech_{message.id}.mp3"
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, tts.save, filename)
                    source = discord.FFmpegPCMAudio(filename)
                    message.guild.voice_client.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
                except Exception as e:
                    logger.error(f"TTS Error: {e}")
            
            # 5. Handle Large Responses
            if len(response_text) > 2000:
                remainder = response_text[2000:]
                for i in range(0, len(remainder), 2000):
                    await message.channel.send(remainder[i:i+2000])

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("No DISCORD_TOKEN found in environment variables!")
    else:
        bot.run(DISCORD_TOKEN)
