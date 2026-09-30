"""Secret-safe, opt-in configuration loading for independent text agents."""
import json
import os
from dataclasses import replace

from src.ai_pipeline.task_providers import OpenAICompatibleTaskProvider, TaskModelSettings
from src.backend.domain.policy import MediaCompliancePolicy, StrategyRubric


def configured_task_components(environ=None):
    """Load task models and optional approved policy snapshots from the environment."""
    environ = os.environ if environ is None else environ
    media_settings = TaskModelSettings.from_environment("MEDIA_COMPLIANCE", environ)
    strategy_settings = TaskModelSettings.from_environment("STRATEGY_EVALUATION", environ)
    media_policy, media_error = _load_json_contract(
        environ.get("AUTH_WORKFLOW_MEDIA_POLICY_JSON"), MediaCompliancePolicy
    )
    strategy_rubric, strategy_error = _load_json_contract(
        environ.get("AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON"), StrategyRubric
    )
    if media_error:
        media_settings = replace(media_settings, configuration_error=media_error)
    if strategy_error:
        strategy_settings = replace(strategy_settings, configuration_error=strategy_error)
    return (
        OpenAICompatibleTaskProvider(media_settings),
        OpenAICompatibleTaskProvider(strategy_settings),
        media_policy,
        strategy_rubric,
    )


def _load_json_contract(raw, contract):
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    try:
        return contract.from_dict(json.loads(raw)), None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, "INVALID_POLICY_CONFIGURATION"
