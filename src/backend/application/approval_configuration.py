from __future__ import annotations

from dataclasses import dataclass, replace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Any, Literal, Mapping
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.application.workflow import ApplicationError
from src.backend.db.models.approval_configuration import (
    AuthWorkflowAutoRejectPolicySignoff,
    AuthWorkflowApprovalPolicySignoff,
    AuthWorkflowConfigurationLock,
    AuthWorkflowConfigurationHead,
    AuthWorkflowConfigurationRevision,
    AuthWorkflowRoundConfigurationSnapshot,
)
from src.backend.db.models.employee import AdminAuditEvent
from src.backend.db.models import EmployeeProfile, Role, User, UserRole
from src.shared.validation import canonical_hash, json_value

CONFIGURATION_KINDS = (
    "approval_policy",
    "budget",
    "media_policy",
    "strategy_rubric",
    "authority",
    "checker_assignment",
    "auto_reject_policy",
)
ConfigurationStatus = Literal["UNCONFIGURED", "DISABLED", "EFFECTIVE", "SCHEDULED", "SUPERSEDED"]
_AMOUNT_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,23})\Z")
_STRATEGY_CRITERIA_ORDER = (
    "objective", "audience", "channel", "timeline", "kpi", "budget_efficiency", "risk_control",
)
_STRATEGY_CRITERIA = frozenset(_STRATEGY_CRITERIA_ORDER)


class ConfigurationValidationError(ValueError):
    """Raised when an administrator submits a value outside its typed contract."""


@dataclass(frozen=True)
class BudgetDecision:
    result: Literal["PASS", "HUMAN_REVIEW_REQUIRED"]
    status: Literal["CONFIGURED", "UNCONFIGURED", "DISABLED", "AMBIGUOUS", "INVALID_INPUT"]
    currency: str | None
    amount_minor_units: str | None
    limit_minor_units: str | None
    configuration_revision_id: str | None
    configuration_revision: int | None
    configuration_hash: str | None


@dataclass(frozen=True)
class ConfigurationResolution:
    kind: str
    status: Literal["UNCONFIGURED", "DISABLED", "EFFECTIVE"]
    revision_id: str | None
    revision: int | None
    effective_at: datetime | None
    configuration_hash: str | None
    value: dict[str, Any] | None
    signoff: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "revision_id": self.revision_id,
            "revision": self.revision,
            "effective_at": _iso_utc(self.effective_at) if self.effective_at else None,
            "configuration_hash": self.configuration_hash,
            "value": deepcopy(self.value),
            "signoff": deepcopy(self.signoff),
        }


@dataclass(frozen=True)
class RoundConfigurationSnapshot:
    plan_id: UUID
    plan_version: int
    approval_round: int
    effective_at: datetime
    configurations: dict[str, dict[str, Any]]
    checker_assignment: dict[str, Any]
    snapshot_hash: str
    snapshot_id: UUID | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
            "plan_id": str(self.plan_id),
            "plan_version": self.plan_version,
            "approval_round": self.approval_round,
            "effective_at": _iso_utc(self.effective_at),
            "configurations": deepcopy(self.configurations),
            "checker_assignment": deepcopy(self.checker_assignment),
            "snapshot_hash": self.snapshot_hash,
        }


def _utc_from_storage(value: datetime) -> datetime:
    # SQLite drops timezone metadata even for timezone=True columns. Those
    # stored naive values are UTC by contract; aware values are normalized.
    stored_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return stored_value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    normalized = _utc_from_storage(value)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ConfigurationValidationError(f"{field_name} must be a timezone-aware UTC timestamp.")
    return value.astimezone(timezone.utc)


def _object(value: Any, field_name: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        expected = ", ".join(sorted(keys))
        raise ConfigurationValidationError(f"{field_name} must contain exactly: {expected}.")
    return dict(value)


def _nonblank(value: Any, field_name: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        raise ConfigurationValidationError(f"{field_name} must be non-blank, trimmed text up to {maximum} characters.")
    return value


def _finite_number(value: Any, field_name: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float):
        raise ConfigurationValidationError(f"{field_name} must be a number from {minimum} through {maximum}.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ConfigurationValidationError(f"{field_name} must be a number from {minimum} through {maximum}.") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ConfigurationValidationError(f"{field_name} must be a number from {minimum} through {maximum}.")
    return number


def _uuid_text(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ConfigurationValidationError(f"{field_name} must be a user ID.")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ConfigurationValidationError(f"{field_name} must be a valid user ID.") from exc


def validate_configuration_value(kind: str, value: Any) -> dict[str, Any]:
    """Validate and normalize the closed value schema for a configuration kind."""
    if kind not in CONFIGURATION_KINDS:
        raise ConfigurationValidationError("Unknown configuration kind.")

    if kind == "approval_policy":
        raw = _object(value, kind, {
            "enabled", "media_confidence_threshold", "feasibility_score_threshold_exclusive",
            "feasibility_confidence_threshold",
        })
        if type(raw["enabled"]) is not bool:
            raise ConfigurationValidationError("enabled must be a boolean.")
        if raw["enabled"]:
            raise ConfigurationValidationError("Auto-approval cannot be enabled before PO sign-off.")
        score_threshold = raw["feasibility_score_threshold_exclusive"]
        if type(score_threshold) is not int or not 0 <= score_threshold < 100:
            raise ConfigurationValidationError("The exclusive feasibility threshold must be an integer from 0 to 99.")
        return {
            "enabled": False,
            "media_confidence_threshold": _finite_number(raw["media_confidence_threshold"], "media_confidence_threshold", 0, 1),
            "feasibility_score_threshold_exclusive": score_threshold,
            "feasibility_confidence_threshold": _finite_number(raw["feasibility_confidence_threshold"], "feasibility_confidence_threshold", 0, 1),
        }

    if kind == "budget":
        raw = _object(value, kind, {"currency", "limits"})
        if raw["currency"] != "VND":
            raise ConfigurationValidationError("Budget configuration supports VND only.")
        if not isinstance(raw["limits"], list):
            raise ConfigurationValidationError("limits must be an array.")
        limits: list[dict[str, Any]] = []
        departments: set[str] = set()
        for index, item in enumerate(raw["limits"]):
            entry = _object(item, f"limits[{index}]", {"department", "limit_minor_units", "active"})
            department = _nonblank(entry["department"], f"limits[{index}].department", 120)
            amount = entry["limit_minor_units"]
            if not isinstance(amount, str) or not _AMOUNT_PATTERN.fullmatch(amount):
                raise ConfigurationValidationError(f"limits[{index}].limit_minor_units must be a non-negative VND integer string.")
            if type(entry["active"]) is not bool:
                raise ConfigurationValidationError(f"limits[{index}].active must be a boolean.")
            if department in departments:
                raise ConfigurationValidationError(f"Budget department {department} has overlapping limits.")
            departments.add(department)
            limits.append({"department": department, "limit_minor_units": amount, "active": entry["active"]})
        return {"currency": "VND", "limits": limits}

    if kind == "strategy_rubric":
        raw = _object(value, kind, {"rubric_id", "rubric_version", "status", "criteria"})
        if not isinstance(raw["status"], str) or raw["status"] not in {"ACTIVE", "DISABLED"}:
            raise ConfigurationValidationError("Rubric status must be ACTIVE or DISABLED.")
        rubric_id = _nonblank(raw["rubric_id"], "rubric_id")
        rubric_version = _nonblank(raw["rubric_version"], "rubric_version")
        if not isinstance(raw["criteria"], list):
            raise ConfigurationValidationError("criteria must be an array.")
        criteria: list[dict[str, Any]] = []
        seen: set[str] = set()
        total_weight = 0
        for index, item in enumerate(raw["criteria"]):
            entry = _object(item, f"criteria[{index}]", {"criterion_id", "label", "weight"})
            criterion_id = _nonblank(entry["criterion_id"], f"criteria[{index}].criterion_id", 80)
            if criterion_id not in _STRATEGY_CRITERIA or criterion_id in seen:
                raise ConfigurationValidationError("Rubric must contain each supported criterion at most once.")
            if type(entry["weight"]) is not int or not 1 <= entry["weight"] <= 100:
                raise ConfigurationValidationError(f"criteria[{index}].weight must be an integer from 1 to 100.")
            seen.add(criterion_id)
            total_weight += entry["weight"]
            criteria.append({
                "criterion_id": criterion_id,
                "label": _nonblank(entry["label"], f"criteria[{index}].label", 160),
                "weight": entry["weight"],
            })
        if seen != _STRATEGY_CRITERIA or total_weight != 100:
            raise ConfigurationValidationError("Rubric must contain all seven strategy criteria with weights totaling 100.")
        criteria.sort(key=lambda item: _STRATEGY_CRITERIA_ORDER.index(item["criterion_id"]))
        return {"rubric_id": rubric_id, "rubric_version": rubric_version, "status": raw["status"], "criteria": criteria}

    if kind == "checker_assignment":
        raw = _object(value, kind, {"maker_may_select_other", "defaults"})
        if type(raw["maker_may_select_other"]) is not bool:
            raise ConfigurationValidationError("maker_may_select_other must be a boolean.")
        if not isinstance(raw["defaults"], list):
            raise ConfigurationValidationError("defaults must be an array.")
        defaults: list[dict[str, str]] = []
        departments: set[str] = set()
        for index, item in enumerate(raw["defaults"]):
            entry = _object(item, f"defaults[{index}]", {"department", "checker_id"})
            department = _nonblank(entry["department"], f"defaults[{index}].department", 120)
            if department in departments:
                raise ConfigurationValidationError(f"Department {department} has more than one default Checker.")
            departments.add(department)
            defaults.append({"department": department, "checker_id": _uuid_text(entry["checker_id"], f"defaults[{index}].checker_id") or ""})
        return {"maker_may_select_other": raw["maker_may_select_other"], "defaults": defaults}

    if kind == "authority":
        raw = _object(value, kind, {
            "currency", "auto_limit_minor_units", "allowed_departments", "checker_id",
            "policy_owner_id", "budget_authority_id", "active",
        })
        if raw["currency"] != "VND":
            raise ConfigurationValidationError("Authority configuration supports VND only.")
        amount = raw["auto_limit_minor_units"]
        if not isinstance(amount, str) or not _AMOUNT_PATTERN.fullmatch(amount):
            raise ConfigurationValidationError("auto_limit_minor_units must be a non-negative VND integer string.")
        if not isinstance(raw["allowed_departments"], list):
            raise ConfigurationValidationError("allowed_departments must be an array.")
        departments = [_nonblank(item, "allowed_departments item", 120) for item in raw["allowed_departments"]]
        if not departments or len(departments) != len(set(departments)):
            raise ConfigurationValidationError("allowed_departments must be non-empty and unique.")
        if type(raw["active"]) is not bool:
            raise ConfigurationValidationError("active must be a boolean.")
        return {
            "currency": "VND",
            "auto_limit_minor_units": amount,
            "allowed_departments": departments,
            "checker_id": _uuid_text(raw["checker_id"], "checker_id", nullable=True),
            "policy_owner_id": _uuid_text(raw["policy_owner_id"], "policy_owner_id", nullable=True),
            "budget_authority_id": _uuid_text(raw["budget_authority_id"], "budget_authority_id", nullable=True),
            "active": raw["active"],
        }

    if kind == "media_policy":
        from src.backend.domain.policy import MediaCompliancePolicy
        try:
            policy = MediaCompliancePolicy.from_dict(value)
        except (TypeError, ValueError, KeyError) as exc:
            raise ConfigurationValidationError("Media policy does not match the supported schema.") from exc
        return policy.to_dict()

    if kind == "auto_reject_policy":
        from src.backend.domain.policy import AutoRejectPolicy
        raw = _object(value, kind, {
            "configuration_id", "policy_version", "revision", "enabled", "environment",
            "scope_departments", "scope_channels", "rules",
        })
        if raw["enabled"] is not False:
            raise ConfigurationValidationError(
                "Auto-reject policy revisions must remain disabled until authenticated Policy Owner sign-off."
            )
        if not isinstance(raw["scope_departments"], list) or not isinstance(raw["scope_channels"], list):
            raise ConfigurationValidationError("Auto-reject policy requires explicit department and channel scope.")
        if not isinstance(raw["rules"], list):
            raise ConfigurationValidationError("Auto-reject policy rules must be an array.")
        try:
            policy = AutoRejectPolicy.from_dict({
                **raw,
                "configuration_hash": None,
                "signoff_source": None,
                "signed_by": None,
                "signed_at": None,
            })
        except (TypeError, ValueError, KeyError) as exc:
            raise ConfigurationValidationError("Auto-reject policy does not match the supported schema.") from exc
        return {
            key: item for key, item in policy.to_dict().items()
            if key in {"configuration_id", "policy_version", "revision", "enabled", "environment",
                       "scope_departments", "scope_channels", "rules"}
        }

    raise ConfigurationValidationError("Unknown configuration kind.")


def _validate_signed_approval_policy_value(
    value: Any,
    signoff: Mapping[str, Any] | None,
    *,
    revision_id: str,
    configuration_hash: str,
) -> dict[str, Any]:
    """Validate the ordinary policy schema and bind enabled=true to a persisted PO sign-off."""
    if not isinstance(value, Mapping) or value.get("enabled") is not True:
        return validate_configuration_value("approval_policy", value)
    disabled_value = dict(value)
    disabled_value["enabled"] = False
    normalized = validate_configuration_value("approval_policy", disabled_value)
    enabled_value = {**normalized, "enabled": True}
    approved_revisions = signoff.get("configuration_revisions") if isinstance(signoff, Mapping) else None
    candidate_revision = (
        approved_revisions.get("approval_policy_candidate")
        if isinstance(approved_revisions, Mapping) else None
    )
    require_signoff = (
        isinstance(signoff, Mapping)
        and signoff.get("approval_policy_revision_id") == revision_id
        and signoff.get("approved_configuration_hash") == configuration_hash
        and signoff.get("policy_owner_id")
        and signoff.get("candidate_revision_id")
        and isinstance(candidate_revision, Mapping)
        and candidate_revision.get("revision_id") == signoff.get("candidate_revision_id")
        and isinstance(candidate_revision.get("configuration_hash"), str)
        and frozenset(approved_revisions) in {
            frozenset(set(CONFIGURATION_KINDS) | {"approval_policy_candidate"}),
            frozenset((set(CONFIGURATION_KINDS) - {"auto_reject_policy"}) | {"approval_policy_candidate"}),
        }
        and canonical_configuration_hash(enabled_value) == configuration_hash
    )
    if not require_signoff:
        raise ConfigurationValidationError("Enabled auto-approval policy has no matching Policy Owner sign-off.")
    return enabled_value


def _validate_signed_auto_reject_policy_value(
    value: Any,
    signoff: Mapping[str, Any] | None,
    *,
    revision_id: str,
    configuration_hash: str,
) -> dict[str, Any]:
    """Allow an enabled rejection rule only when its exact stored revision was signed."""
    if not isinstance(value, Mapping) or value.get("enabled") is not True:
        return validate_configuration_value("auto_reject_policy", value)
    disabled = dict(value)
    disabled["enabled"] = False
    normalized = validate_configuration_value("auto_reject_policy", disabled)
    enabled_value = {**normalized, "enabled": True}
    revisions = signoff.get("configuration_revisions") if isinstance(signoff, Mapping) else None
    candidate = revisions.get("auto_reject_policy_candidate") if isinstance(revisions, Mapping) else None
    valid_signoff = (
        isinstance(signoff, Mapping)
        and signoff.get("auto_reject_policy_revision_id") == revision_id
        and signoff.get("approved_configuration_hash") == configuration_hash
        and bool(signoff.get("policy_owner_id"))
        and isinstance(signoff.get("candidate_revision_id"), str)
        and isinstance(candidate, Mapping)
        and candidate.get("revision_id") == signoff.get("candidate_revision_id")
        and isinstance(candidate.get("configuration_hash"), str)
        and set(revisions) == set(CONFIGURATION_KINDS) | {"auto_reject_policy_candidate"}
        and canonical_configuration_hash(enabled_value) == configuration_hash
    )
    if not valid_signoff:
        raise ConfigurationValidationError(
            "Enabled auto-reject policy has no matching authenticated Policy Owner sign-off."
        )
    return enabled_value


def canonical_configuration_hash(value: Any) -> str:
    """Hash a validated JSON configuration using the repository canonical JSON helper."""
    return canonical_hash(value)


def _value_is_enabled(kind: str, value: Mapping[str, Any]) -> bool:
    if kind == "approval_policy":
        return value.get("enabled") is True
    if kind == "budget":
        return any(item.get("active") is True for item in value.get("limits", []))
    if kind in {"media_policy", "strategy_rubric"}:
        return value.get("status") == "ACTIVE"
    if kind == "authority":
        return value.get("active") is True
    if kind == "checker_assignment":
        return bool(value.get("defaults"))
    if kind == "auto_reject_policy":
        return value.get("enabled") is True
    return False


CONFIGURATION_KIND_PERMISSIONS = {
    "checker_assignment": "ADMIN_APPROVER_MANAGE",
}


def _require_admin(principal: Any, correlation_id: str, *, kind: str | None = None) -> None:
    if "ADMIN" not in getattr(principal, "roles", ()):
        raise ApplicationError("FORBIDDEN", "Administrator role is required to manage workflow configuration.", correlation_id)
    required_permission = CONFIGURATION_KIND_PERMISSIONS.get(kind)
    if required_permission and required_permission not in getattr(principal, "permissions", ()):
        raise ApplicationError("FORBIDDEN", "You do not have permission to manage this workflow configuration.", correlation_id)


def _write_transaction(session: Session):
    if session.in_transaction():
        session.rollback()
    return session.begin()


def lock_configuration_registry(session: Session) -> None:
    """Serialize revision writes and round capture on the seeded structural lock row."""
    row = session.scalar(
        select(AuthWorkflowConfigurationLock)
        .where(AuthWorkflowConfigurationLock.id == 1)
        .with_for_update()
    )
    if row is not None:
        return
    # The migration seeds this row. Lazy creation keeps module-level tests usable
    # with metadata.create_all while retaining one winner on a fresh test database.
    session.add(AuthWorkflowConfigurationLock(id=1))
    try:
        session.flush()
    except IntegrityError:
        raise ApplicationError("CONFLICT", "Configuration registry was initialized concurrently; reload and retry.", "configuration-lock")
    session.scalar(
        select(AuthWorkflowConfigurationLock)
        .where(AuthWorkflowConfigurationLock.id == 1)
        .with_for_update()
    )


def _revision_row(session: Session, kind: str, effective_at: datetime) -> AuthWorkflowConfigurationRevision | None:
    return session.scalar(
        select(AuthWorkflowConfigurationRevision)
        .where(
            AuthWorkflowConfigurationRevision.kind == kind,
            AuthWorkflowConfigurationRevision.effective_at <= effective_at,
        )
        .order_by(
            AuthWorkflowConfigurationRevision.effective_at.desc(),
            AuthWorkflowConfigurationRevision.revision.desc(),
        )
        .limit(1)
    )


def _signoff_dict(row: AuthWorkflowApprovalPolicySignoff | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "candidate_revision_id": str(row.candidate_revision_id),
        "approval_policy_revision_id": str(row.approval_policy_revision_id),
        "approved_configuration_hash": row.approved_configuration_hash,
        "policy_owner_id": str(row.policy_owner_id),
        "signed_at": _iso_utc(row.signed_at),
        "authority_revision_id": str(row.authority_revision_id),
        "authority_configuration_hash": row.authority_configuration_hash,
        "configuration_revisions": deepcopy(row.configuration_revisions),
    }


def _auto_reject_signoff_dict(
    row: AuthWorkflowAutoRejectPolicySignoff | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "candidate_revision_id": str(row.candidate_revision_id),
        "auto_reject_policy_revision_id": str(row.auto_reject_policy_revision_id),
        "approved_configuration_hash": row.approved_configuration_hash,
        "policy_owner_id": str(row.policy_owner_id),
        "signed_at": _iso_utc(row.signed_at),
        "configuration_revisions": deepcopy(row.configuration_revisions),
    }


def _signoff_matches_configuration_revisions(
    signoff: Mapping[str, Any] | None,
    configurations: Mapping[str, Any],
) -> bool:
    """A policy sign-off is valid only for its exact non-policy config revisions."""
    if not isinstance(signoff, Mapping):
        return False
    approved = signoff.get("configuration_revisions")
    if not isinstance(approved, Mapping):
        return False
    for kind in CONFIGURATION_KINDS:
        if kind in {"approval_policy", "auto_reject_policy"}:
            continue
        expected = approved.get(kind)
        captured = configurations.get(kind)
        if not isinstance(expected, Mapping) or not isinstance(captured, Mapping):
            return False
        if (
            expected.get("revision_id") != captured.get("revision_id")
            or expected.get("configuration_hash") != captured.get("configuration_hash")
        ):
            return False
    return True


def _auto_reject_signoff_matches_configuration_revisions(
    signoff: Mapping[str, Any] | None,
    configurations: Mapping[str, Any],
) -> bool:
    """Auto-reject sign-off follows current rules, scope and mandate snapshots, not itself."""
    if not isinstance(signoff, Mapping):
        return False
    approved = signoff.get("configuration_revisions")
    if not isinstance(approved, Mapping):
        return False
    if set(approved) != set(CONFIGURATION_KINDS) | {"auto_reject_policy_candidate"}:
        return False
    for kind in CONFIGURATION_KINDS:
        if kind == "auto_reject_policy":
            continue
        expected = approved.get(kind)
        captured = configurations.get(kind)
        if not isinstance(expected, Mapping) or not isinstance(captured, Mapping):
            return False
        if (
            expected.get("revision_id") != captured.get("revision_id")
            or expected.get("configuration_hash") != captured.get("configuration_hash")
        ):
            return False
    candidate = approved.get("auto_reject_policy_candidate")
    return (
        isinstance(candidate, Mapping)
        and candidate.get("revision_id") == signoff.get("candidate_revision_id")
        and isinstance(candidate.get("configuration_hash"), str)
        and candidate.get("configuration_hash") != ""
    )


def _resolution_from_row(
    session: Session,
    kind: str,
    row: AuthWorkflowConfigurationRevision | None,
    effective_at: datetime,
) -> ConfigurationResolution:
    if row is None:
        return ConfigurationResolution(kind, "UNCONFIGURED", None, None, None, None, None)
    signoff = None
    is_enabled = _value_is_enabled(kind, row.value)
    if kind == "approval_policy" and is_enabled:
        signoff_row = session.scalar(select(AuthWorkflowApprovalPolicySignoff).where(
            AuthWorkflowApprovalPolicySignoff.approval_policy_revision_id == row.id,
            AuthWorkflowApprovalPolicySignoff.approved_configuration_hash == row.configuration_hash,
        ))
        signoff = _signoff_dict(signoff_row)
        is_enabled = signoff is not None
        if is_enabled:
            live_configurations = {}
            for related_kind in CONFIGURATION_KINDS:
                if related_kind == "approval_policy":
                    continue
                related = _revision_row(session, related_kind, effective_at)
                live_configurations[related_kind] = {
                    "revision_id": str(related.id) if related else None,
                    "configuration_hash": related.configuration_hash if related else None,
                }
            is_enabled = _signoff_matches_configuration_revisions(signoff, live_configurations)
    elif kind == "auto_reject_policy" and is_enabled:
        signoff_row = session.scalar(select(AuthWorkflowAutoRejectPolicySignoff).where(
            AuthWorkflowAutoRejectPolicySignoff.auto_reject_policy_revision_id == row.id,
            AuthWorkflowAutoRejectPolicySignoff.approved_configuration_hash == row.configuration_hash,
        ))
        signoff = _auto_reject_signoff_dict(signoff_row)
        candidate = session.get(
            AuthWorkflowConfigurationRevision,
            signoff_row.candidate_revision_id,
        ) if signoff_row is not None else None
        candidate_reference = (
            signoff.get("configuration_revisions", {}).get("auto_reject_policy_candidate")
            if signoff is not None else None
        )
        is_enabled = bool(
            signoff is not None
            and candidate is not None
            and candidate.kind == "auto_reject_policy"
            and candidate.value.get("enabled") is False
            and isinstance(candidate_reference, Mapping)
            and candidate_reference.get("revision_id") == str(candidate.id)
            and candidate_reference.get("configuration_hash") == candidate.configuration_hash
        )
        if is_enabled:
            live_configurations = {}
            for related_kind in CONFIGURATION_KINDS:
                related = _revision_row(session, related_kind, effective_at)
                live_configurations[related_kind] = {
                    "revision_id": str(related.id) if related else None,
                    "configuration_hash": related.configuration_hash if related else None,
                }
            is_enabled = _auto_reject_signoff_matches_configuration_revisions(signoff, live_configurations)
    return ConfigurationResolution(
        kind=kind,
        status="EFFECTIVE" if is_enabled else "DISABLED",
        revision_id=str(row.id),
        revision=row.revision,
        effective_at=row.effective_at,
        configuration_hash=row.configuration_hash,
        value=deepcopy(row.value),
        signoff=signoff,
    )


def resolve_configuration_kind(
    session: Session,
    kind: str,
    effective_at: datetime,
) -> ConfigurationResolution:
    if kind not in CONFIGURATION_KINDS:
        raise ConfigurationValidationError("Unknown configuration kind.")
    moment = _require_utc(effective_at, "effective_at")
    return _resolution_from_row(session, kind, _revision_row(session, kind, moment), moment)


def budget_decision(
    configuration: Mapping[str, Any] | None,
    department: str,
    amount_minor_units: str,
    *,
    resolution: ConfigurationResolution | None = None,
) -> BudgetDecision:
    if not isinstance(amount_minor_units, str) or not _AMOUNT_PATTERN.fullmatch(amount_minor_units):
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", "INVALID_INPUT", None, None, None, None, None, None)
    if configuration is None:
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", "UNCONFIGURED", None, amount_minor_units, None, None, None, None)
    try:
        configuration = validate_configuration_value("budget", configuration)
    except ConfigurationValidationError:
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", "INVALID_INPUT", None, amount_minor_units, None, None, None, None)
    matches = [
        item for item in configuration.get("limits", [])
        if item.get("department") == department and item.get("active") is True
    ]
    if len(matches) != 1:
        state = "UNCONFIGURED" if not matches else "AMBIGUOUS"
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", state, "VND", amount_minor_units, None, None, None, None)
    limit = matches[0]["limit_minor_units"]
    if not isinstance(limit, str) or not _AMOUNT_PATTERN.fullmatch(limit):
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", "INVALID_INPUT", "VND", amount_minor_units, None, None, None, None)
    selected = resolution
    return BudgetDecision(
        result="PASS" if int(amount_minor_units) <= int(limit) else "HUMAN_REVIEW_REQUIRED",
        status="CONFIGURED",
        currency="VND",
        amount_minor_units=amount_minor_units,
        limit_minor_units=limit,
        configuration_revision_id=selected.revision_id if selected else None,
        configuration_revision=selected.revision if selected else None,
        configuration_hash=selected.configuration_hash if selected else None,
    )


def _validate_effective_relationships(
    session: Session,
    *,
    candidate_kind: str,
    candidate_value: dict[str, Any],
    effective_at: datetime,
) -> None:
    related: dict[str, dict[str, Any] | None] = {}
    for kind in ("budget", "authority", "strategy_rubric", "approval_policy"):
        if kind == candidate_kind:
            related[kind] = candidate_value
        else:
            row = _revision_row(session, kind, effective_at)
            related[kind] = row.value if row is not None else None

    rubric = related["strategy_rubric"]
    policy = related["approval_policy"]
    if rubric and policy:
        threshold = policy.get("feasibility_score_threshold_exclusive")
        rubric_maximum = sum(item["weight"] for item in rubric.get("criteria", []))
        if threshold is not None and not 0 <= threshold < rubric_maximum:
            raise ConfigurationValidationError("Feasibility threshold must be below the rubric's 100 point maximum.")


def feasibility_score_passes(score: Any, exclusive_threshold: int) -> bool:
    """Keep the default 'greater than 70' boundary explicit for evaluator consumers."""
    if type(score) not in (int, float) or not 0 <= score <= 100:
        return False
    if type(exclusive_threshold) is not int or not 0 <= exclusive_threshold < 100:
        return False
    return score > exclusive_threshold


def create_configuration_revision(
    session: Session,
    principal: Any,
    correlation_id: str,
    *,
    kind: str,
    expected_revision: int | None,
    effective_at: datetime,
    change_reason: str,
    value: Any,
) -> dict[str, Any]:
    _require_admin(principal, correlation_id, kind=kind)
    if kind not in CONFIGURATION_KINDS:
        raise ApplicationError("VALIDATION_ERROR", "Unknown configuration kind.", correlation_id)
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 1):
        raise ApplicationError("VALIDATION_ERROR", "expected_revision must be null or a positive integer.", correlation_id)
    try:
        effective_at = _require_utc(effective_at, "effective_at")
        if not isinstance(change_reason, str) or not change_reason.strip() or len(change_reason.strip()) > 1000:
            raise ConfigurationValidationError("change_reason must contain 1 to 1000 non-blank characters.")
        normalized_value = validate_configuration_value(kind, value)
    except ConfigurationValidationError as exc:
        raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc

    try:
        with _write_transaction(session):
            lock_configuration_registry(session)
            if kind == "checker_assignment":
                from src.backend.application.checker_assignment_configuration import validate_checker_assignment_value
                try:
                    validate_checker_assignment_value(session, normalized_value, lock=True)
                except ValueError as exc:
                    raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
            if kind == "authority":
                from src.backend.application.checker_assignment_configuration import validate_authority_value
                try:
                    validate_authority_value(session, normalized_value, lock=True)
                except ValueError as exc:
                    raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
            head = session.scalar(
                select(AuthWorkflowConfigurationHead)
                .where(AuthWorkflowConfigurationHead.kind == kind)
                .with_for_update()
            )
            if head is None:
                head = AuthWorkflowConfigurationHead(kind=kind, latest_revision=0)
                session.add(head)
                try:
                    session.flush()
                except IntegrityError as exc:
                    raise ApplicationError("CONFLICT", "Configuration was updated concurrently; reload and retry.", correlation_id) from exc
            current_revision = head.latest_revision or None
            if current_revision != expected_revision:
                raise ApplicationError("CONFLICT", "Configuration revision changed; reload before saving.", correlation_id)
            overlap = session.scalar(select(AuthWorkflowConfigurationRevision.id).where(
                AuthWorkflowConfigurationRevision.kind == kind,
                AuthWorkflowConfigurationRevision.effective_at == effective_at,
            ).limit(1))
            if overlap is not None:
                raise ApplicationError("CONFLICT", "A revision already exists at this effective time.", correlation_id)
            try:
                _validate_effective_relationships(
                    session,
                    candidate_kind=kind,
                    candidate_value=normalized_value,
                    effective_at=effective_at,
                )
            except ConfigurationValidationError as exc:
                raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc

            revision_number = head.latest_revision + 1
            revision = AuthWorkflowConfigurationRevision(
                kind=kind,
                revision=revision_number,
                effective_at=effective_at,
                change_reason=change_reason.strip(),
                value=normalized_value,
                configuration_hash=canonical_configuration_hash(normalized_value),
                changed_by=principal.id,
            )
            session.add(revision)
            head.latest_revision = revision_number
            session.flush()
            session.add(AdminAuditEvent(
                actor_id=principal.id,
                employee_id=None,
                action="WORKFLOW_CONFIG_REVISION_CREATED",
                before_state={"kind": kind, "revision": current_revision},
                after_state={
                    "kind": kind,
                    "revision": revision_number,
                    "revision_id": str(revision.id),
                    "configuration_hash": revision.configuration_hash,
                    "effective_at": _iso_utc(effective_at),
                    "change_reason": change_reason.strip(),
                    "result": "SUCCESS",
                },
            ))
            session.flush()
            session.refresh(revision)
            return configuration_revision_dict(revision, status="SCHEDULED" if effective_at > datetime.now(timezone.utc) else _resolution_from_row(session, kind, revision, effective_at).status)
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Configuration was updated concurrently or overlaps an effective date.", correlation_id) from exc


def sign_off_approval_policy(
    session: Session,
    principal: Any,
    correlation_id: str,
    *,
    expected_revisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Policy Owner signs and atomically activates the exact, currently configured policy."""
    if "ADMIN" not in getattr(principal, "roles", ()):
        raise ApplicationError("FORBIDDEN", "An authenticated administrator Policy Owner is required for sign-off.", correlation_id)
    if set(expected_revisions) != set(CONFIGURATION_KINDS):
        raise ApplicationError("VALIDATION_ERROR", "Sign-off requires the current revision of every workflow configuration.", correlation_id)
    try:
        with _write_transaction(session):
            lock_configuration_registry(session)
            moment = datetime.now(timezone.utc)
            policy_ref = expected_revisions["approval_policy"]
            candidate = session.scalar(select(AuthWorkflowConfigurationRevision).where(
                AuthWorkflowConfigurationRevision.kind == "approval_policy",
                AuthWorkflowConfigurationRevision.id == UUID(policy_ref["revision_id"]),
            ).with_for_update())
            if candidate is None:
                raise ApplicationError("CONFLICT", "The approval policy changed; reload before signing.", correlation_id)

            prior_signoff = session.scalar(select(AuthWorkflowApprovalPolicySignoff).where(
                AuthWorkflowApprovalPolicySignoff.candidate_revision_id == candidate.id,
            ))
            if prior_signoff is not None:
                if prior_signoff.policy_owner_id != principal.id:
                    raise ApplicationError("FORBIDDEN", "Only the original Policy Owner may replay this sign-off.", correlation_id)
                revision = session.get(AuthWorkflowConfigurationRevision, prior_signoff.approval_policy_revision_id)
                replay_status = _resolution_from_row(
                    session, "approval_policy", revision, datetime.now(timezone.utc),
                ).status
                return {
                    "revision": configuration_revision_dict(
                        revision, status=replay_status, signoff=_signoff_dict(prior_signoff),
                    ),
                    "replayed": True,
                }

            resolved: dict[str, AuthWorkflowConfigurationRevision] = {}
            for kind in CONFIGURATION_KINDS:
                row = _revision_row(session, kind, moment)
                reference = expected_revisions[kind]
                if (row is None or str(row.id) != reference["revision_id"]
                        or row.configuration_hash != reference["configuration_hash"]):
                    raise ApplicationError("CONFLICT", "Workflow configuration changed; reload all revisions before signing.", correlation_id)
                resolved[kind] = row

            head = session.scalar(select(AuthWorkflowConfigurationHead).where(
                AuthWorkflowConfigurationHead.kind == "approval_policy",
            ).with_for_update())
            if head is None or head.latest_revision != candidate.revision:
                raise ApplicationError("CONFLICT", "A newer approval-policy revision exists; reload before signing.", correlation_id)
            if candidate.configuration_hash != policy_ref["configuration_hash"] or candidate.value.get("enabled") is not False:
                raise ApplicationError("CONFLICT", "Sign-off must target the currently disabled approval-policy candidate.", correlation_id)

            policy_value = validate_configuration_value("approval_policy", candidate.value)
            if (policy_value["media_confidence_threshold"] != 0.85
                    or policy_value["feasibility_score_threshold_exclusive"] != 70
                    or policy_value["feasibility_confidence_threshold"] != 0.80):
                raise ApplicationError("VALIDATION_ERROR", "The approved auto-approval thresholds do not match this policy revision.", correlation_id)

            from src.backend.application.checker_assignment_configuration import (
                validate_authority_value, validate_checker_assignment_value,
            )
            from src.backend.domain.policy import STRATEGY_CRITERIA

            budget = validate_configuration_value("budget", resolved["budget"].value)
            marketing_limits = [item for item in budget["limits"] if item["department"] == "Marketing" and item["active"]]
            if budget["currency"] != "VND" or len(marketing_limits) != 1 or marketing_limits[0]["limit_minor_units"] != "10000000":
                raise ApplicationError("VALIDATION_ERROR", "Marketing's active budget must be exactly 10,000,000 VND.", correlation_id)

            media = validate_configuration_value("media_policy", resolved["media_policy"].value)
            if (media["status"] != "ACTIVE" or media["scope_departments"] != ["Marketing"]
                    or media["scope_channels"] != ["social"] or len(media["rules"]) != 2
                    or any(rule["severity"] != "WARNING" for rule in media["rules"])):
                raise ApplicationError("VALIDATION_ERROR", "Media policy must retain the two approved WARNING rules in Marketing/social scope.", correlation_id)

            rubric = validate_configuration_value("strategy_rubric", resolved["strategy_rubric"].value)
            expected_weights = {criterion_id: weight for criterion_id, _label, weight in STRATEGY_CRITERIA}
            actual_weights = {item["criterion_id"]: item["weight"] for item in rubric["criteria"]}
            if rubric["status"] != "ACTIVE" or actual_weights != expected_weights:
                raise ApplicationError("VALIDATION_ERROR", "The active Strategy rubric does not match the approved rubric weights.", correlation_id)

            assignment = validate_configuration_value("checker_assignment", resolved["checker_assignment"].value)
            try:
                validate_checker_assignment_value(session, assignment, lock=True)
            except ValueError as exc:
                raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
            marketing_assignment = next((item for item in assignment["defaults"] if item["department"] == "Marketing"), None)
            if assignment["maker_may_select_other"] is not True or marketing_assignment is None:
                raise ApplicationError("VALIDATION_ERROR", "Marketing assignment must default to lekhoi and allow only eligible Checker selection.", correlation_id)

            authority = validate_configuration_value("authority", resolved["authority"].value)
            if (authority["active"] is not True or authority["currency"] != "VND"
                    or authority["auto_limit_minor_units"] != "5000000"
                    or authority["allowed_departments"] != ["Marketing"]
                    or authority["checker_id"] != marketing_assignment["checker_id"]
                    or authority["policy_owner_id"] != str(principal.id)
                    or authority["budget_authority_id"] is None):
                raise ApplicationError("VALIDATION_ERROR", "Authority must be active with the approved limit, Marketing scope, Checker, Policy Owner and Budget Authority.", correlation_id)
            try:
                validate_authority_value(session, authority, lock=True)
            except ValueError as exc:
                raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc

            active_owner = session.scalar(
                select(User).join(EmployeeProfile, EmployeeProfile.user_id == User.id).where(
                    User.id == principal.id,
                    User.username == "bkhoa",
                    User.status == "ACTIVE",
                    User.activation_pending.is_(False),
                    User.employment_status == "ACTIVE",
                    EmployeeProfile.employment_status == "ACTIVE",
                ).with_for_update()
            )
            if active_owner is None:
                raise ApplicationError("FORBIDDEN", "Sign-off requires the active bkhoa Policy Owner account.", correlation_id)
            if principal.id != active_owner.id:
                raise ApplicationError("FORBIDDEN", "Sign-off actor does not match the active Policy Owner account.", correlation_id)
            checker = session.scalar(select(User).where(
                User.id == UUID(authority["checker_id"]), User.username == "lekhoi",
                User.status == "ACTIVE", User.activation_pending.is_(False),
                User.employment_status == "ACTIVE",
            ))
            if checker is None:
                raise ApplicationError("VALIDATION_ERROR", "The configured default Checker is not the active lekhoi account.", correlation_id)

            enabled_value = {**policy_value, "enabled": True}
            policy_hash = canonical_configuration_hash(enabled_value)
            new_revision_id = uuid4()
            configuration_revisions = {
                **{
                    kind: {
                        "revision_id": str(row.id),
                        "configuration_hash": row.configuration_hash,
                    }
                    for kind, row in resolved.items()
                },
                "approval_policy_candidate": {
                    "revision_id": str(candidate.id),
                    "configuration_hash": candidate.configuration_hash,
                },
            }
            signoff_proof = {
                "candidate_revision_id": str(candidate.id),
                "approval_policy_revision_id": str(new_revision_id),
                "approved_configuration_hash": policy_hash,
                "policy_owner_id": str(principal.id),
                "configuration_revisions": configuration_revisions,
            }
            normalized_enabled = _validate_signed_approval_policy_value(
                enabled_value, signoff_proof, revision_id=str(new_revision_id),
                configuration_hash=policy_hash,
            )
            effective_at = moment
            while session.scalar(select(AuthWorkflowConfigurationRevision.id).where(
                AuthWorkflowConfigurationRevision.kind == "approval_policy",
                AuthWorkflowConfigurationRevision.effective_at == effective_at,
            )) is not None:
                effective_at += timedelta(microseconds=1)

            activated = AuthWorkflowConfigurationRevision(
                id=new_revision_id,
                kind="approval_policy",
                revision=head.latest_revision + 1,
                effective_at=effective_at,
                change_reason="Policy Owner ký duyệt cấu hình auto-approval.",
                value=normalized_enabled,
                configuration_hash=policy_hash,
                changed_by=principal.id,
            )
            session.add(activated)
            head.latest_revision = activated.revision
            signature = AuthWorkflowApprovalPolicySignoff(
                candidate_revision_id=candidate.id,
                approval_policy_revision_id=new_revision_id,
                approved_configuration_hash=policy_hash,
                policy_owner_id=principal.id,
                signed_at=moment,
                authority_revision_id=resolved["authority"].id,
                authority_configuration_hash=resolved["authority"].configuration_hash,
                configuration_revisions=configuration_revisions,
            )
            session.add(signature)
            session.flush()
            signoff = _signoff_dict(signature)
            session.add(AdminAuditEvent(
                actor_id=principal.id,
                employee_id=None,
                action="WORKFLOW_AUTO_APPROVAL_SIGNOFF",
                before_state={
                    "approval_policy_revision_id": str(candidate.id),
                    "configuration_hash": candidate.configuration_hash,
                    "enabled": False,
                },
                after_state={
                    "approval_policy_revision_id": str(activated.id),
                    "revision": activated.revision,
                    "approved_configuration_hash": policy_hash,
                    "effective_at": _iso_utc(effective_at),
                    "policy_owner_id": str(principal.id),
                    "signed_at": _iso_utc(moment),
                    "authority_revision_id": str(resolved["authority"].id),
                    "authority_configuration_hash": resolved["authority"].configuration_hash,
                    "configuration_revisions": deepcopy(configuration_revisions),
                    "checker_id": authority["checker_id"],
                    "budget_authority_id": authority["budget_authority_id"],
                    "thresholds": {
                        "media_confidence_threshold": policy_value["media_confidence_threshold"],
                        "feasibility_score_threshold_exclusive": policy_value["feasibility_score_threshold_exclusive"],
                        "feasibility_confidence_threshold": policy_value["feasibility_confidence_threshold"],
                    },
                    "result": "SUCCESS",
                },
            ))
            session.flush()
            session.refresh(activated)
            return {
                "revision": configuration_revision_dict(
                    activated, status="EFFECTIVE", signoff=signoff,
                ),
                "replayed": False,
            }
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Policy Owner sign-off conflicted with a concurrent configuration change.", correlation_id) from exc


def sign_off_auto_reject_policy(
    session: Session,
    principal: Any,
    correlation_id: str,
    *,
    expected_revisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Activate one exact production rule revision only through its authenticated Policy Owner."""
    if "ADMIN" not in getattr(principal, "roles", ()):
        raise ApplicationError("FORBIDDEN", "An authenticated administrator Policy Owner is required for sign-off.", correlation_id)
    if set(expected_revisions) != set(CONFIGURATION_KINDS):
        raise ApplicationError("VALIDATION_ERROR", "Sign-off requires the current revision of every workflow configuration.", correlation_id)

    try:
        with _write_transaction(session):
            lock_configuration_registry(session)
            moment = datetime.now(timezone.utc)
            policy_ref = expected_revisions["auto_reject_policy"]
            candidate = session.scalar(select(AuthWorkflowConfigurationRevision).where(
                AuthWorkflowConfigurationRevision.kind == "auto_reject_policy",
                AuthWorkflowConfigurationRevision.id == UUID(policy_ref["revision_id"]),
            ).with_for_update())
            if candidate is None:
                raise ApplicationError("CONFLICT", "The auto-reject policy changed; reload before signing.", correlation_id)

            prior_signoff = session.scalar(select(AuthWorkflowAutoRejectPolicySignoff).where(
                AuthWorkflowAutoRejectPolicySignoff.candidate_revision_id == candidate.id,
            ))
            if prior_signoff is not None:
                if prior_signoff.policy_owner_id != principal.id:
                    raise ApplicationError("FORBIDDEN", "Only the original Policy Owner may replay this sign-off.", correlation_id)
                revision = session.get(AuthWorkflowConfigurationRevision, prior_signoff.auto_reject_policy_revision_id)
                status = _resolution_from_row(session, "auto_reject_policy", revision, datetime.now(timezone.utc)).status
                return {
                    "revision": configuration_revision_dict(
                        revision, status=status, signoff=_auto_reject_signoff_dict(prior_signoff),
                    ),
                    "replayed": True,
                }

            resolved: dict[str, AuthWorkflowConfigurationRevision] = {}
            for kind in CONFIGURATION_KINDS:
                row = _revision_row(session, kind, moment)
                reference = expected_revisions[kind]
                if (row is None or str(row.id) != reference["revision_id"]
                        or row.configuration_hash != reference["configuration_hash"]):
                    raise ApplicationError("CONFLICT", "Workflow configuration changed; reload all revisions before signing.", correlation_id)
                resolved[kind] = row

            head = session.scalar(select(AuthWorkflowConfigurationHead).where(
                AuthWorkflowConfigurationHead.kind == "auto_reject_policy",
            ).with_for_update())
            if (head is None or head.latest_revision != candidate.revision
                    or _utc_from_storage(candidate.effective_at) > moment):
                raise ApplicationError("CONFLICT", "A newer or scheduled auto-reject revision exists; reload before signing.", correlation_id)
            if candidate.configuration_hash != policy_ref["configuration_hash"] or candidate.value.get("enabled") is not False:
                raise ApplicationError("CONFLICT", "Sign-off must target the current disabled auto-reject candidate.", correlation_id)

            try:
                disabled_policy = validate_configuration_value("auto_reject_policy", candidate.value)
            except ConfigurationValidationError as exc:
                raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
            if (disabled_policy["environment"] != "PRODUCTION"
                    or disabled_policy["configuration_id"].startswith("VERIFY-")
                    or disabled_policy["scope_departments"] != ["Marketing"]
                    or disabled_policy["scope_channels"] != ["social"]):
                raise ApplicationError("VALIDATION_ERROR", "Production auto-reject must use Marketing/social and cannot use a Verify fixture identity.", correlation_id)
            if any(rule["media_confidence_threshold"] < 0.85
                   or rule["feasibility_confidence_threshold"] < 0.80
                   for rule in disabled_policy["rules"]):
                raise ApplicationError("VALIDATION_ERROR", "Auto-reject rules cannot lower the approved Media/Strategy confidence floors.", correlation_id)

            approval_value = resolved["approval_policy"].value
            if not isinstance(approval_value, Mapping) or approval_value.get("enabled") is not True:
                raise ApplicationError("VALIDATION_ERROR", "Production auto-reject requires the currently signed auto-approval policy and all ordinary approval gates.", correlation_id)
            approval_signoff_row = session.scalar(select(AuthWorkflowApprovalPolicySignoff).where(
                AuthWorkflowApprovalPolicySignoff.approval_policy_revision_id == resolved["approval_policy"].id,
            ))
            approval_signoff = _signoff_dict(approval_signoff_row)
            try:
                validate_configuration_value("approval_policy", {
                    **approval_value, "enabled": False,
                })
                _validate_signed_approval_policy_value(
                    approval_value, approval_signoff,
                    revision_id=str(resolved["approval_policy"].id),
                    configuration_hash=resolved["approval_policy"].configuration_hash,
                )
            except ConfigurationValidationError as exc:
                raise ApplicationError("VALIDATION_ERROR", "Production auto-reject requires a valid, current auto-approval Policy Owner sign-off.", correlation_id) from exc
            if (approval_value.get("media_confidence_threshold") != 0.85
                    or approval_value.get("feasibility_score_threshold_exclusive") != 70
                    or approval_value.get("feasibility_confidence_threshold") != 0.80):
                raise ApplicationError("VALIDATION_ERROR", "The approved auto-approval thresholds must remain 0.85, >70 and 0.80.", correlation_id)
            live_revisions = {
                kind: {"revision_id": str(row.id), "configuration_hash": row.configuration_hash}
                for kind, row in resolved.items()
            }
            if not _signoff_matches_configuration_revisions(approval_signoff, live_revisions):
                raise ApplicationError("VALIDATION_ERROR", "The auto-approval sign-off no longer matches current budget, authority, Media, Strategy or assignment revisions.", correlation_id)

            budget = validate_configuration_value("budget", resolved["budget"].value)
            marketing_limits = [item for item in budget["limits"] if item["department"] == "Marketing" and item["active"]]
            if budget["currency"] != "VND" or len(marketing_limits) != 1 or marketing_limits[0]["limit_minor_units"] != "10000000":
                raise ApplicationError("VALIDATION_ERROR", "Marketing's active budget must be exactly 10,000,000 VND.", correlation_id)

            media = validate_configuration_value("media_policy", resolved["media_policy"].value)
            if (media["status"] != "ACTIVE" or media["scope_departments"] != ["Marketing"]
                    or media["scope_channels"] != ["social"] or len(media["rules"]) != 2
                    or any(rule["severity"] != "WARNING" for rule in media["rules"])):
                raise ApplicationError("VALIDATION_ERROR", "Media policy must retain the two approved WARNING rules in Marketing/social scope.", correlation_id)

            rubric = validate_configuration_value("strategy_rubric", resolved["strategy_rubric"].value)
            from src.backend.domain.policy import STRATEGY_CRITERIA
            expected_weights = {criterion_id: weight for criterion_id, _label, weight in STRATEGY_CRITERIA}
            actual_weights = {item["criterion_id"]: item["weight"] for item in rubric["criteria"]}
            if rubric["status"] != "ACTIVE" or actual_weights != expected_weights:
                raise ApplicationError("VALIDATION_ERROR", "The active Strategy rubric does not match the approved rubric weights.", correlation_id)

            assignment = validate_configuration_value("checker_assignment", resolved["checker_assignment"].value)
            from src.backend.application.checker_assignment_configuration import validate_checker_assignment_value
            try:
                validate_checker_assignment_value(session, assignment, lock=True)
            except ValueError as exc:
                raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
            marketing_assignment = next((item for item in assignment["defaults"] if item["department"] == "Marketing"), None)
            if marketing_assignment is None or assignment["maker_may_select_other"] is not True:
                raise ApplicationError("VALIDATION_ERROR", "Marketing must retain its default Checker and eligible Checker selection.", correlation_id)
            checker = session.scalar(select(User).where(
                User.id == UUID(marketing_assignment["checker_id"]), User.username == "lekhoi",
                User.status == "ACTIVE", User.activation_pending.is_(False), User.employment_status == "ACTIVE",
            ))
            if checker is None:
                raise ApplicationError("VALIDATION_ERROR", "The configured default Checker is not the active lekhoi account.", correlation_id)

            authority = validate_configuration_value("authority", resolved["authority"].value)
            if (authority["active"] is not True or authority["currency"] != "VND"
                    or authority["auto_limit_minor_units"] != "5000000"
                    or authority["allowed_departments"] != ["Marketing"]
                    or authority["checker_id"] != str(checker.id)
                    or authority["policy_owner_id"] != str(principal.id)
                    or authority["budget_authority_id"] is None):
                raise ApplicationError("VALIDATION_ERROR", "A complete active 5,000,000 VND Marketing authority must identify the assigned Checker, signing Policy Owner and Budget Authority.", correlation_id)
            budget_authority = session.scalar(
                select(User).join(EmployeeProfile, EmployeeProfile.user_id == User.id).where(
                    User.id == UUID(authority["budget_authority_id"]),
                    User.status == "ACTIVE", User.activation_pending.is_(False),
                    User.employment_status == "ACTIVE", EmployeeProfile.employment_status == "ACTIVE",
                ).with_for_update()
            )
            if budget_authority is None:
                raise ApplicationError("VALIDATION_ERROR", "The configured Budget Authority account must be active before auto-reject sign-off.", correlation_id)

            owner = session.scalar(
                select(User).join(EmployeeProfile, EmployeeProfile.user_id == User.id)
                .join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                .where(
                    User.id == principal.id, User.username == "bkhoa", Role.code == "ADMIN",
                    User.status == "ACTIVE", User.activation_pending.is_(False),
                    User.employment_status == "ACTIVE", EmployeeProfile.employment_status == "ACTIVE",
                ).with_for_update()
            )
            if owner is None:
                raise ApplicationError("FORBIDDEN", "Sign-off requires the active bkhoa Policy Owner administrator account.", correlation_id)

            active_value = {
                **disabled_policy,
                "revision": head.latest_revision + 1,
                "enabled": True,
            }
            policy_hash = canonical_configuration_hash(active_value)
            activated_id = uuid4()
            configuration_revisions = {
                **{
                    kind: {"revision_id": str(row.id), "configuration_hash": row.configuration_hash}
                    for kind, row in resolved.items()
                },
                "auto_reject_policy_candidate": {
                    "revision_id": str(candidate.id), "configuration_hash": candidate.configuration_hash,
                },
            }
            signoff_proof = {
                "candidate_revision_id": str(candidate.id),
                "auto_reject_policy_revision_id": str(activated_id),
                "approved_configuration_hash": policy_hash,
                "policy_owner_id": str(principal.id),
                "configuration_revisions": configuration_revisions,
            }
            normalized_enabled = _validate_signed_auto_reject_policy_value(
                active_value, signoff_proof, revision_id=str(activated_id), configuration_hash=policy_hash,
            )
            activated_at = moment
            while session.scalar(select(AuthWorkflowConfigurationRevision.id).where(
                AuthWorkflowConfigurationRevision.kind == "auto_reject_policy",
                AuthWorkflowConfigurationRevision.effective_at == activated_at,
            )) is not None:
                activated_at += timedelta(microseconds=1)
            activated = AuthWorkflowConfigurationRevision(
                id=activated_id, kind="auto_reject_policy", revision=head.latest_revision + 1,
                effective_at=activated_at,
                change_reason="Policy Owner ký duyệt cấu hình auto-reject theo rule và hash cụ thể.",
                value=normalized_enabled, configuration_hash=policy_hash, changed_by=principal.id,
            )
            session.add(activated)
            head.latest_revision = activated.revision
            signature = AuthWorkflowAutoRejectPolicySignoff(
                candidate_revision_id=candidate.id,
                auto_reject_policy_revision_id=activated_id,
                approved_configuration_hash=policy_hash,
                policy_owner_id=principal.id,
                signed_at=moment,
                configuration_revisions=configuration_revisions,
            )
            session.add(signature)
            session.flush()
            signoff = _auto_reject_signoff_dict(signature)
            session.add(AdminAuditEvent(
                actor_id=principal.id, employee_id=None,
                action="WORKFLOW_AUTO_REJECT_SIGNOFF",
                before_state={
                    "auto_reject_policy_revision_id": str(candidate.id),
                    "configuration_hash": candidate.configuration_hash,
                    "enabled": False,
                },
                after_state={
                    "auto_reject_policy_revision_id": str(activated.id),
                    "revision": activated.revision,
                    "approved_configuration_hash": policy_hash,
                    "effective_at": _iso_utc(activated_at),
                    "policy_owner_id": str(principal.id),
                    "signed_at": _iso_utc(moment),
                    "configuration_revisions": deepcopy(configuration_revisions),
                    "scope_departments": disabled_policy["scope_departments"],
                    "scope_channels": disabled_policy["scope_channels"],
                    "rules": [{
                        "rule_id": rule["rule_id"], "reason_code": rule["reason_code"],
                        "evidence_kind": rule["evidence_kind"],
                        "evidence_confidence_threshold": rule["evidence_confidence_threshold"],
                        "media_confidence_threshold": rule["media_confidence_threshold"],
                        "feasibility_confidence_threshold": rule["feasibility_confidence_threshold"],
                    } for rule in disabled_policy["rules"]],
                    "result": "SUCCESS",
                },
            ))
            session.flush()
            session.refresh(activated)
            return {"revision": configuration_revision_dict(activated, status="EFFECTIVE", signoff=signoff), "replayed": False}
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Policy Owner sign-off conflicted with a concurrent configuration change.", correlation_id) from exc


def configuration_revision_dict(
    revision: AuthWorkflowConfigurationRevision,
    *,
    status: str | None = None,
    signoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "revision_id": str(revision.id),
        "kind": revision.kind,
        "revision": revision.revision,
        "status": status or ("EFFECTIVE" if _value_is_enabled(revision.kind, revision.value) else "DISABLED"),
        "effective_at": _iso_utc(revision.effective_at),
        "change_reason": revision.change_reason,
        "value": deepcopy(revision.value),
        "configuration_hash": revision.configuration_hash,
        "changed_by": str(revision.changed_by),
        "created_at": _iso_utc(revision.created_at),
        "signoff": deepcopy(signoff),
    }


def current_configuration(
    session: Session,
    principal: Any,
    correlation_id: str,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    moment = _require_utc(as_of or datetime.now(timezone.utc), "as_of")
    result = []
    for kind in CONFIGURATION_KINDS:
        active = _revision_row(session, kind, moment)
        next_revision = session.scalar(
            select(AuthWorkflowConfigurationRevision)
            .where(
                AuthWorkflowConfigurationRevision.kind == kind,
                AuthWorkflowConfigurationRevision.effective_at > moment,
            )
            .order_by(AuthWorkflowConfigurationRevision.effective_at.asc(), AuthWorkflowConfigurationRevision.revision.asc())
            .limit(1)
        )
        resolution = _resolution_from_row(session, kind, active, moment)
        result.append({
            "kind": kind,
            "status": resolution.status,
            "current_revision": configuration_revision_dict(active, status=resolution.status, signoff=resolution.signoff) if active else None,
            "next_scheduled_revision": configuration_revision_dict(next_revision, status="SCHEDULED") if next_revision else None,
        })
    return {"as_of": _iso_utc(moment), "items": result}


def configuration_history(
    session: Session,
    kind: str,
    principal: Any,
    correlation_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    _require_admin(principal, correlation_id, kind=kind)
    if kind not in CONFIGURATION_KINDS:
        raise ApplicationError("VALIDATION_ERROR", "Unknown configuration kind.", "configuration-history")
    if offset < 0 or not 1 <= limit <= 200:
        raise ApplicationError("VALIDATION_ERROR", "Invalid history pagination.", "configuration-history")
    moment = _require_utc(as_of or datetime.now(timezone.utc), "as_of")
    total = session.scalar(select(func.count(AuthWorkflowConfigurationRevision.id)).where(
        AuthWorkflowConfigurationRevision.kind == kind,
    )) or 0
    rows = session.scalars(
        select(AuthWorkflowConfigurationRevision)
        .where(AuthWorkflowConfigurationRevision.kind == kind)
        .order_by(AuthWorkflowConfigurationRevision.revision.desc())
        .offset(offset).limit(limit)
    ).all()
    effective = _revision_row(session, kind, moment)
    items = []
    for row in rows:
        if _utc_from_storage(row.effective_at) > moment:
            status = "SCHEDULED"
        elif effective is not None and row.id == effective.id:
            status = _resolution_from_row(session, kind, row, moment).status
        else:
            status = "SUPERSEDED"
        signoff_row = session.scalar(select(AuthWorkflowApprovalPolicySignoff).where(
            AuthWorkflowApprovalPolicySignoff.approval_policy_revision_id == row.id,
        )) if kind == "approval_policy" else None
        auto_reject_signoff = session.scalar(select(AuthWorkflowAutoRejectPolicySignoff).where(
            AuthWorkflowAutoRejectPolicySignoff.auto_reject_policy_revision_id == row.id,
        )) if kind == "auto_reject_policy" else None
        revision_signoff = (
            _signoff_dict(signoff_row) if signoff_row is not None
            else _auto_reject_signoff_dict(auto_reject_signoff)
        )
        items.append(configuration_revision_dict(row, status=status, signoff=revision_signoff))
    return {"kind": kind, "as_of": _iso_utc(moment), "items": items, "offset": offset, "limit": limit, "total": total}


def resolve_round_configuration(
    session: Session,
    *,
    plan_id: UUID,
    plan_version: int,
    approval_round: int,
    department_id: str | None,
    maker_id: UUID,
    selected_checker_id: UUID | None,
    effective_at: datetime,
) -> RoundConfigurationSnapshot:
    from src.backend.application.checker_assignment_configuration import resolve_checker_assignment

    moment = _require_utc(effective_at, "effective_at")
    lock_configuration_registry(session)
    configurations = {
        kind: resolve_configuration_kind(session, kind, moment).as_dict()
        for kind in CONFIGURATION_KINDS
    }
    assignment = resolve_checker_assignment(
        session,
        department_id=department_id,
        maker_id=maker_id,
        selected_checker_id=selected_checker_id,
        effective_at=moment,
    )
    body = {
        "plan_id": str(plan_id),
        "plan_version": plan_version,
        "approval_round": approval_round,
        "effective_at": _iso_utc(moment),
        "configurations": configurations,
        "checker_assignment": assignment.as_dict(),
    }
    return RoundConfigurationSnapshot(
        plan_id=plan_id,
        plan_version=plan_version,
        approval_round=approval_round,
        effective_at=moment,
        configurations=configurations,
        checker_assignment=assignment.as_dict(),
        snapshot_hash=canonical_configuration_hash(body),
    )


def capture_round_configuration_snapshot(
    session: Session,
    *,
    plan_id: UUID,
    plan_version: int,
    approval_round: int,
    department_id: str | None,
    maker_id: UUID,
    selected_checker_id: UUID | None,
    effective_at: datetime,
) -> RoundConfigurationSnapshot:
    """Capture the immutable config boundary once; a retry always receives the stored row."""
    existing = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
        AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
        AuthWorkflowRoundConfigurationSnapshot.approval_round == approval_round,
    ))
    if existing is not None:
        if existing.plan_version != plan_version:
            raise ApplicationError("CONFLICT", "Round configuration snapshot identity does not match the requested version.", "configuration-snapshot")
        return RoundConfigurationSnapshot(
            snapshot_id=existing.id,
            plan_id=existing.plan_id,
            plan_version=existing.plan_version,
            approval_round=existing.approval_round,
            effective_at=_utc_from_storage(existing.effective_at),
            configurations=deepcopy(existing.configurations),
            checker_assignment=deepcopy(existing.checker_assignment),
            snapshot_hash=existing.snapshot_hash,
        )

    resolved = resolve_round_configuration(
        session,
        plan_id=plan_id,
        plan_version=plan_version,
        approval_round=approval_round,
        department_id=department_id,
        maker_id=maker_id,
        selected_checker_id=selected_checker_id,
        effective_at=effective_at,
    )
    row = AuthWorkflowRoundConfigurationSnapshot(
        plan_id=resolved.plan_id,
        plan_version=resolved.plan_version,
        approval_round=resolved.approval_round,
        effective_at=resolved.effective_at,
        configurations=deepcopy(resolved.configurations),
        checker_assignment=deepcopy(resolved.checker_assignment),
        snapshot_hash=resolved.snapshot_hash,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        concurrent = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
            AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
            AuthWorkflowRoundConfigurationSnapshot.approval_round == approval_round,
        ))
        if concurrent is None or concurrent.plan_version != plan_version:
            raise ApplicationError("CONFLICT", "A round configuration snapshot was captured concurrently.", "configuration-snapshot") from exc
        return RoundConfigurationSnapshot(
            snapshot_id=concurrent.id,
            plan_id=concurrent.plan_id,
            plan_version=concurrent.plan_version,
            approval_round=concurrent.approval_round,
            effective_at=_utc_from_storage(concurrent.effective_at),
            configurations=deepcopy(concurrent.configurations),
            checker_assignment=deepcopy(concurrent.checker_assignment),
            snapshot_hash=concurrent.snapshot_hash,
        )
    return RoundConfigurationSnapshot(
        snapshot_id=row.id,
        plan_id=resolved.plan_id,
        plan_version=resolved.plan_version,
        approval_round=resolved.approval_round,
        effective_at=resolved.effective_at,
        configurations=resolved.configurations,
        checker_assignment=resolved.checker_assignment,
        snapshot_hash=resolved.snapshot_hash,
    )


def get_round_configuration_snapshot(
    session: Session,
    *,
    plan_id: UUID,
    approval_round: int,
) -> RoundConfigurationSnapshot | None:
    """Read the exact immutable round snapshot for retries and evaluators."""
    existing = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
        AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
        AuthWorkflowRoundConfigurationSnapshot.approval_round == approval_round,
    ))
    if existing is None:
        return None
    return RoundConfigurationSnapshot(
        snapshot_id=existing.id,
        plan_id=existing.plan_id,
        plan_version=existing.plan_version,
        approval_round=existing.approval_round,
        effective_at=_utc_from_storage(existing.effective_at),
        configurations=deepcopy(existing.configurations),
        checker_assignment=deepcopy(existing.checker_assignment),
        snapshot_hash=existing.snapshot_hash,
    )


def apply_round_configuration_snapshot(base_configuration, snapshot):
    """Freeze the B registry values into the evaluator/policy config for this round.

    The base configuration contributes runtime model snapshots and the legacy
    compatibility values only where the B registry has no revision. Any B
    revision, including a disabled one, takes precedence. The caller stores the
    returned object on the evaluation run; retries must deserialize that saved
    object and the same round snapshot rather than resolving current revisions.
    """
    from src.backend.domain.policy import (
        ApprovalConfiguration,
        AuthoritySnapshot,
        BudgetConfiguration,
        Criterion,
        MediaCompliancePolicy,
        PolicySnapshot,
        STRATEGY_CRITERIA,
        StrategyRubric,
    )

    configurations = getattr(snapshot, "configurations", None)
    if not isinstance(configurations, Mapping):
        raise ConfigurationValidationError("Round configuration snapshot is incomplete.")
    # Older immutable rounds captured the original six kinds. Add an in-memory
    # fail-closed value for the new policy; never rewrite a historical snapshot.
    legacy_kinds = set(CONFIGURATION_KINDS) - {"auto_reject_policy"}
    if set(configurations) == legacy_kinds:
        configurations = {
            **configurations,
            "auto_reject_policy": {
                "kind": "auto_reject_policy", "status": "UNCONFIGURED",
                "revision_id": None, "revision": None, "effective_at": None,
                "configuration_hash": None, "value": None, "signoff": None,
            },
        }
    if set(configurations) != set(CONFIGURATION_KINDS):
        raise ConfigurationValidationError("Round configuration snapshot is incomplete.")

    resolutions: dict[str, tuple[str, dict[str, Any] | None, Mapping[str, Any]]] = {}
    for kind in CONFIGURATION_KINDS:
        entry = configurations.get(kind)
        if not isinstance(entry, Mapping) or entry.get("kind") != kind:
            raise ConfigurationValidationError("Round configuration snapshot has an invalid entry.")
        status = entry.get("status")
        if status not in {"UNCONFIGURED", "DISABLED", "EFFECTIVE"}:
            raise ConfigurationValidationError("Round configuration snapshot has an invalid status.")
        value = entry.get("value")
        if status == "UNCONFIGURED":
            if value is not None or entry.get("configuration_hash") is not None:
                raise ConfigurationValidationError("Unconfigured snapshot entry contains configuration data.")
            resolutions[kind] = (status, None, entry)
            continue
        if not isinstance(value, Mapping):
            raise ConfigurationValidationError("Configured snapshot entry has no value.")
        signoff_configuration_matches = True
        if kind == "approval_policy" and value.get("enabled") is True:
            normalized = _validate_signed_approval_policy_value(
                value, entry.get("signoff"), revision_id=entry["revision_id"],
                configuration_hash=entry["configuration_hash"],
            )
            signoff_configuration_matches = _signoff_matches_configuration_revisions(
                entry.get("signoff"), configurations,
            )
        elif kind == "auto_reject_policy" and value.get("enabled") is True:
            normalized = _validate_signed_auto_reject_policy_value(
                value, entry.get("signoff"), revision_id=entry["revision_id"],
                configuration_hash=entry["configuration_hash"],
            )
            signoff_configuration_matches = _auto_reject_signoff_matches_configuration_revisions(
                entry.get("signoff"), configurations,
            )
        else:
            normalized = validate_configuration_value(kind, value)
        if canonical_configuration_hash(value) != entry.get("configuration_hash"):
            raise ConfigurationValidationError("Round configuration value hash does not match its snapshot.")
        if not isinstance(entry.get("revision_id"), str) or type(entry.get("revision")) is not int or entry["revision"] < 1:
            raise ConfigurationValidationError("Configured snapshot entry has no revision identity.")
        if (_value_is_enabled(kind, normalized) != (status == "EFFECTIVE")):
            is_stale_signed_policy = (
                kind == "approval_policy"
                and normalized.get("enabled") is True
                and status == "DISABLED"
                and not signoff_configuration_matches
            ) or (
                kind == "auto_reject_policy"
                and normalized.get("enabled") is True
                and status == "DISABLED"
                and not signoff_configuration_matches
            )
            if not is_stale_signed_policy:
                raise ConfigurationValidationError("Round configuration status does not match its captured value.")
        resolutions[kind] = (status, normalized, entry)

    approval_status, approval_value, approval_entry = resolutions["approval_policy"]
    base_policy = base_configuration.policy
    approval_revision_id = approval_entry.get("revision_id")
    approval_revision = approval_entry.get("revision")
    policy = replace(
        base_policy,
        snapshot_id=approval_revision_id or base_policy.snapshot_id,
        policy_version=(
            f"AUTH-POLICY-{approval_revision}"
            if approval_revision is not None else base_policy.policy_version
        ),
        auto_approval_policy_enabled=(
            approval_status == "EFFECTIVE"
            and approval_value is not None
            and approval_value.get("enabled") is True
            and _signoff_matches_configuration_revisions(
                approval_entry.get("signoff"), configurations,
            )
        ),
        feasibility_threshold=(
            approval_value["feasibility_score_threshold_exclusive"]
            if approval_value is not None else base_policy.feasibility_threshold
        ),
        media_confidence_threshold=(
            approval_value["media_confidence_threshold"]
            if approval_value is not None else base_policy.media_confidence_threshold
        ),
        feasibility_confidence_threshold=(
            approval_value["feasibility_confidence_threshold"]
            if approval_value is not None else base_policy.feasibility_confidence_threshold
        ),
    )

    media_status, media_value, _media_entry = resolutions["media_policy"]
    if media_status == "EFFECTIVE":
        media_policy = MediaCompliancePolicy.from_dict(media_value)
    elif media_status == "DISABLED":
        media_policy = None
    else:
        media_policy = base_configuration.media_policy

    rubric_status, rubric_value, _rubric_entry = resolutions["strategy_rubric"]
    if rubric_status == "EFFECTIVE":
        expected_weights = {key: weight for key, _label, weight in STRATEGY_CRITERIA}
        configured_weights = {
            item["criterion_id"]: item["weight"] for item in rubric_value["criteria"]
        }
        if configured_weights == expected_weights:
            strategy_rubric = StrategyRubric.from_dict(rubric_value)
            policy_criteria = tuple(Criterion(item.criterion_id, item.weight) for item in strategy_rubric.criteria)
            policy = replace(policy, criteria=policy_criteria)
        else:
            # StrategyRubric cannot represent this value. Keep it only in B's
            # immutable round snapshot; the evaluator will fail before provider work.
            strategy_rubric = None
    elif rubric_status == "DISABLED":
        strategy_rubric = None
    else:
        strategy_rubric = base_configuration.strategy_rubric

    budget_status, budget_value, budget_entry = resolutions["budget"]
    if budget_status == "EFFECTIVE":
        budgets = tuple(BudgetConfiguration(
            configuration_id=budget_entry["revision_id"],
            currency=budget_value["currency"],
            precision=0,
            limit_minor_units=item["limit_minor_units"],
            department=item["department"],
            active=item["active"],
        ) for item in budget_value["limits"])
    elif budget_status == "DISABLED":
        budgets = ()
    else:
        budgets = base_configuration.budgets

    authority_status, authority_value, authority_entry = resolutions["authority"]
    if authority_value is not None:
        authority = AuthoritySnapshot(
            snapshot_id=authority_entry["revision_id"],
            currency=authority_value["currency"],
            auto_limit_minor_units=authority_value["auto_limit_minor_units"],
            allowed_departments=tuple(authority_value["allowed_departments"]),
            checker_id=authority_value["checker_id"],
            policy_owner_id=authority_value["policy_owner_id"],
            budget_authority_id=authority_value["budget_authority_id"],
            active=authority_value["active"] and authority_status == "EFFECTIVE",
        )
    elif authority_status == "UNCONFIGURED":
        authority = base_configuration.authority
    else:
        authority = None

    auto_reject_status, auto_reject_value, auto_reject_entry = resolutions["auto_reject_policy"]
    auto_reject_policy = None
    if (auto_reject_status == "EFFECTIVE" and auto_reject_value is not None
            and auto_reject_value.get("enabled") is True
            and _auto_reject_signoff_matches_configuration_revisions(
                auto_reject_entry.get("signoff"), configurations,
            )):
        from src.backend.domain.policy import AutoRejectPolicy
        signoff = auto_reject_entry["signoff"]
        auto_reject_policy = AutoRejectPolicy.from_dict({
            **auto_reject_value,
            "configuration_hash": auto_reject_entry["configuration_hash"],
            "signoff_source": "AUTHENTICATED_POLICY_OWNER",
            "signed_by": signoff["policy_owner_id"],
            "signed_at": signoff["signed_at"],
        })

    return ApprovalConfiguration(
        policy=policy,
        budgets=budgets,
        authority=authority,
        media_policy=media_policy,
        strategy_rubric=strategy_rubric,
        auto_reject_policy=auto_reject_policy,
        media_model_snapshot=json_value(base_configuration.media_model_snapshot),
        strategy_model_snapshot=json_value(base_configuration.strategy_model_snapshot),
        visual_model_snapshot=json_value(base_configuration.visual_model_snapshot),
    )


def budget_decision_for_snapshot(snapshot: RoundConfigurationSnapshot, department: str, amount_minor_units: str) -> BudgetDecision:
    resolution_data = snapshot.configurations["budget"]
    resolution = ConfigurationResolution(
        kind="budget",
        status=resolution_data["status"],
        revision_id=resolution_data["revision_id"],
        revision=resolution_data["revision"],
        effective_at=datetime.fromisoformat(resolution_data["effective_at"].replace("Z", "+00:00"))
        if resolution_data["effective_at"] else None,
        configuration_hash=resolution_data["configuration_hash"],
        value=resolution_data["value"],
    )
    if resolution.status != "EFFECTIVE":
        state = "DISABLED" if resolution.status == "DISABLED" else "UNCONFIGURED"
        return BudgetDecision("HUMAN_REVIEW_REQUIRED", state, None, amount_minor_units, None, resolution.revision_id, resolution.revision, resolution.configuration_hash)
    return budget_decision(resolution.value, department, amount_minor_units, resolution=resolution)
