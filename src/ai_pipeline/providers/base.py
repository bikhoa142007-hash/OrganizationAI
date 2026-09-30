"""Provider interface. Providers only return advisory, untrusted JSON."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


class ProviderError(RuntimeError):
    """Sanitized provider failure; never contains credentials or raw payloads."""

    def __init__(self, message="Provider execution failed", *, code="PROVIDER_ERROR"):
        super().__init__(message)
        self.code = code


class ProviderTimeout(ProviderError):
    def __init__(self, message="Provider timed out"):
        super().__init__(message, code="PROVIDER_TIMEOUT")


class ProviderConfigurationError(ProviderError):
    def __init__(self, message="Provider is not configured", *, code="PROVIDER_NOT_CONFIGURED"):
        super().__init__(message, code=code)


class ProviderNonRetryableError(ProviderError):
    """A sanitized provider error that should fail without another request."""


@dataclass(frozen=True)
class ProviderAnalysis:
    """Untrusted model output plus transport metadata observed by the adapter."""

    output: Mapping[str, Any]
    raw_output_hash: str | None = None
    model_revision: str | None = None
    reported_model_id: str | None = None


class VisualModelProvider(ABC):
    output_kind = "EVALUATION"

    @abstractmethod
    def analyze_image(self, request: Any) -> Mapping[str, Any] | ProviderAnalysis:
        """Return untrusted structured output for the immutable request."""

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
