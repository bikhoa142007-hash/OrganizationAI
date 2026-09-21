"""Opt-in provider adapters.

The Sprint 1 runtime remains local by default. These adapters never transmit
plan/media data unless an explicitly configured host supplies an approved backend.
"""

import os

from .base import ProviderError, VisualModelProvider


class OpenAIProvider(VisualModelProvider):
    def __init__(self, *, api_key=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_version = model or os.getenv("OPENAI_MODEL")
        if not self.api_key or not self.model_version:
            raise ProviderError("OpenAI provider is not configured")

    def health_check(self):
        return bool(self.api_key and self.model_version)

    def get_model_metadata(self):
        return {"provider": "LOCAL_VLM", "model_version": self.model_version}

    def analyze_image(self, request):
        raise ProviderError("External provider execution is disabled without approved transport")


class LocalVLMProvider(VisualModelProvider):
    """Environment-configured local adapter with an injected inference callable."""

    def __init__(self, *, model=None, analyzer=None):
        self.model_version = model or os.getenv("LOCAL_VLM_MODEL")
        self._analyzer = analyzer
        if not self.model_version:
            raise ProviderError("Local VLM provider is not configured")

    def health_check(self):
        return self._analyzer is not None

    def get_model_metadata(self):
        return {"provider": "LOCAL_VLM", "model_version": self.model_version}

    def analyze_image(self, request):
        if self._analyzer is None:
            raise ProviderError("Local VLM inference backend is unavailable")
        return self._analyzer(request)
