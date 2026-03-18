import discord
from discord.ext import commands
import aiohttp
import logging
from config import TRACK_URL, TRACKED_URL, SCRAPER_BASE_URL

logger = logging.getLogger(__name__)

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

class TrackedSetSelect(discord.ui.Select):
    def __init__(self, options, scraper_base_url):
        super().__init__(placeholder="Select a set to remove...", min_values=1, max_values=1, options=options)
        self.scraper_base_url = scraper_base_url

    async def callback(self, interaction: discord.Interaction):
        product_number = self.values[0]
        await interaction.response.send_message(f"Attempting to remove LEGO set {product_number}...", ephemeral=True)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(f"{self.scraper_base_url}/track/{product_number}") as response:
                    if response.status == 200:
                        await interaction.edit_original_response(content=f"Successfully removed LEGO set {product_number}.")
                    else:
                        await interaction.edit_original_response(content=f"Error removing set: {response.status}")
        except Exception as e:
            await interaction.edit_original_response(content=f"Failed to reach scraper: {e}")

class TrackedSetsView(discord.ui.View):
    def __init__(self, sets, scraper_base_url):
        super().__init__(timeout=60)
        self.sets = sets
        self.scraper_base_url = scraper_base_url
        
        options = [
            discord.SelectOption(label=f"{s['name'][:25]} ({s['product_number']})", value=s['product_number'], description=f"Price: ${s['latest_price']}")
            for s in sets[:25]
        ]
        
        if options:
            self.add_item(TrackedSetSelect(options, scraper_base_url))

class Tracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def track(self, ctx, url: str):
        """Tracks the price of a LEGO set from a URL."""
        logger.info(f"Received !track command from {ctx.author}: {url}")
        async with ctx.typing():
            result = await track_lego_logic(url)
            logger.info(f"!track command completed for {ctx.author}: {result}")
            await ctx.send(result)

    @commands.command()
    async def tracked(self, ctx):
        """Lists all LEGO sets currently being tracked with interactive options."""
        logger.info(f"Received !tracked command from {ctx.author}")
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(TRACKED_URL) as response:
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

async def setup(bot):
    await bot.add_cog(Tracking(bot))
