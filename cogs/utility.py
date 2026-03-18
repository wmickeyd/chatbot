import discord
from discord.ext import commands
import wikipediaapi
import numexpr
import asyncio
import logging
import database, models

logger = logging.getLogger(__name__)

async def calculate_logic(expression):
    """Evaluates a mathematical expression using numexpr safely."""
    try:
        # numexpr.evaluate is relatively safe for numerical expressions
        result = numexpr.evaluate(expression)
        return str(result)
    except Exception as e:
        logger.error(f"Error evaluating math: {e}")
        return f"Could not calculate '{expression}'. (Error: {e})"

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def wiki(self, ctx, *, query: str):
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

    @commands.command(aliases=['wolfram'])
    async def calc(self, ctx, *, expression: str):
        """Evaluates a mathematical expression (Advanced Calculator)."""
        async with ctx.typing():
            logger.info(f"Calc command for: {expression}")
            result = await calculate_logic(expression)
            await ctx.send(f"**Result:** `{result}`")

    @commands.command()
    async def ping(self, ctx):
        """Standard ping command."""
        await ctx.send('Pong!')

    @commands.command(name="set")
    async def _set(self, ctx, key: str = None, value: str = None):
        """Update your personal bot settings (e.g. !set model llama3)."""
        if not key or not value:
            return await ctx.send("Usage: `!set <key> <value>`\nKeys: `model`, `unit` (Celsius/Fahrenheit), `lang` (e.g., 'es', 'fr', 'en')")
        
        db = database.SessionLocal()
        try:
            user_id = str(ctx.author.id)
            profile = db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
            if not profile:
                profile = models.UserProfile(user_id=user_id)
                db.add(profile)
            
            if key.lower() == 'model':
                profile.preferred_model = value
            elif key.lower() == 'unit':
                profile.preferred_temp_unit = value
            elif key.lower() == 'lang':
                profile.preferred_lang = value
            else:
                return await ctx.send(f"Unknown setting: {key}. Available: `model`, `unit`, `lang`.")
            
            db.commit()
            await ctx.send(f"Successfully updated your `{key}` preference to `{value}`!")
        except Exception as e:
            logger.error(f"Error in !set command: {e}")
            await ctx.send(f"Could not update setting: {e}")
        finally:
            db.close()

    @commands.command(name="profile")
    async def _profile(self, ctx):
        """View your current bot settings."""
        db = database.SessionLocal()
        try:
            user_id = str(ctx.author.id)
            profile = db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
            if not profile:
                return await ctx.send("You haven't set any preferences yet. Use `!set` to customize your experience!")
            
            embed = discord.Embed(title=f"User Profile: {ctx.author.name}", color=discord.Color.teal())
            embed.add_field(name="Model", value=profile.preferred_model)
            embed.add_field(name="Temperature Unit", value=profile.preferred_temp_unit)
            embed.add_field(name="Language", value=profile.preferred_lang)
            await ctx.send(embed=embed)
        finally:
            db.close()

    @commands.command(name="commands")
    async def _commands(self, ctx):
        """Lists all available bot commands."""
        embed = discord.Embed(title="Kelor Bot Commands", color=discord.Color.blue())
        
        embed.add_field(name="!wiki <query>", value="Search Wikipedia for a summary.", inline=False)
        embed.add_field(name="!calc <expression>", value="Perform advanced math (e.g., `2^10`).", inline=False)
        embed.add_field(name="!set <key> <value>", value="Update your profile (e.g. `!set model llama3`).", inline=False)
        embed.add_field(name="!profile", value="View your current bot settings.", inline=False)
        embed.add_field(name="!track <url>", value="Start tracking a LEGO set price.", inline=False)
        embed.add_field(name="!tracked", value="List and manage all tracked LEGO sets.", inline=False)
        embed.add_field(name="!join / !leave", value="Join or leave a voice channel.", inline=False)
        embed.add_field(name="!play <url/search>", value="Play audio from YouTube, Spotify, etc.", inline=False)
        embed.add_field(name="!pause / !resume / !stop", value="Control music playback.", inline=False)
        embed.add_field(name="!speak <text>", value="Convert text to speech in voice channel.", inline=False)
        embed.add_field(name="Mention @Kelor", value="Ask me anything! I can search the web, read PDFs/Docs, translate text, get weather, and more.", inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
