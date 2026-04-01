import discord
from discord.ext import commands
import os
import logging
import aiohttp
import asyncio
import json
import re
import ast
from datetime import datetime
from config import ORCHESTRATOR_URL
import database, models

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds; doubles each attempt (1s, 2s, 4s)

class LLMCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ask_orchestrator(self, session_id, user_id, prompt, attachments=None):
        """Calls the Agent Orchestrator SSE endpoint with retry on connection errors."""
        payload = {
            "session_id": str(session_id),
            "user_id": str(user_id),
            "prompt": prompt,
            "attachments": attachments
        }

        timeout = aiohttp.ClientTimeout(total=600, sock_read=60)
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    logger.info(f"Connecting to Orchestrator for session {session_id} (attempt {attempt}/{MAX_RETRIES})")
                    async with session.post(ORCHESTRATOR_URL, json=payload) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            yield {"event": "error", "data": {"message": f"Orchestrator error {response.status}: {error_text}"}}
                            return

                        current_event = None
                        data_buffer = []
                        while True:
                            line = await response.content.readline()
                            if not line:
                                break
                            decoded_line = line.decode('utf-8').strip()

                            if not decoded_line:
                                if data_buffer:
                                    data_str = "\n".join(data_buffer)
                                    try:
                                        data = json.loads(data_str)
                                        yield {"event": current_event, "data": data}
                                    except json.JSONDecodeError:
                                        try:
                                            data = ast.literal_eval(data_str)
                                            yield {"event": current_event, "data": data}
                                        except Exception as e:
                                            logger.warning(f"Failed to decode SSE data: {data_str}. Error: {e}")
                                current_event = None
                                data_buffer = []
                            elif decoded_line.startswith("event:"):
                                current_event = decoded_line[6:].strip()
                            elif decoded_line.startswith("data:"):
                                data_buffer.append(decoded_line[5:].strip())
                            elif decoded_line.startswith(":"):
                                yield {"event": "heartbeat", "data": {"type": "keep-alive"}}
                # Completed successfully — exit retry loop
                return

            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(f"SSE connection error on attempt {attempt}/{MAX_RETRIES}: {e}")
            except Exception as e:
                # Non-connection errors (e.g. programming bugs) should not be retried
                logger.error(f"Unexpected SSE error: {e}")
                yield {"event": "error", "data": {"message": f"Critical error: {str(e)}"}}
                return

            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        logger.error(f"All {MAX_RETRIES} connection attempts failed: {last_error}")
        yield {"event": "error", "data": {"message": "Could not reach the orchestrator after several attempts. Please try again shortly."}}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return
        if message.content.startswith(self.bot.command_prefix): return

        if self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
            async with message.channel.typing():
                prompt = re.sub(f'<@!?{self.bot.user.id}>', '', message.content).strip()
                
                attachments = []
                for a in message.attachments:
                    attachments.append({"url": a.url, "filename": a.filename})

                msg_to_edit = None
                response_text = ""
                last_update_time = 0
                status_text = ""

                try:
                    async for event_data in self.ask_orchestrator(message.channel.id, message.author.id, prompt, attachments):
                        event = event_data["event"]
                        data = event_data["data"]

                        if event == "status":
                            status_text = f"*({data.get('state', 'processing')}...)*"
                        elif event == "content":
                            response_text += data.get("delta", "")
                        elif event == "error":
                            response_text = f"❌ Error: {data.get('message', 'Unknown error')}"
                        elif event == "final_answer":
                            response_text = data.get("content", response_text)
                            status_text = ""

                        if response_text.strip() or status_text:
                            display_text = f"{response_text}\n\n{status_text}" if status_text and event != "final_answer" else response_text
                            if not display_text.strip(): continue

                            if not msg_to_edit:
                                if len(display_text) > 5:
                                    msg_to_edit = await message.channel.send(display_text[:2000])
                            elif (datetime.now().timestamp() - last_update_time) > 1.2:
                                await msg_to_edit.edit(content=display_text[:2000])
                                last_update_time = datetime.now().timestamp()

                        if event == "final_answer":
                            if msg_to_edit:
                                await msg_to_edit.edit(content=response_text[:2000])
                            else:
                                await message.channel.send(response_text[:2000])
                            break

                except Exception as e:
                    logger.error(f"Thin Client Error: {e}")
                    await message.channel.send(f"I lost connection to my brain: {e}")

async def setup(bot):
    await bot.add_cog(LLMCog(bot))
