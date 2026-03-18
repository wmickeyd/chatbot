import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path="deploy/base/.env")

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'gemma3n:e4b')
SCRAPER_BASE_URL = os.getenv('SCRAPER_BASE_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local')
UTILITY_BASE_URL = os.getenv('UTILITY_BASE_URL', 'http://dev-utility-api.utility-dev.svc.cluster.local')

SCRAPER_URL = f"{SCRAPER_BASE_URL}/read"
TRACK_URL = f"{SCRAPER_BASE_URL}/track"
SCRAPE_URL = f"{SCRAPER_BASE_URL}/scrape"
TRACKED_URL = f"{SCRAPER_BASE_URL}/tracked"

FINANCE_URL = f"{UTILITY_BASE_URL}/finance"
SEARCH_URL = f"{UTILITY_BASE_URL}/search"
IMAGE_SEARCH_URL = f"{UTILITY_BASE_URL}/image_search"
WEATHER_URL = f"{UTILITY_BASE_URL}/weather"
NEWS_URL = f"{UTILITY_BASE_URL}/news"
REDDIT_URL = f"{UTILITY_BASE_URL}/reddit"
