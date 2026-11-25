"""Factory for creating configured AI providers."""

from app.config import settings
from app.ai.base import BaseAIProvider
from app.ai.grok_provider import GrokAIProvider


class AIProviderFactory:
    """Factory to instantiate the configured clinical AI provider."""

    @staticmethod
    def get_provider() -> BaseAIProvider:
        provider_name = settings.AI_PROVIDER.lower().strip()
        if provider_name == "grok":
            return GrokAIProvider(
                api_key=settings.AI_API_KEY,
                model=settings.AI_MODEL,
                base_url=settings.AI_BASE_URL,
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
        # Future providers (e.g., Gemini, OpenAI, Claude) will be plugged in here
        raise ValueError(f"Unsupported AI Provider: {settings.AI_PROVIDER}")
