import discord
from discord.ext import commands
import os

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True

# Define bot prefix
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.content.lower() == 'hello':
        await message.channel.send(f'Hi {message.author.name}!')
    
    await bot.process_commands(message)

bot.run(os.getenv('DISCORD_TOKEN'))