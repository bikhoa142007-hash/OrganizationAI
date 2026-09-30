"""Runtime composition for the authenticated workflow's existing AI pipeline."""
import os

from src.ai_pipeline.providers.base import ProviderError, VisualModelProvider
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.ai_pipeline.providers.openai_provider import LocalVLMProvider
from src.backend.application.auth_workflow import ALLOWED_MEDIA, MAX_ATTACHMENT_BYTES
from src.backend.domain.policy import (
    ApprovalConfiguration,
    Criterion,
    MANDATORY_FIELDS,
    PolicySnapshot,
)


MOCK_SCENARIOS = frozenset({"pass", "review", "timeout", "error", "malformed", "unknown_media"})


def create_authenticated_provider(app_env: str) -> VisualModelProvider:
    """Select a provider explicitly; local inference failures never switch to Mock."""
    provider_name = os.getenv("AUTH_WORKFLOW_AI_PROVIDER", "LOCAL_VLM").strip().upper()
    if provider_name == "LOCAL_VLM":
        return LocalVLMProvider()
    if provider_name == "MOCK_VLM":
        if app_env != "demo":
            raise ValueError("MOCK_VLM is available only when APP_ENV=demo.")
        scenario = os.getenv("AUTH_WORKFLOW_MOCK_SCENARIO", "pass").strip().lower()
        if scenario not in MOCK_SCENARIOS:
            raise ValueError("Unsupported authenticated workflow mock scenario.")
        version = os.getenv("AUTH_WORKFLOW_MOCK_MODEL_VERSION", "mock-1").strip()
        if not version:
            raise ValueError("AUTH_WORKFLOW_MOCK_MODEL_VERSION cannot be blank.")
        return MockVLMProvider(scenario, model_version=version)
    raise ValueError("AUTH_WORKFLOW_AI_PROVIDER must be LOCAL_VLM or MOCK_VLM.")


def unconfigured_approval_configuration(provider: VisualModelProvider) -> ApprovalConfiguration:
    """Fail-closed policy snapshot for deployments without approved auth policy data.

    The existing demo policy, budget and authority are intentionally not copied
    into authenticated-account decisions. A real configuration must be injected
    by an approved configuration store before auto-approval can become eligible.
    """
    metadata = provider.get_model_metadata()
    model_version = metadata.get("model_version")
    known_models = (model_version,) if isinstance(model_version, str) and model_version.strip() else ()
    policy = PolicySnapshot(
        snapshot_id="AUTH-WORKFLOW-POLICY-UNCONFIGURED",
        policy_version="AUTH-WORKFLOW-POLICY-UNCONFIGURED-1",
        auto_approval_policy_enabled=False,
        mandatory_fields=MANDATORY_FIELDS,
        criteria=(Criterion("strategy", 100),),
        known_model_versions=known_models,
        allowed_media_types=tuple(ALLOWED_MEDIA),
        max_attachment_bytes=MAX_ATTACHMENT_BYTES,
    )
    return ApprovalConfiguration(policy=policy, budgets=(), authority=None)


def provider_metadata(provider: VisualModelProvider) -> tuple[str, str | None, str | None]:
    try:
        metadata = provider.get_model_metadata()
    except ProviderError:
        metadata = {}
    provider_name = metadata.get("provider")
    if provider_name not in {"LOCAL_VLM", "MOCK_VLM"}:
        provider_name = "LOCAL_VLM"
    model_version = metadata.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        model_version = None
    model_id = metadata.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        model_id = None
    return provider_name, model_version, model_id
