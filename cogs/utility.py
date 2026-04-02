import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal
import wikipediaapi
import asyncio
import random
import logging
import aiohttp
from config import ORCHESTRATOR_BASE_URL

logger = logging.getLogger(__name__)

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    async def _ask_raw(self, channel_id, user_id, prompt: str) -> str:
        """Send a prompt to the orchestrator and return the full response."""
        llm = self.bot.get_cog('LLMCog')
        if not llm:
            return "Error: LLM service is unavailable."
        response = ""
        async for event_data in llm.ask_orchestrator(channel_id, user_id, prompt):
            event = event_data["event"]
            if event == "content":
                response += event_data["data"].get("delta", "")
            elif event == "final_answer":
                response = event_data["data"].get("content", response)
                break
            elif event == "error":
                return f"Error: {event_data['data'].get('message', 'Unknown error')}"
        return response or "No response."

    async def _ask(self, ctx, prompt: str) -> str:
        return await self._ask_raw(ctx.channel.id, ctx.author.id, prompt)

    def _build_wiki_embed(self, result):
        summary = result["summary"][:1500] + "..." if len(result["summary"]) > 1500 else result["summary"]
        embed = discord.Embed(title=result["title"], url=result["url"], color=discord.Color.green())
        embed.description = summary
        embed.set_footer(text="Source: Wikipedia")
        return embed

    def _build_poll_embed(self, question, options):
        reactions = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        if options:
            description = "\n".join([f"{reactions[i]} {options[i]}" for i in range(len(options))])
            return discord.Embed(title=f"📊 {question}", description=description, color=discord.Color.blue()), reactions[:len(options)]
        return discord.Embed(title=f"📊 {question}", color=discord.Color.blue()), ["✅", "❌"]

    # ------------------------------------------------------------------ #
    # Prefix commands                                                      #
    # ------------------------------------------------------------------ #

    @commands.command()
    async def ping(self, ctx):
        """Standard ping command."""
        await ctx.send('Pong!')

    @commands.command()
    async def wiki(self, ctx, *, query: str):
        """Searches Wikipedia for a summary of a topic."""
        async with ctx.typing():
            def fetch_wiki():
                w = wikipediaapi.Wikipedia(user_agent="KelorBot/1.0", language='en')
                page = w.page(query)
                return {"title": page.title, "url": page.fullurl, "summary": page.summary} if page.exists() else None
            result = await asyncio.get_event_loop().run_in_executor(None, fetch_wiki)
            if result:
                await ctx.send(embed=self._build_wiki_embed(result))
            else:
                await ctx.send(f"I couldn't find a Wikipedia page for '{query}'.")

    @commands.command(name="weather")
    async def weather(self, ctx, *, location: str):
        """Fetch weather for a location via Kelor."""
        async with ctx.typing():
            await ctx.send((await self._ask(ctx, f"What is the current weather in {location}?"))[:2000])

    @commands.command(name="stock", aliases=["finance", "price"])
    async def stock(self, ctx, symbol: str):
        """Fetch stock/crypto price via Kelor."""
        async with ctx.typing():
            await ctx.send((await self._ask(ctx, f"What is the current price of {symbol}?"))[:2000])

    @commands.command(name="define")
    async def define(self, ctx, word: str):
        """Fetch the definition of a word via Kelor."""
        async with ctx.typing():
            await ctx.send((await self._ask(ctx, f"Define the word: {word}"))[:2000])

    @commands.command(name="youtube", aliases=["yt", "summarise"])
    async def youtube(self, ctx, url: str):
        """Summarise a YouTube video via Kelor."""
        async with ctx.typing():
            await ctx.send((await self._ask(ctx, f"Summarise this YouTube video: {url}"))[:2000])

    @commands.command(name="poll")
    async def poll(self, ctx, question: str, *options):
        """Creates a poll. Optionally provide up to 10 options."""
        if len(options) > 10:
            return await ctx.send("You can only have up to 10 options.")
        embed, reactions = self._build_poll_embed(question, list(options))
        msg = await ctx.send(embed=embed)
        for r in reactions:
            await msg.add_reaction(r)

    @commands.command(name="roll")
    async def roll(self, ctx, dice: str = "1d20"):
        """Rolls dice in the format NdN (e.g., 2d6)."""
        try:
            num, sides = map(int, dice.lower().split('d'))
            if num > 100 or sides > 1000:
                return await ctx.send("Dice count/sides too large!")
            rolls = [random.randint(1, sides) for _ in range(num)]
            await ctx.send(f"🎲 Rolling {dice}: `{' + '.join(map(str, rolls))} = {sum(rolls)}`")
        except ValueError:
            await ctx.send("Usage: `!roll NdN` (e.g., `!roll 2d6`)")

    @commands.command(name="set")
    async def _set(self, ctx, key: str = None, value: str = None):
        """Update your personal bot settings."""
        if not key or not value:
            return await ctx.send("Usage: `!set <key> <value>`\nKeys: `model`, `unit`, `lang`")
        await self._update_profile(ctx.author.id, key, value, ctx.send)

    @commands.command(name="profile")
    async def _profile(self, ctx):
        """View your current bot settings."""
        await self._send_profile(ctx.author.id, ctx.author.name, ctx.send)

    @commands.command(name="commands")
    async def _commands(self, ctx):
        """Lists all available bot commands."""
        embed = discord.Embed(title="Kelor Bot Commands", color=discord.Color.blue())
        embed.add_field(name="!wiki <query>", value="Wikipedia.", inline=True)
        embed.add_field(name="!weather <loc>", value="Weather.", inline=True)
        embed.add_field(name="!stock <sym>", value="Stock/Crypto.", inline=True)
        embed.add_field(name="!define <word>", value="Dictionary.", inline=True)
        embed.add_field(name="!youtube <url>", value="Summarise video.", inline=True)
        embed.add_field(name="!poll <q> [opts]", value="Poll.", inline=True)
        embed.add_field(name="!roll [dice]", value="Dice.", inline=True)
        embed.add_field(name="!purge <n>", value="Delete msgs.", inline=True)
        embed.add_field(name="!userinfo", value="User details.", inline=True)
        embed.add_field(name="!uptime", value="Bot uptime.", inline=True)
        embed.add_field(name="!set <key> <val>", value="Update settings.", inline=True)
        embed.add_field(name="!profile", value="View settings.", inline=True)
        embed.add_field(name="Mention @Kelor", value="AI chat.", inline=False)
        embed.set_footer(text="All commands also available as / slash commands.")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Shared profile helpers (used by both prefix and slash)              #
    # ------------------------------------------------------------------ #

    async def _update_profile(self, user_id, key, value, reply):
        key = key.lower()
        payload = {}
        if key == 'model':   payload['preferred_model'] = value
        elif key == 'unit':  payload['preferred_temp_unit'] = value
        elif key == 'lang':  payload['preferred_lang'] = value
        else:
            await reply(f"Unknown setting `{key}`. Valid keys: `model`, `unit`, `lang`")
            return
        url = f"{ORCHESTRATOR_BASE_URL}/v1/users/{user_id}"
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload) as r:
                if r.status == 200:
                    await reply(f"Updated `{key}` to `{value}`.")
                else:
                    await reply(f"Error updating profile: {r.status}")

    async def _send_profile(self, user_id, username, reply):
        url = f"{ORCHESTRATOR_BASE_URL}/v1/users/{user_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    embed = discord.Embed(title=f"User Profile: {username}", color=discord.Color.teal())
                    embed.add_field(name="Model", value=data.get('preferred_model', 'default'))
                    embed.add_field(name="Temperature Unit", value=data.get('preferred_temp_unit', 'Celsius'))
                    embed.add_field(name="Language", value=data.get('preferred_lang', 'en'))
                    await reply(embed=embed)
                else:
                    await reply("Could not retrieve your profile.")

    # ------------------------------------------------------------------ #
    # Slash commands                                                       #
    # ------------------------------------------------------------------ #

    @app_commands.command(name="ping", description="Check if Kelor is alive")
    async def slash_ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!")

    @app_commands.command(name="wiki", description="Search Wikipedia for a topic")
    @app_commands.describe(query="The topic to look up")
    async def slash_wiki(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        def fetch_wiki():
            w = wikipediaapi.Wikipedia(user_agent="KelorBot/1.0", language='en')
            page = w.page(query)
            return {"title": page.title, "url": page.fullurl, "summary": page.summary} if page.exists() else None
        result = await asyncio.get_event_loop().run_in_executor(None, fetch_wiki)
        if result:
            await interaction.followup.send(embed=self._build_wiki_embed(result))
        else:
            await interaction.followup.send(f"I couldn't find a Wikipedia page for '{query}'.")

    @app_commands.command(name="weather", description="Get the current weather for a location")
    @app_commands.describe(location="City, region, or zip code")
    async def slash_weather(self, interaction: discord.Interaction, location: str):
        await interaction.response.defer()
        result = await self._ask_raw(interaction.channel_id, interaction.user.id, f"What is the current weather in {location}?")
        await interaction.followup.send(result[:2000])

    @app_commands.command(name="stock", description="Get the current price of a stock or crypto")
    @app_commands.describe(symbol="Ticker symbol e.g. AAPL, BTC-USD")
    async def slash_stock(self, interaction: discord.Interaction, symbol: str):
        await interaction.response.defer()
        result = await self._ask_raw(interaction.channel_id, interaction.user.id, f"What is the current price of {symbol}?")
        await interaction.followup.send(result[:2000])

    @app_commands.command(name="define", description="Get the definition of a word")
    @app_commands.describe(word="The word to define")
    async def slash_define(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer()
        result = await self._ask_raw(interaction.channel_id, interaction.user.id, f"Define the word: {word}")
        await interaction.followup.send(result[:2000])

    @app_commands.command(name="youtube", description="Summarise a YouTube video")
    @app_commands.describe(url="The YouTube video URL")
    async def slash_youtube(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        result = await self._ask_raw(interaction.channel_id, interaction.user.id, f"Summarise this YouTube video: {url}")
        await interaction.followup.send(result[:2000])

    @app_commands.command(name="poll", description="Create a poll")
    @app_commands.describe(question="The poll question", options="Comma-separated options (leave blank for yes/no)")
    async def slash_poll(self, interaction: discord.Interaction, question: str, options: str = ""):
        opt_list = [o.strip() for o in options.split(",") if o.strip()] if options else []
        if len(opt_list) > 10:
            return await interaction.response.send_message("Maximum 10 options.", ephemeral=True)
        embed, reactions = self._build_poll_embed(question, opt_list)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for r in reactions:
            await msg.add_reaction(r)

    @app_commands.command(name="roll", description="Roll dice e.g. 2d6")
    @app_commands.describe(dice="Dice notation e.g. 2d6, 1d20 (default: 1d20)")
    async def slash_roll(self, interaction: discord.Interaction, dice: str = "1d20"):
        try:
            num, sides = map(int, dice.lower().split('d'))
            if num > 100 or sides > 1000:
                return await interaction.response.send_message("Dice count/sides too large!", ephemeral=True)
            rolls = [random.randint(1, sides) for _ in range(num)]
            await interaction.response.send_message(f"🎲 Rolling {dice}: `{' + '.join(map(str, rolls))} = {sum(rolls)}`")
        except ValueError:
            await interaction.response.send_message("Usage: `/roll 2d6`", ephemeral=True)

    @app_commands.command(name="set", description="Update your personal Kelor settings")
    @app_commands.describe(key="Setting to change", value="New value")
    async def slash_set(self, interaction: discord.Interaction, key: Literal["model", "unit", "lang"], value: str):
        await interaction.response.defer(ephemeral=True)
        await self._update_profile(interaction.user.id, key, value,
                                   lambda **kw: interaction.followup.send(**kw))

    @app_commands.command(name="profile", description="View your current Kelor settings")
    async def slash_profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._send_profile(interaction.user.id, interaction.user.name,
                                 lambda **kw: interaction.followup.send(**kw))


async def setup(bot):
    await bot.add_cog(Utility(bot))
