"""Unified provider abstraction for different LLM APIs."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio


class Provider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """Return list of supported model identifiers."""
        pass

    @abstractmethod
    async def query_model(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        """
        Query a model.

        Args:
            model: Model identifier (without provider prefix)
            messages: List of message dicts with 'role' and 'content'
            timeout: Request timeout in seconds

        Returns:
            Response dict with 'content' and optional 'reasoning_details', or None if failed
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and available."""
        pass


class OpenRouterProvider(Provider):
    """Provider for OpenRouter API."""

    def __init__(self):
        from .config import OPENROUTER_API_KEY
        self.api_key = OPENROUTER_API_KEY

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def supported_models(self) -> List[str]:
        # OpenRouter supports many models, these are just commonly used ones
        return [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/o1-preview",
            "openai/o1-mini",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "google/gemini-pro",
            "google/gemini-2.0-flash-exp",
            "meta-llama/llama-3.1-405b-instruct",
            "x-ai/grok-2",
        ]

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def query_model(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        from .openrouter import query_model
        return await query_model(model, messages, timeout)


class CopilotProvider(Provider):
    """Provider for GitHub Copilot API."""

    def __init__(self):
        from .copilot import copilot_service, COPILOT_MODELS
        from .config import COPILOT_MODELS as CONFIG_COPILOT_MODELS
        self.service = copilot_service
        # Use the imported list from config (already has copilot/ prefix)
        self._models = CONFIG_COPILOT_MODELS

    @property
    def name(self) -> str:
        return "copilot"

    @property
    def supported_models(self) -> List[str]:
        return self._models.copy()

    def is_available(self) -> bool:
        return self.service.is_authenticated()

    async def query_model(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        return await self.service.query_model(model, messages, timeout)


class ProviderRegistry:
    """Registry for managing multiple LLM providers."""

    def __init__(self):
        self._providers: Dict[str, Provider] = {}
        self._register_default_providers()

    def _register_default_providers(self):
        """Register the default providers."""
        self.register(OpenRouterProvider())
        self.register(CopilotProvider())

    def register(self, provider: Provider) -> None:
        """Register a provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> Optional[Provider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_available_providers(self) -> List[str]:
        """List all available (configured) provider names."""
        return [name for name, provider in self._providers.items() if provider.is_available()]

    def parse_model_identifier(self, model_id: str) -> tuple[str, str]:
        """
        Parse a model identifier into provider and model name.

        Model identifiers can be:
        - "copilot/gpt-4o" -> ("copilot", "gpt-4o")
        - "openrouter/openai/gpt-4o" -> ("openrouter", "openai/gpt-4o")
        - "openai/gpt-4o" (no prefix) -> ("openrouter", "openai/gpt-4o")  # default

        Args:
            model_id: The model identifier string

        Returns:
            Tuple of (provider_name, model_name)
        """
        parts = model_id.split("/", 1)

        if len(parts) == 1:
            # No provider prefix, assume it's a Copilot model name
            return ("copilot", model_id)

        prefix = parts[0]

        # Check if prefix is a known provider
        if prefix in self._providers:
            return (prefix, parts[1])

        # Otherwise, assume it's an OpenRouter model (e.g., "openai/gpt-4o")
        return ("openrouter", model_id)

    async def query_model(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        """
        Query a model using the appropriate provider.

        Args:
            model_id: Full model identifier (e.g., "copilot/gpt-4o" or "openai/gpt-4o")
            messages: List of message dicts with 'role' and 'content'
            timeout: Request timeout in seconds

        Returns:
            Response dict or None if failed
        """
        provider_name, model_name = self.parse_model_identifier(model_id)
        provider = self.get(provider_name)

        if provider is None:
            print(f"Unknown provider: {provider_name}")
            return None

        if not provider.is_available():
            print(f"Provider {provider_name} is not available/configured")
            return None

        return await provider.query_model(model_name, messages, timeout)

    async def query_models_parallel(
        self,
        model_ids: List[str],
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Query multiple models in parallel.

        Args:
            model_ids: List of full model identifiers
            messages: List of message dicts to send to each model
            timeout: Request timeout in seconds

        Returns:
            Dict mapping model identifier to response dict (or None if failed)
        """
        tasks = [self.query_model(model_id, messages, timeout) for model_id in model_ids]
        responses = await asyncio.gather(*tasks)
        return {model_id: response for model_id, response in zip(model_ids, responses)}

    async def query_models_sequential(
        self,
        model_ids: List[str],
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        delay: float = 1.0
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Query multiple models sequentially with a delay between each.

        Args:
            model_ids: List of full model identifiers
            messages: List of message dicts to send to each model
            timeout: Request timeout in seconds
            delay: Delay between queries in seconds

        Returns:
            Dict mapping model identifier to response dict (or None if failed)
        """
        responses = {}
        for i, model_id in enumerate(model_ids):
            if i > 0:
                await asyncio.sleep(delay)
            responses[model_id] = await self.query_model(model_id, messages, timeout)
        return responses


# Global singleton instance
provider_registry = ProviderRegistry()
