import discord
from discord.ext import commands
import os
import logging
import aiohttp
import json
import re
import base64
import PyPDF2
import docx
from deep_translator import GoogleTranslator
from RestrictedPython import compile_restricted, safe_builtins
import asyncio
from datetime import datetime, timedelta, timezone
from config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_VISION_MODEL,
    SCRAPER_URL, TRACK_URL, FINANCE_URL, SEARCH_URL,
    IMAGE_SEARCH_URL, WEATHER_URL, NEWS_URL, REDDIT_URL
)
import database, models
from .tracking import track_lego_logic

logger = logging.getLogger(__name__)

async def search_web(query):
    """Calls the utility API to search the web for a query with domain filtering."""
    params = {"q": query}
    timeout = aiohttp.ClientTimeout(total=60)
    blacklist = ["grokipedia.com", "pinterest.com", "facebook.com", "instagram.com", "twitter.com", "tiktok.com"]
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    filtered = [r for r in results if not any(domain in r['href'].lower() for domain in blacklist)]
                    formatted_results = "\n".join([f"- {r['title']}: {r['body']} (Link: {r['href']})" for r in filtered[:4]])
                    return formatted_results or "No reputable results found."
                else:
                    return f"Error from search: {response.status}"
    except Exception as e:
        logger.error(f"Error calling search: {e}")
        return f"Could not search right now. (Error: {e})"

async def read_url(url):
    """Calls the heavy scraper API to read a URL's text content."""
    params = {"url": url}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SCRAPER_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get('content', 'No content found.')
                    return f"SOURCE URL: {url}\n\nCONTENT:\n{content}"
                else:
                    return f"Error from scraper: {response.status}"
    except Exception as e:
        logger.error(f"Error calling scraper: {e}")
        return f"Could not reach my browser right now. (Error: {e})"

async def get_finance_data(symbol):
    """Calls the utility API to get stock or crypto prices."""
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
    """Calls the utility API to search for images."""
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
    """Calls the utility API to get weather data."""
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
    """Calls the utility API to get the latest news on a topic."""
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
    """Calls the utility API to read a Reddit thread."""
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
                    return f"DOCUMENT CONTENT (from {url}):\n\n{text[:5000]}"
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
        loc = {}
        byte_code = compile_restricted(code, filename='<string>', mode='exec')
        exec(byte_code, {'__builtins__': safe_builtins}, loc)
        if 'result' in loc:
            return str(loc['result'])
        return str(loc)
    except Exception as e:
        logger.error(f"Error executing python: {e}")
        return f"Execution error: {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_images",
            "description": "Search the web for images and return their URLs.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The image search query."}},
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
                "properties": {"symbol": {"type": "string", "description": "The ticker symbol."}},
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
                "properties": {"query": {"type": "string", "description": "The search query."}},
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
                "properties": {"url": {"type": "string", "description": "The full URL to read."}},
                "required": ["url"]
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
                "properties": {"url": {"type": "string", "description": "The LEGO.com product URL."}},
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
                "properties": {"location": {"type": "string", "description": "The city and country, e.g., 'London, UK'."}},
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
                "properties": {"query": {"type": "string", "description": "The news topic to search for."}},
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
                "properties": {"url": {"type": "string", "description": "The full Reddit thread URL."}},
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
                "properties": {"url": {"type": "string", "description": "The URL of the PDF or DOCX file."}},
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
                "properties": {"code": {"type": "string", "description": "The Python code to execute."}},
                "required": ["code"]
            }
        }
    }
]

class LLMCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ask_ollama(self, prompt, channel_id=None, user_id=None, images=None, system_override=None, current_messages=None):
        db = database.SessionLocal()
        model = OLLAMA_MODEL
        if user_id:
            profile = db.query(models.UserProfile).filter(models.UserProfile.user_id == str(user_id)).first()
            if profile and profile.preferred_model:
                model = profile.preferred_model
        
        messages = []
        if current_messages:
            messages = current_messages
        else:
            current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
            system_instruction = system_override or (
                f"You are Kelor, a utility assistant with REAL-TIME access to the web. Current time is {current_time}. "
                "You MUST use tools for any factual query. Call tools silently. Only mention a source if you include the URL."
            )
            messages.append({"role": "system", "content": system_instruction})
            
            # Retrieve last 10 messages from SQL database for current context (ALWAYS do this)
            if channel_id:
                history = db.query(models.ChatMessage).filter(models.ChatMessage.channel_id == str(channel_id)).order_by(models.ChatMessage.timestamp.desc()).limit(10).all()
                last_role = "system"
                for msg in reversed(history):
                    if msg.role != last_role and msg.content and msg.content.strip():
                        messages.append({"role": msg.role, "content": msg.content})
                        last_role = msg.role
            
            if prompt and prompt.strip():
                user_msg = {"role": "user", "content": prompt}
                if images: user_msg["images"] = images
                messages.append(user_msg)
            else:
                user_msg = {"role": "user", "content": "Analyze these photos." if images else "Hello"}
                if images: user_msg["images"] = images
                messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "tools": TOOLS
        }

        async def perform_request(current_payload):
            chat_url = OLLAMA_URL.replace("/generate", "/chat")
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.info(f"Sending request to Ollama: {model} (Tools: {'Yes' if current_payload.get('tools') else 'No'})")
                async with session.post(chat_url, json=current_payload) as response:
                    if response.status == 200:
                        full_response_content = ""
                        tool_calls = []
                        async for line in response.content:
                            if not line: continue
                            try:
                                data = json.loads(line.decode('utf-8'))
                                msg_chunk = data.get('message', {})
                                if msg_chunk.get('tool_calls'):
                                    tool_calls.extend(msg_chunk['tool_calls'])
                                    continue
                                chunk = msg_chunk.get('content', '')
                                full_response_content += chunk
                                if chunk: yield {"type": "content", "content": chunk, "full_content": full_response_content}
                                if data.get('done'): break
                            except json.JSONDecodeError: continue
                        if tool_calls:
                            yield {"type": "tool_calls", "calls": tool_calls, "messages": messages}
                        else:
                            if channel_id and not images:
                                db_inner = database.SessionLocal()
                                user_entry = models.ChatMessage(channel_id=str(channel_id), role="user", content=prompt or "Follow-up")
                                assistant_entry = models.ChatMessage(channel_id=str(channel_id), role="assistant", content=full_response_content)
                                db_inner.add(user_entry)
                                db_inner.add(assistant_entry)
                                db_inner.commit()
                                db_inner.close()
                    elif response.status == 400:
                        error_body = await response.text()
                        if "does not support tools" in error_body and "tools" in current_payload:
                            logger.warning(f"Model {model} does not support tools. Retrying without tools...")
                            new_payload = current_payload.copy()
                            del new_payload["tools"]
                            async for chunk in perform_request(new_payload): yield chunk
                        else:
                            logger.error(f"Ollama error: {response.status} - {error_body}")
                            yield {"type": "content", "content": f"Error: {response.status}"}
                    else:
                        error_body = await response.text()
                        logger.error(f"Ollama error: {response.status} - {error_body}")
                        yield {"type": "content", "content": f"Error: {response.status}"}

        try:
            async for chunk in perform_request(payload): yield chunk
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            yield {"type": "content", "content": f"Error: {e}"}
        finally: db.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return
        if message.content.startswith(self.bot.command_prefix): return

        if self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
            async with message.channel.typing():
                images = []
                docs = []
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment.url) as resp:
                                if resp.status == 200:
                                    img_data = await resp.read()
                                    images.append(base64.b64encode(img_data).decode('utf-8'))
                    elif any(attachment.filename.lower().endswith(ext) for ext in ['.pdf', '.docx']):
                        docs.append(attachment.url)

                prompt = re.sub(f'<@!?{self.bot.user.id}>', '', message.content).strip()
                if docs: prompt += "\n\nI have uploaded these documents:\n" + "\n".join(docs)
                
                msg_to_edit = None
                response_text = ""
                last_update_time = 0
                
                try:
                    active_messages = None
                    for turn in range(3):
                        found_tool_call = False
                        current_prompt = prompt if turn == 0 else None
                        async for chunk_data in self.ask_ollama(current_prompt, channel_id=message.channel.id, user_id=message.author.id, images=images if turn == 0 else None, current_messages=active_messages):
                            if chunk_data["type"] == "content":
                                chunk = chunk_data["content"]
                                response_text += chunk
                                if len(response_text) < 100: continue
                                if chunk.strip():
                                    if not msg_to_edit:
                                        msg_to_edit = await message.channel.send(response_text[:2000])
                                    elif (datetime.now().timestamp() - last_update_time) > 1.5:
                                        await msg_to_edit.edit(content=response_text[:2000])
                                        last_update_time = datetime.now().timestamp()
                            elif chunk_data["type"] == "tool_calls":
                                found_tool_call = True
                                active_messages = chunk_data["messages"]
                                active_messages.append({"role": "assistant", "tool_calls": chunk_data["calls"]})
                                for tool_call in chunk_data["calls"]:
                                    func_name = tool_call['function']['name']
                                    args = tool_call['function']['arguments']
                                    logger.info(f"Tool Call: {func_name}({args})")
                                    tool_result = "Unknown tool."
                                    if func_name == "search_web": tool_result = await search_web(args.get("query"))
                                    elif func_name == "read_url": tool_result = await read_url(args.get("url"))
                                    elif func_name == "track_lego_set": tool_result = await track_lego_logic(args.get("url"))
                                    elif func_name == "get_stock_crypto_price": tool_result = await get_finance_data(args.get("symbol"))
                                    elif func_name == "search_images": tool_result = await search_images(args.get("query"))
                                    elif func_name == "get_weather": tool_result = await get_weather(args.get("location"))
                                    elif func_name == "get_news": tool_result = await get_news(args.get("query"))
                                    elif func_name == "read_reddit": tool_result = await read_reddit(args.get("url"))
                                    elif func_name == "read_document": tool_result = await read_document(args.get("url"))
                                    elif func_name == "translate_text": tool_result = await translate_text(args.get("text"), args.get("target_lang", "en"))
                                    elif func_name == "execute_python": tool_result = await execute_python(args.get("code"))
                                    active_messages.append({"role": "tool", "content": str(tool_result), "tool_call_id": tool_call.get('id', 'fixed_id')})
                        if not found_tool_call: break
                    if msg_to_edit: await msg_to_edit.edit(content=response_text[:2000])
                    else: await message.channel.send(response_text[:2000])
                    if len(response_text) > 2000:
                        remainder = response_text[2000:]
                        for i in range(0, len(remainder), 2000): await message.channel.send(remainder[i:i+2000])
                except Exception as e:
                    logger.error(f"Error in on_message AI loop: {e}")
                    await message.channel.send(f"Sorry, I encountered an error: {e}")

async def setup(bot):
    await bot.add_cog(LLMCog(bot))
