import discord
from discord.ext import commands
import wikipediaapi
import asyncio
import logging
import aiohttp
from config import ORCHESTRATOR_BASE_URL

logger = logging.getLogger(__name__)

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _ask(self, ctx, prompt: str) -> str:
        """Sends a prompt to the orchestrator and returns the full response text."""
        llm = self.bot.get_cog('LLMCog')
        response = ""
        async for event_data in llm.ask_orchestrator(ctx.channel.id, ctx.author.id, prompt):
            event = event_data["event"]
            if event == "content":
                response += event_data["data"].get("delta", "")
            elif event == "final_answer":
                response = event_data["data"].get("content", response)
                break
            elif event == "error":
                return f"Error: {event_data['data'].get('message', 'Unknown error')}"
        return response or "No response."

    @commands.command()
    async def wiki(self, ctx, *, query: str):
        """Searches Wikipedia for a summary of a topic."""
        async with ctx.typing():
            def fetch_wiki():
                wiki_wiki = wikipediaapi.Wikipedia(
                    user_agent="KelorBot/1.0 (wmcdonald@example.com)",
                    language='en'
                )
                page = wiki_wiki.page(query)
                if page.exists():
                    return {"title": page.title, "url": page.fullurl, "summary": page.summary}
                return None

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

    @commands.command()
    async def ping(self, ctx):
        """Standard ping command."""
        await ctx.send('Pong!')

    @commands.command(name="weather")
    async def weather(self, ctx, *, location: str):
        """Fetch weather for a location via Kelor."""
        async with ctx.typing():
            result = await self._ask(ctx, f"What is the current weather in {location}?")
            await ctx.send(result[:2000])

    @commands.command(name="stock", aliases=["finance", "price"])
    async def stock(self, ctx, symbol: str):
        """Fetch stock/crypto price via Kelor."""
        async with ctx.typing():
            result = await self._ask(ctx, f"What is the current price of {symbol}?")
            await ctx.send(result[:2000])

    @commands.command(name="define")
    async def define(self, ctx, word: str):
        """Fetch the definition of a word via Kelor."""
        async with ctx.typing():
            result = await self._ask(ctx, f"Define the word: {word}")
            await ctx.send(result[:2000])

    @commands.command(name="poll")
    async def poll(self, ctx, question: str, *options):
        """Creates a poll with up to 10 options."""
        if not options:
            embed = discord.Embed(title=f"📊 {question}", color=discord.Color.blue())
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            return
        if len(options) > 10:
            return await ctx.send("You can only have up to 10 options.")
        reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        description = "\n".join([f"{reactions[i]} {options[i]}" for i in range(len(options))])
        embed = discord.Embed(title=f"📊 {question}", description=description, color=discord.Color.blue())
        msg = await ctx.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(reactions[i])

    @commands.command(name="roll")
    async def roll(self, ctx, dice: str = "1d20"):
        """Rolls dice in the format NdN (e.g., 2d20)."""
        try:
            import random
            num, sides = map(int, dice.lower().split('d'))
            if num > 100 or sides > 1000:
                return await ctx.send("Dice count/sides too large!")
            rolls = [random.randint(1, sides) for _ in range(num)]
            await ctx.send(f"🎲 Rolling {dice}: `{' + '.join(map(str, rolls))} = {sum(rolls)}`")
        except ValueError:
            await ctx.send("Usage: `!roll NdN` (e.g., `!roll 2d6`)")

    @commands.command(name="set")
    async def _set(self, ctx, key: str = None, value: str = None):
        """Update your personal bot settings via the Orchestrator."""
        if not key or not value:
            return await ctx.send("Usage: `!set <key> <value>`\nKeys: `model`, `unit`, `lang`")
        url = f"{ORCHESTRATOR_BASE_URL}/v1/users/{ctx.author.id}"
        payload = {}
        if key.lower() == 'model': payload['preferred_model'] = value
        elif key.lower() == 'unit': payload['preferred_temp_unit'] = value
        elif key.lower() == 'lang': payload['preferred_lang'] = value
        else: return await ctx.send(f"Unknown setting: {key}")
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload) as r:
                if r.status == 200:
                    await ctx.send(f"Successfully updated your `{key}` to `{value}`!")
                else:
                    await ctx.send(f"Error updating profile: {r.status}")

    @commands.command(name="profile")
    async def _profile(self, ctx):
        """View your current bot settings from the Orchestrator."""
        url = f"{ORCHESTRATOR_BASE_URL}/v1/users/{ctx.author.id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    embed = discord.Embed(title=f"User Profile: {ctx.author.name}", color=discord.Color.teal())
                    embed.add_field(name="Model", value=data.get('preferred_model'))
                    embed.add_field(name="Temperature Unit", value=data.get('preferred_temp_unit'))
                    embed.add_field(name="Language", value=data.get('preferred_lang'))
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Could not retrieve your profile.")

    @commands.command(name="commands")
    async def _commands(self, ctx):
        """Lists all available bot commands."""
        embed = discord.Embed(title="Kelor Bot Commands", color=discord.Color.blue())
        embed.add_field(name="!wiki <query>", value="Wikipedia.", inline=True)
        embed.add_field(name="!weather <loc>", value="Weather.", inline=True)
        embed.add_field(name="!stock <sym>", value="Stock/Crypto.", inline=True)
        embed.add_field(name="!define <word>", value="Dictionary.", inline=True)
        embed.add_field(name="!poll <q> [opts]", value="Poll.", inline=True)
        embed.add_field(name="!roll <dice>", value="Dice.", inline=True)
        embed.add_field(name="!purge <num>", value="Delete msgs.", inline=True)
        embed.add_field(name="!userinfo", value="User details.", inline=True)
        embed.add_field(name="!uptime", value="Bot uptime.", inline=True)
        embed.add_field(name="Mention @Kelor", value="Agent (AI).", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
