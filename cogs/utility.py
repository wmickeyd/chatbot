import discord
from discord.ext import commands
import wikipediaapi
import asyncio
import logging
import aiohttp
from config import ORCHESTRATOR_BASE_URL, WEATHER_URL, FINANCE_URL

logger = logging.getLogger(__name__)

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
        """Directly fetch weather for a location (Bypasses Agent)."""
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(WEATHER_URL, params={"location": location}) as r:
                        if r.status == 200:
                            data = await r.json()
                            embed = discord.Embed(title=f"Weather: {data['location']}", color=discord.Color.blue())
                            embed.add_field(name="Condition", value=data['condition'])
                            embed.add_field(name="Temp", value=data['temp'])
                            embed.add_field(name="Feels Like", value=data['feels_like'])
                            embed.add_field(name="Humidity", value=data['humidity'])
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(f"Error fetching weather: {r.status}")
            except Exception as e:
                await ctx.send(f"Could not reach weather service: {e}")

    @commands.command(name="stock", aliases=["finance", "price"])
    async def stock(self, ctx, symbol: str):
        """Directly fetch stock/crypto price (Bypasses Agent)."""
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(FINANCE_URL, params={"symbol": symbol}) as r:
                        if r.status == 200:
                            data = await r.json()
                            embed = discord.Embed(title=f"Market Info: {data['symbol']}", color=discord.Color.gold())
                            embed.add_field(name="Name", value=data['name'])
                            embed.add_field(name="Price", value=f"{data['price']} {data['currency']}")
                            embed.set_footer(text=f"Source: {data['source']}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(f"Error fetching finance data: {r.status}")
            except Exception as e:
                await ctx.send(f"Could not reach finance service: {e}")

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
        embed.add_field(name="!wiki <query>", value="Search Wikipedia.", inline=True)
        embed.add_field(name="!weather <loc>", value="Direct weather report.", inline=True)
        embed.add_field(name="!stock <sym>", value="Direct price check.", inline=True)
        embed.add_field(name="!set <key> <val>", value="Update profile.", inline=True)
        embed.add_field(name="!profile", value="View settings.", inline=True)
        embed.add_field(name="!track <url>", value="Track a LEGO set price.", inline=True)
        embed.add_field(name="!tracked", value="List tracked LEGO sets.", inline=True)
        embed.add_field(name="!play <url>", value="Play music.", inline=True)
        embed.add_field(name="Mention @Kelor", value="Ask anything (Agent-powered).", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
