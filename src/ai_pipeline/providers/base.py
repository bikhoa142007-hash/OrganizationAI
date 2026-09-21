"""Provider interface. Providers only return advisory, untrusted JSON."""

from abc import ABC, abstractmethod
from typing import Any, Mapping


class ProviderError(RuntimeError):
    """Sanitized provider failure; never contains credentials or raw payloads."""


class ProviderTimeout(ProviderError):
    pass


class VisualModelProvider(ABC):
    @abstractmethod
    def analyze_image(self, request: Any) -> Mapping[str, Any]:
        """Return untrusted structured evidence for the immutable request."""

    def analyzeImage(self, request: Any) -> Mapping[str, Any]:  # compatibility alias
        return self.analyze_image(request)

    @abstractmethod
    def health_check(self) -> bool:
        pass

    def healthCheck(self) -> bool:  # compatibility alias
        return self.health_check()

    @abstractmethod
    def get_model_metadata(self) -> Mapping[str, str]:
        pass

    def getModelMetadata(self) -> Mapping[str, str]:  # compatibility alias
        return self.get_model_metadata()
