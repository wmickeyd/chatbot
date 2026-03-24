import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="deploy/base/.env")
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Agent Orchestrator
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://agent-orchestrator.ai-services.svc.cluster.local:8002/v1/chat')

# Downstream APIs (Keep these if cogs still need them directly, but LLM will use Orchestrator)
SCRAPER_BASE_URL = os.getenv('SCRAPER_BASE_URL', 'http://dev-webscraper.webscraper-dev.svc.cluster.local')
UTILITY_BASE_URL = os.getenv('UTILITY_BASE_URL', 'http://dev-utility-api.utility-dev.svc.cluster.local')
