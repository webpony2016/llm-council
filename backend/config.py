"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv
from .copilot import COPILOT_MODELS as _IMPORTED_COPILOT_MODELS

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Copilot OAuth Configuration
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
COPILOT_API_URL = "https://api.githubcopilot.com/chat/completions"

# Copilot models - imported from copilot.py to maintain single source of truth
COPILOT_MODELS = _IMPORTED_COPILOT_MODELS

# OpenRouter models
OPENROUTER_MODELS = [
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.0-flash-exp",
    "x-ai/grok-2",
]

# Council members - list of model identifiers (supports both providers)
# Use "copilot/model-name" for Copilot models, "provider/model-name" for OpenRouter
COUNCIL_MODELS = [
    "copilot/gpt-4o",
    "copilot/claude-sonnet-4",
    "copilot/gemini-2.5-pro",
    "copilot/o4-mini",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "copilot/gpt-4o"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
