import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env at import time — this must happen before any client is created
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_client(provider: str) -> OpenAI:
    """Single source of truth for all LLM clients in the project."""
    if provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY is empty. "
                "Check your .env file is in the project root."
            )
        return OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    elif provider == "ollama":
        return OpenAI(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )
    raise ValueError(f"Unknown provider: {provider}")