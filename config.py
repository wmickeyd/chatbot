import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="deploy/base/.env")
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Agent Orchestrator
ORCHESTRATOR_BASE_URL = os.getenv('ORCHESTRATOR_BASE_URL', 'http://dev-agent-orchestrator.ai-services.svc.cluster.local:8002')
ORCHESTRATOR_URL = f"{ORCHESTRATOR_BASE_URL}/v1/chat"

# Downstream APIs (Keep these if cogs still need them directly, but LLM will use Orchestrator)
SCRAPER_BASE_URL = os.getenv('SCRAPER_BASE_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local:8000')
UTILITY_BASE_URL = os.getenv('UTILITY_BASE_URL', 'http://dev-utility-api.utility-dev.svc.cluster.local:8001')

SCRAPER_URL = f"{SCRAPER_BASE_URL}/read"
TRACK_URL = f"{SCRAPER_BASE_URL}/track"
SCRAPE_URL = f"{SCRAPER_BASE_URL}/scrape"
TRACKED_URL = f"{SCRAPER_BASE_URL}/tracked"

FINANCE_URL = f"{UTILITY_BASE_URL}/finance"
WEATHER_URL = f"{UTILITY_BASE_URL}/weather"
NEWS_URL = f"{UTILITY_BASE_URL}/news"
DEFINE_URL = f"{UTILITY_BASE_URL}/define"
