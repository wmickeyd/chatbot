import discord
from discord.ext import commands
import time
from datetime import datetime, timezone

class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

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
        member = member or ctx.author
        color = member.color if isinstance(member, discord.Member) else discord.Color.blurple()
        embed = discord.Embed(title=f"User Info: {member.name}", color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        if isinstance(member, discord.Member) and member.joined_at:
            embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Joined Discord", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        if isinstance(member, discord.Member) and ctx.guild:
            roles = [role.mention for role in member.roles if role != ctx.guild.default_role]
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def serverinfo(self, ctx):
        """Displays information about the server."""
        guild = ctx.guild
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.purple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Channels", value=f"{len(guild.text_channels)} Text / {len(guild.voice_channels)} Voice", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running."""
        uptime_seconds = int(time.time() - self.start_time)
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        await ctx.send(f"I've been online for: `{days}d {hours}h {minutes}m {seconds}s`")

async def setup(bot):
    await bot.add_cog(Management(bot))
