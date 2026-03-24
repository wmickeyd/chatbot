# Discord Thin Client (Chatbot)

A streamlined Discord bot built with `discord.py`. This service acts as the **User Interface** (Thin Client) for the ecosystem, delegating heavy logic and AI orchestration to the `agent-orchestrator`.

## Features

- **AI Chat (Agentic)**: Connects to the **Agent Orchestrator** via SSE to provide real-time, tool-aware AI conversations.
- **Music Player**: High-quality music streaming from various sources using `yt-dlp` and voice support.
- **Product Tracking**: Manage and view LEGO set price tracking (powered by `webscraper`).
- **Utility Commands**: Quick access to specialized bot commands (`!wiki`, `!calc`, `!profile`).
- **Real-time Feedback**: Displays live agent status (e.g., *thinking...*, *calling tool...*) within Discord.

## Architecture: Thin Client

This bot no longer runs LLM logic or tool execution locally. Instead, it:
1.  Captures user messages and attachments.
2.  Proxies the request to the `agent-orchestrator`.
3.  Streams the response chunks and status updates back to the Discord channel.

## Tech Stack

- **Language**: Python 3.14+
- **Library**: `discord.py`
- **Streaming**: `aiohttp` (SSE client)
- **Dependencies**: `yt-dlp`, `gTTS`, `PyNaCl` (for voice)

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Create a `.env` file or set the following environment variables:
   - `DISCORD_TOKEN`: Your Discord bot token.
   - `ORCHESTRATOR_URL`: URL to the `agent-orchestrator` chat endpoint.

3. **Run the Bot**:
   ```bash
   python main.py
   ```

## Development

The bot is organized into **Cogs**:
- `cogs/llm.py`: Thin client logic for communicating with the Orchestrator.
- `cogs/music.py`: Voice channel and music playback logic.
- `cogs/tracking.py`: UI for managing product tracking.
- `cogs/utility.py`: General utility and profile commands.
