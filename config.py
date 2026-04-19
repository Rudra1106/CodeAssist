import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter config (free models)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Ollama config (local models)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Model assignments per agent role
MODELS = {
    "planner":      {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
    "coder":        {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
    "critic":       {"provider": "ollama",     "model": "qwen2.5-coder:3b"},
    "teacher":      {"provider": "ollama",     "model": "deepseek-r1:1.5b"},
    "orchestrator": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
}

# Fallbacks if primary fails
FALLBACKS = {
    "openrouter": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
    "ollama":     {"provider": "ollama", "model": "qwen2.5-coder:3b"},
}