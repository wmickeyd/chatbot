import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import logging
import io
import pandas as pd
import matplotlib.pyplot as plt
from config import TRACK_URL, TRACKED_URL, SCRAPER_BASE_URL, ALERTS_URL

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
    def __init__(self, options, scraper_base_url, parent_view):
        super().__init__(placeholder="Select a set for options...", min_values=1, max_values=1, options=options)
        self.scraper_base_url = scraper_base_url
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_set = self.values[0]
        # Find the retailer for the selected set
        for opt in self.options:
            if opt.value == self.values[0]:
                # We store the retailer in the description or label if needed, 
                # but for now let's assume 'lego' or parse from description
                self.parent_view.selected_retailer = "lego"
                if "AMAZON" in opt.label: self.parent_view.selected_retailer = "amazon"
                elif "WALMART" in opt.label: self.parent_view.selected_retailer = "walmart"
                elif "TARGET" in opt.label: self.parent_view.selected_retailer = "target"
                break
        
        await interaction.response.edit_message(view=self.parent_view)

class TrackedSetsView(discord.ui.View):
    def __init__(self, sets, scraper_base_url):
        super().__init__(timeout=60)
        self.sets = sets
        self.scraper_base_url = scraper_base_url
        self.selected_set = None
        self.selected_retailer = "lego"
        
        options = [
            discord.SelectOption(
                label=f"[{s.get('retailer', 'lego').upper()}] {s['name'][:20]}", 
                value=s['product_number'], 
                description=f"Set {s['product_number']} - Price: ${s['latest_price']}"
            )
            for s in sets[:25]
        ]
        
        if options:
            self.add_item(TrackedSetSelect(options, scraper_base_url, self))

    @discord.ui.button(label="Remove Set", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_set:
            return await interaction.response.send_message("Please select a set from the dropdown first.", ephemeral=True)
        
        await interaction.response.send_message(f"Removing {self.selected_set}...", ephemeral=True)
        try:
            params = {"user_id": str(interaction.user.id), "retailer": self.selected_retailer}
            async with aiohttp.ClientSession() as session:
                async with session.delete(f"{self.scraper_base_url}/track/{self.selected_set}", params=params) as response:
                    if response.status == 200:
                        await interaction.edit_original_response(content=f"Successfully removed LEGO set {self.selected_set}.")
                    else:
                        await interaction.edit_original_response(content=f"Error removing set: {response.status}")
        except Exception as e:
            await interaction.edit_original_response(content=f"Failed to reach scraper: {e}")

    @discord.ui.button(label="View History Chart", style=discord.ButtonStyle.primary)
    async def history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_set:
            return await interaction.response.send_message("Please select a set from the dropdown first.", ephemeral=True)
        
        await interaction.response.defer()
        try:
            async with aiohttp.ClientSession() as session:
                params = {"user_id": str(interaction.user.id), "retailer": self.selected_retailer}
                async with session.get(f"{self.scraper_base_url}/track/{self.selected_set}/history", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        history = data.get("history", [])
                        if len(history) < 2:
                            return await interaction.followup.send(f"Not enough price history for {data['name']} yet.", ephemeral=True)

                        df = pd.DataFrame(history)
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df = df.sort_values('timestamp')

                        plt.figure(figsize=(10, 5))
                        plt.plot(df['timestamp'], df['price'], marker='o', linestyle='-', color='gold')
                        plt.title(f"Price History: {data['name']} ({self.selected_set})")
                        plt.xlabel("Date")
                        plt.ylabel("Price ($)")
                        plt.grid(True, linestyle='--', alpha=0.7)
                        plt.xticks(rotation=45)
                        plt.tight_layout()

                        buf = io.BytesIO()
                        plt.savefig(buf, format='png')
                        buf.seek(0)
                        plt.close()

                        file = discord.File(buf, filename=f"lego_{self.selected_set}_history.png")
                        await interaction.followup.send(f"Price history for **{data['name']}**:", file=file)
                    else:
                        await interaction.followup.send("Could not fetch history for this set.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error generating history chart: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

class Tracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_alerts.start()

    def cog_unload(self):
        self.check_alerts.cancel()

    @tasks.loop(minutes=30)
    async def check_alerts(self):
        """Polls the scraper for sets that have hit their target price and DMs the user."""
        logger.info("Checking for LEGO price alerts...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ALERTS_URL) as response:
                    if response.status == 200:
                        alerts = await response.json()
                        for alert in alerts:
                            user_id = alert.get('user_id')
                            if not user_id:
                                continue
                            
                            try:
                                user = await self.bot.fetch_user(int(user_id))
                                if user:
                                    embed = discord.Embed(
                                        title="Price Alert! 🚨",
                                        description=f"The LEGO set **{alert['name']}** has hit your target price!",
                                        color=discord.Color.green()
                                    )
                                    embed.add_field(name="Current Price", value=f"${alert['current_price']}", inline=True)
                                    embed.add_field(name="Target Price", value=f"${alert['target_price']}", inline=True)
                                    embed.add_field(name="Retailer", value=alert['retailer'].upper(), inline=True)
                                    embed.add_field(name="Link", value=f"[Buy Now]({alert['url']})", inline=False)
                                    
                                    await user.send(embed=embed)
                                    logger.info(f"Sent price alert to user {user_id} for set {alert['product_number']}")
                                    
                                    # Acknowledge the alert so we don't send it again
                                    async with session.post(
                                        f"{SCRAPER_BASE_URL}/track/{alert['id']}/ack", 
                                        params={"price": alert['current_price']}
                                    ) as ack_res:
                                        if ack_res.status != 200:
                                            logger.error(f"Failed to acknowledge alert for {alert['id']}: {ack_res.status}")
                            except Exception as e:
                                logger.error(f"Error notifying user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Error in check_alerts task: {e}")

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

    @commands.command()
    async def history(self, ctx, product_number: str, retailer: str = "lego"):
        """Displays the price history chart for a tracked LEGO set."""
        logger.info(f"Received !history command from {ctx.author}: {product_number} ({retailer})")
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    params = {"user_id": str(ctx.author.id), "retailer": retailer.lower()}
                    async with session.get(f"{SCRAPER_BASE_URL}/track/{product_number}/history", params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            history = data.get("history", [])
                            if len(history) < 2:
                                return await ctx.send(f"Not enough price history yet for {data['name']} to generate a chart.")

                            # Generate Chart
                            df = pd.DataFrame(history)
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df = df.sort_values('timestamp')

                            plt.figure(figsize=(10, 5))
                            plt.plot(df['timestamp'], df['price'], marker='o', linestyle='-', color='gold')
                            plt.title(f"Price History: {data['name']} ({product_number})")
                            plt.xlabel("Date")
                            plt.ylabel("Price ($)")
                            plt.grid(True, linestyle='--', alpha=0.7)
                            plt.xticks(rotation=45)
                            plt.tight_layout()

                            # Save to buffer
                            buf = io.BytesIO()
                            plt.savefig(buf, format='png')
                            buf.seek(0)
                            plt.close()

                            file = discord.File(buf, filename=f"lego_{product_number}_history.png")
                            await ctx.send(f"Price history for **{data['name']}** at {retailer.upper()}:", file=file)
                        else:
                            await ctx.send(f"Error fetching history: {response.status}. Make sure you are tracking this set from this retailer.")
            except Exception as e:
                logger.error(f"Error in !history command: {e}")
                await ctx.send(f"Could not generate history chart: {e}")

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
