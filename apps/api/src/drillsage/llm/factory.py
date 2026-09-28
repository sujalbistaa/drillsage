"""Choose the model provider from settings (`DRILLSAGE_LLM_PROVIDER`)."""

from drillsage.core.config import Settings
from drillsage.llm.gemini import GeminiProvider
from drillsage.llm.providers import AnthropicProvider, Provider


def make_provider(settings: Settings) -> Provider:
    if settings.llm_provider == "gemini":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        return GeminiProvider(
            key,
            fallback_models=settings.llm_fallback_models,
            min_interval_s=settings.llm_min_interval_s,
        )
    return AnthropicProvider(refusal_fallback=settings.llm_refusal_fallback)
