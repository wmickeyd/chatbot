import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import logging
from config import TRACK_URL, TRACKED_URL, SCRAPER_BASE_URL

logger = logging.getLogger(__name__)

async def track_lego_logic(url, user_id=None, target_price=None):
    """Internal logic to track a LEGO set, reusable by commands and LLM tools."""
    supported_retailers = ["lego.com", "amazon.com", "walmart.com", "target.com"]
    if not any(r in url.lower() for r in supported_retailers):
        return "Please provide a valid URL from a supported retailer (LEGO, Amazon, Walmart, Target)."

    params = {"url": url}
    if user_id:
        params["user_id"] = str(user_id)
    if target_price:
        params["target_price"] = target_price

    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(TRACK_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    message = data.get('message', 'Successfully updated tracking.')
                    price = data.get('price', 'N/A')
                    target_msg = f" (Target: ${target_price})" if target_price else ""
                    return f"{message}{target_msg}. Current price: ${price}. URL: {url}"
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
    async def track(self, ctx, url: str, target_price: float = None):
        """Tracks the price of a LEGO set from a URL. Optional: target_price."""
        logger.info(f"Received !track command from {ctx.author}: {url} (target: {target_price})")
        async with ctx.typing():
            result = await track_lego_logic(url, user_id=ctx.author.id, target_price=target_price)
            logger.info(f"!track command completed for {ctx.author}: {result}")
            await ctx.send(result)

    @commands.command()
    async def tracked(self, ctx):
        """Lists all LEGO sets currently being tracked with interactive options."""
        logger.info(f"Received !tracked command from {ctx.author}")
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(TRACKED_URL, params={"user_id": str(ctx.author.id)}) as response:
                        if response.status == 200:
                            data = await response.json()
                            if not data:
                                return await ctx.send("Not tracking any LEGO sets yet.")
                            
                            embed = discord.Embed(title="Currently Tracked LEGO Sets", color=discord.Color.gold())
                            for item in data:
                                price = f"${item['latest_price']}" if item['latest_price'] else "Unknown"
                                target = f" (Target: ${item['target_price']})" if item.get('target_price') else ""
                                retailer = f" [{item.get('retailer', 'lego').upper()}]"
                                embed.add_field(
                                    name=f"{item['name']} ({item['product_number']}){retailer}",
                                    value=f"Price: {price}{target}\n[Link]({item['url']})",
                                    inline=False
                                )
                            
                            view = TrackedSetsView(data, SCRAPER_BASE_URL)
                            await ctx.send(embed=embed, view=view)
                        else:
                            await ctx.send(f"Error fetching tracked sets: {response.status}")
            except Exception as e:
                logger.error(f"Error in !tracked command: {e}")
                await ctx.send("Could not reach the tracking database.")

    @app_commands.command(name="track", description="Track the price of a LEGO set")
    @app_commands.describe(url="The product URL", target_price="Notify me when price hits this value")
    async def slash_track(self, interaction: discord.Interaction, url: str, target_price: float = None):
        await interaction.response.defer()
        result = await track_lego_logic(url, user_id=interaction.user.id, target_price=target_price)
        await interaction.followup.send(result)

    @app_commands.command(name="tracked", description="List your tracked LEGO sets")
    async def slash_tracked(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(TRACKED_URL, params={"user_id": str(interaction.user.id)}) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data:
                            return await interaction.followup.send("You aren't tracking any LEGO sets yet.")
                        embed = discord.Embed(title="Your Tracked LEGO Sets", color=discord.Color.gold())
                        for item in data:
                            price = f"${item['latest_price']}" if item['latest_price'] else "Unknown"
                            target = f" (Target: ${item['target_price']})" if item.get('target_price') else ""
                            retailer = f" [{item.get('retailer', 'lego').upper()}]"
                            embed.add_field(
                                name=f"{item['name']} ({item['product_number']}){retailer}",
                                value=f"Price: {price}{target}\n[Link]({item['url']})",
                                inline=False
                            )
                        view = TrackedSetsView(data, SCRAPER_BASE_URL)
                        await interaction.followup.send(embed=embed, view=view)
                    else:
                        await interaction.followup.send(f"Error fetching tracked sets: {response.status}")
        except Exception as e:
            logger.error(f"Error in /tracked: {e}")
            await interaction.followup.send("Could not reach the tracking database.")


async def setup(bot):
    await bot.add_cog(Tracking(bot))
