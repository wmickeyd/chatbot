import discord
from discord.ext import commands
import os
import logging
import aiohttp
import json
import re
from datetime import datetime
from config import ORCHESTRATOR_URL
import database, models

logger = logging.getLogger(__name__)

class LLMCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ask_orchestrator(self, session_id, user_id, prompt, attachments=None):
        """Calls the Agent Orchestrator SSE endpoint with heartbeat support."""
        payload = {
            "session_id": str(session_id),
            "user_id": str(user_id),
            "prompt": prompt,
            "attachments": attachments
        }
        
        timeout = aiohttp.ClientTimeout(total=600, sock_read=60) # High total, but expect data frequently
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.info(f"Connecting to Orchestrator for session {session_id}")
                async with session.post(ORCHESTRATOR_URL, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        yield {"event": "error", "data": {"message": f"Orchestrator error {response.status}: {error_text}"}}
                        return

                    # SSE parsing loop
                    current_event = None
                    async for line in response.content:
                        if not line: continue
                        decoded_line = line.decode('utf-8').strip()
                        
                        if not decoded_line: # End of event block
                            current_event = None
                            continue
                        
                        if decoded_line.startswith("event:"):
                            current_event = decoded_line[6:].strip()
                        elif decoded_line.startswith("data:"):
                            data_str = decoded_line[5:].strip()
                            try:
                                data = json.loads(data_str)
                                yield {"event": current_event, "data": data}
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to decode SSE data: {data_str}")
                                continue
                        elif decoded_line.startswith(":"): # Heartbeat or comment
                            yield {"event": "heartbeat", "data": {"type": "keep-alive"}}
        except aiohttp.ClientError as e:
            logger.error(f"SSE Connection Error: {e}")
            yield {"event": "error", "data": {"message": f"Connection lost: {str(e)}"}}
        except Exception as e:
            logger.error(f"Unexpected SSE Error: {e}")
            yield {"event": "error", "data": {"message": f"Critical error: {str(e)}"}}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return
        if message.content.startswith(self.bot.command_prefix): return

        # Respond to mentions or DMs
        if self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
            async with message.channel.typing():
                prompt = re.sub(f'<@!?{self.bot.user.id}>', '', message.content).strip()
                
                # Gather attachments to pass to orchestrator
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
                            status_text = f"*({data['state']}...)*"
                        
                        elif event == "content":
                            response_text += data["delta"]
                        
                        elif event == "tool_result":
                            # Optionally show tool activity in a small way
                            pass

                        elif event == "error":
                            response_text = f"❌ Error: {data['message']}"

                        # Update Discord message with debounce
                        if response_text.strip() or status_text:
                            display_text = f"{response_text}\n\n{status_text}" if status_text and event != "final_answer" else response_text
                            
                            if not msg_to_edit:
                                if len(display_text) > 10: # Small buffer
                                    msg_to_edit = await message.channel.send(display_text[:2000])
                            elif (datetime.now().timestamp() - last_update_time) > 1.2:
                                await msg_to_edit.edit(content=display_text[:2000])
                                last_update_time = datetime.now().timestamp()

                        if event == "final_answer":
                            status_text = "" # Clear status on finish
                            if msg_to_edit:
                                await msg_to_edit.edit(content=response_text[:2000])
                            else:
                                await message.channel.send(response_text[:2000])

                except Exception as e:
                    logger.error(f"Thin Client Error: {e}")
                    await message.channel.send(f"I lost connection to my brain: {e}")

async def setup(bot):
    await bot.add_cog(LLMCog(bot))
