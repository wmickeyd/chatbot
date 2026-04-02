import discord
from discord import app_commands
from discord.ext import commands
import time
from datetime import datetime, timezone


class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    def _uptime_string(self):
        seconds = int(time.time() - self.start_time)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        return f"{days}d {hours}h {minutes}m {secs}s"

    def _userinfo_embed(self, member):
        color = member.color if isinstance(member, discord.Member) else discord.Color.blurple()
        embed = discord.Embed(title=f"User Info: {member.name}", color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        if isinstance(member, discord.Member) and member.joined_at:
            embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Joined Discord", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        if isinstance(member, discord.Member):
            roles = [r.mention for r in member.roles if r != member.guild.default_role]
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
        return embed

    def _serverinfo_embed(self, guild):
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.purple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Channels", value=f"{len(guild.text_channels)} Text / {len(guild.voice_channels)} Voice", inline=True)
        return embed

    # ------------------------------------------------------------------ #
    # Prefix commands                                                      #
    # ------------------------------------------------------------------ #

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """Deletes a specified number of messages (requires Manage Messages)."""
        if amount < 1:
            return await ctx.send("Please specify a positive number of messages to delete.")
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Successfully deleted {len(deleted)-1} messages.", delete_after=5)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Displays information about a user."""
        await ctx.send(embed=self._userinfo_embed(member or ctx.author))

    @commands.command()
    async def serverinfo(self, ctx):
        """Displays information about the server."""
        await ctx.send(embed=self._serverinfo_embed(ctx.guild))

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running."""
        await ctx.send(f"I've been online for: `{self._uptime_string()}`")

    # ------------------------------------------------------------------ #
    # Slash commands                                                       #
    # ------------------------------------------------------------------ #

    @app_commands.command(name="userinfo", description="Display info about a user")
    @app_commands.describe(member="The user to look up (defaults to you)")
    async def slash_userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.send_message(embed=self._userinfo_embed(member or interaction.user))

    @app_commands.command(name="serverinfo", description="Display info about this server")
    async def slash_serverinfo(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("This command only works in a server.", ephemeral=True)
        await interaction.response.send_message(embed=self._serverinfo_embed(interaction.guild))

    @app_commands.command(name="uptime", description="Show how long Kelor has been running")
    async def slash_uptime(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"I've been online for: `{self._uptime_string()}`")

    @app_commands.command(name="purge", description="Delete messages from this channel (requires Manage Messages)")
    @app_commands.describe(amount="Number of messages to delete")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int):
        if amount < 1:
            return await interaction.response.send_message("Please specify a positive number.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Management(bot))
