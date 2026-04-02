# Kelor — Discord Chatbot

The user-facing Discord bot for the Kelor AI ecosystem. Acts as a thin client — it handles all Discord interaction and streams responses from the `agent-orchestrator`, keeping AI logic and tool execution out of this service entirely.

## Architecture

```
Discord User
    │
    ▼
Kelor (this service)
    │  SSE stream
    ▼
agent-orchestrator ──► Ollama (LLM)
                   ──► utility-api (search, weather, finance, news...)
                   ──► webscraper (web content, LEGO tracking)
```

When a user mentions `@Kelor` or sends a DM, the bot forwards the prompt to the orchestrator and streams the response back to Discord in real time. Status indicators only appear when a tool is actively being called or an image is being analysed — simple responses appear directly with no preamble.

## Features

### AI Chat
- Mention `@Kelor` or DM the bot to start a conversation
- Responses stream token-by-token as the LLM generates them
- Shows `🔧 using tools...` when the agent calls an external tool
- Shows `🔍 analysing image...` when an uploaded image is being described
- Automatically retries the orchestrator connection with exponential backoff on transient failures

### Image Understanding
Upload any image alongside your message and Kelor will describe it using the `moondream` vision model before responding. Works with JPG, PNG, GIF, and WebP.

### Commands

All commands are available as both prefix (`!`) and slash (`/`) commands. Slash commands have autocomplete and inline descriptions in the Discord UI.

| Command | Description |
|---|---|
| `!weather <location>` | Current weather via Kelor |
| `!stock <symbol>` | Stock or crypto price (e.g. `AAPL`, `BTC-USD`) |
| `!define <word>` | Dictionary definition |
| `!youtube <url>` | Summarise a YouTube video |
| `!wiki <query>` | Wikipedia summary |
| `!poll "<question>" [options...]` | Create a reaction poll (up to 10 options) |
| `!roll [NdN]` | Roll dice (default `1d20`) |
| `!track <url>` | Track a LEGO set price |
| `!tracked` | List your tracked LEGO sets with removal UI |
| `!set <key> <value>` | Update your profile (`model`, `unit`, `lang`) |
| `!profile` | View your current settings |
| `!userinfo [@user]` | Discord user details |
| `!serverinfo` | Server details |
| `!uptime` | How long the bot has been running |
| `!purge <n>` | Delete messages (requires Manage Messages) |
| `!ping` | Latency check |

### Music
Voice channel music playback via `yt-dlp`. Streams audio from YouTube and other supported sources directly into a voice channel.

### User Profiles
Each user can customise their experience:
- `model` — which Ollama model to use (e.g. `gemma3:1b`)
- `unit` — temperature unit (`Celsius` or `Fahrenheit`)
- `lang` — response language (e.g. `en`, `es`, `fr`, `de`)

## Cog Structure

| Cog | Responsibility |
|---|---|
| `cogs/llm.py` | SSE client, streaming, retry logic, `@Kelor` mention handler |
| `cogs/utility.py` | General commands + slash commands (weather, stock, wiki, etc.) |
| `cogs/tracking.py` | LEGO price tracking UI with interactive dropdowns |
| `cogs/management.py` | Server management commands (purge, userinfo, serverinfo, uptime) |
| `cogs/music.py` | Voice channel music playback |

## Tech Stack

- **Python 3.12+**
- **discord.py** with app_commands (slash command support)
- **aiohttp** — async SSE client for orchestrator communication
- **yt-dlp** + **PyNaCl** — music streaming
- **SQLAlchemy + SQLite** — local chat history and user profile cache
- **wikipediaapi** — Wikipedia lookups

## Setup

### Environment Variables

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your Discord bot token |
| `ORCHESTRATOR_BASE_URL` | Base URL of the agent-orchestrator service |
| `SCRAPER_BASE_URL` | Base URL of the webscraper service |
| `UTILITY_BASE_URL` | Base URL of the utility-api service |

### Running Locally

```bash
pip install -r requirements.txt
python main.py
```

### Kubernetes

Deployed to the `chatbot-dev` namespace via ArgoCD. Manifests are in the `gitops` repository.

```bash
kubectl apply -k gitops/chatbot/overlays/dev
```

### Slash Command Registration

On first startup, the bot syncs slash commands with Discord automatically via `bot.tree.sync()` in `on_ready`. Ensure the bot is invited with the `applications.commands` OAuth2 scope.

## Deployment Notes

- The container image is built for `linux/arm64` (M1 Mac Mini cluster)
- Pushed to `ghcr.io/wmickeyd/chatbot` on every push to `main`
- ArgoCD detects the manifest update and redeploys automatically
