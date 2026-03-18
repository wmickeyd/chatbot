import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
import os
from gtts import gTTS

logger = logging.getLogger(__name__)

# yt-dlp setup
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}
ffmpeg_options = {
    'options': '-vn'
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def join(self, ctx):
        """Joins a voice channel."""
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            try:
                await asyncio.wait_for(channel.connect(), timeout=10.0)
                logger.info(f"Joined voice channel: {channel}")
            except asyncio.TimeoutError:
                await ctx.send("Connection to voice channel timed out.")
            except Exception as e:
                await ctx.send(f"Failed to join voice channel: {e}")
        else:
            await ctx.send("You need to be in a voice channel first!")

    @commands.command()
    async def leave(self, ctx):
        """Leaves a voice channel."""
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            logger.info("Left voice channel.")
        else:
            await ctx.send("I'm not in a voice channel!")

    @commands.command()
    async def play(self, ctx, *, url):
        """Plays audio from a URL (YouTube, SoundCloud, Spotify)."""
        async with ctx.typing():
            if not ctx.voice_client:
                if ctx.author.voice:
                    await ctx.author.voice.channel.connect()
                else:
                    return await ctx.send("You are not connected to a voice channel.")
            
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()

            try:
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                ctx.voice_client.play(player, after=lambda e: logger.error(f'Player error: {e}') if e else None)
                await ctx.send(f'**Now playing:** {player.title}')
            except Exception as e:
                logger.error(f"Error in play command: {e}")
                await ctx.send(f"An error occurred while trying to play: {e}")

    @commands.command()
    async def pause(self, ctx):
        """Pauses the currently playing audio."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Audio paused.")
        else:
            await ctx.send("No audio is currently playing.")

    @commands.command()
    async def resume(self, ctx):
        """Resumes the currently paused audio."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Audio resumed.")
        else:
            await ctx.send("Audio is not paused.")

    @commands.command()
    async def stop(self, ctx):
        """Stops the audio."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Audio stopped.")
        else:
            await ctx.send("No audio is currently playing.")

    @commands.command()
    async def speak(self, ctx, *, text=None):
        """TTS in voice channel."""
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("You need to be in a voice channel first!")
        if not text:
            return await ctx.send("Please provide some text for me to say.")
        async with ctx.typing():
            tts = gTTS(text=text, lang='en')
            filename = f"speech_{ctx.message.id}.mp3"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, tts.save, filename)
            source = discord.FFmpegPCMAudio(filename)
            ctx.voice_client.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)

async def setup(bot):
    await bot.add_cog(Music(bot))
