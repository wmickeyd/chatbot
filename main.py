import discord
from discord.ext import commands
import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from config import DISCORD_TOKEN
import database, models

# Initialize database tables
models.Base.metadata.create_all(bind=database.engine)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents, heartbeat_timeout=120.0)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')

    # Start background tasks
    bot.loop.create_task(update_health_check())
    bot.loop.create_task(cleanup_old_messages())

    # Check for Opus (voice support)
    try:
        if not discord.opus.is_loaded():
            discord.opus.load_opus('libopus.so.0')
        logger.info(f"Opus is loaded: {discord.opus.is_loaded()}")
    except Exception as e:
        logger.error(f"Failed to load Opus: {e}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    logger.info('Bot is ready and all cogs loaded.')

async def update_health_check():
    """Background task to update a health check file while the bot is connected and ready."""
    while not bot.is_closed():
        try:
            if bot.is_ready():
                with open("/tmp/health", "w") as f:
                    f.write(str(datetime.now(timezone.utc)))
        except Exception as e:
            logger.error(f"Error updating health check: {e}")
        await asyncio.sleep(30)

async def cleanup_old_messages():
    """Background task to delete chat messages older than 30 days every 24 hours."""
    while not bot.is_closed():
        try:
            if bot.is_ready():
                db = database.SessionLocal()
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
                deleted_count = db.query(models.ChatMessage).filter(models.ChatMessage.timestamp < cutoff_date).delete()
                if deleted_count > 0:
                    db.commit()
                    logger.info(f"Cleanup: Successfully deleted {deleted_count} messages older than 30 days.")
                db.close()
        except Exception as e:
            logger.error(f"Error in chat history cleanup: {e}")
        await asyncio.sleep(86400)

@bot.event
async def on_disconnect():
    logger.warning("Bot has disconnected from the Discord gateway. Attempting to reconnect...")

@bot.event
async def on_resumed():
    logger.info("Bot has successfully resumed its session.")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for commands."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: `{error.param.name}`. Use `!commands` to see usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        logger.error(f"Command Error in !{ctx.command}: {error}")
        await ctx.send(f"An error occurred while running the command: {error}")

async def main():
    async with bot:
        # Load extensions
        await bot.load_extension('cogs.utility')
        await bot.load_extension('cogs.tracking')
        await bot.load_extension('cogs.music')
        await bot.load_extension('cogs.llm')
        await bot.load_extension('cogs.management')
        
        if not DISCORD_TOKEN:
            logger.error("No DISCORD_TOKEN found in environment variables!")
        else:
            await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
