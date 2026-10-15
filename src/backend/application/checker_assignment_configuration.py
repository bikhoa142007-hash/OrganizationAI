from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.application.approval_configuration import (
    lock_configuration_registry,
    resolve_configuration_kind,
)
from src.backend.application.role_admin import effective_role_filter
from src.backend.db.models.employee import EmployeeProfile
from src.backend.db.models.user import User


@dataclass(frozen=True)
class CheckerAssignmentResult:
    checker_id: UUID | None
    eligible: bool
    status: Literal["CONFIGURED", "UNCONFIGURED", "NO_ELIGIBLE_CHECKER"]
    configuration_revision_id: str | None
    configuration_revision: int | None
    configuration_hash: str | None
    source: Literal["DEFAULT", "MAKER_SELECTED", "EXPLICIT_UNCONFIGURED", "NONE"]
    reason: str

    def as_dict(self) -> dict:
        return {
            "checker_id": str(self.checker_id) if self.checker_id else None,
            "eligible": self.eligible,
            "status": self.status,
            "configuration_revision_id": self.configuration_revision_id,
            "configuration_revision": self.configuration_revision,
            "configuration_hash": self.configuration_hash,
            "source": self.source,
            "reason": self.reason,
        }


def _eligible_checker(session: Session, checker_id: UUID, *, lock: bool = False) -> bool:
    query = (
        select(User.id)
        .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
        .where(
            User.id == checker_id,
            User.status == "ACTIVE",
            User.activation_pending.is_(False),
            User.employment_status == "ACTIVE",
            EmployeeProfile.employment_status == "ACTIVE",
            effective_role_filter("CHECKER"),
        )
    )
    if lock:
        query = query.with_for_update()
    return session.scalar(query) is not None


def validate_checker_assignment_value(
    session: Session,
    value: dict,
    *,
    lock: bool = False,
) -> None:
    """Verify configured defaults against active account, employee and Checker role."""
    for entry in value.get("defaults", []):
        checker_id = UUID(entry["checker_id"])
        if not _eligible_checker(session, checker_id, lock=lock):
            raise ValueError(
                f"Default Checker for {entry['department']} is not an active employee with Checker authority."
            )


def validate_authority_value(session: Session, value: dict, *, lock: bool = False) -> None:
    """Validate authority actors are active employees without granting any role."""
    checker_id = UUID(value["checker_id"]) if value.get("checker_id") else None
    if checker_id is not None and not _eligible_checker(session, checker_id, lock=lock):
        raise ValueError("Authority Checker must be an active employee with Checker authority.")
    for field in ("policy_owner_id", "budget_authority_id"):
        user_text = value.get(field)
        if user_text is None:
            continue
        user_id = UUID(user_text)
        query = (
            select(User.id)
            .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
            .where(
                User.id == user_id,
                User.status == "ACTIVE",
                User.activation_pending.is_(False),
                User.employment_status == "ACTIVE",
                EmployeeProfile.employment_status == "ACTIVE",
            )
        )
        if lock:
            query = query.with_for_update()
        if session.scalar(query) is None:
            raise ValueError(f"{field} must reference an active employee account.")


def resolve_checker_assignment(
    session: Session,
    department_id: str | None,
    maker_id: UUID,
    selected_checker_id: UUID | None,
    effective_at: datetime,
    *,
    lock_eligible_checker: bool = False,
    lock_configuration: bool = False,
) -> CheckerAssignmentResult:
    """Resolve the configured default or an explicitly permitted department choice.

    This function never infers a substitute Checker from the employee catalog. An
    absent revision or department default fails closed, including for an explicit
    Checker selection.
    """
    if lock_configuration:
        lock_configuration_registry(session)
    resolution = resolve_configuration_kind(session, "checker_assignment", effective_at)
    metadata = {
        "configuration_revision_id": resolution.revision_id,
        "configuration_revision": resolution.revision,
        "configuration_hash": resolution.configuration_hash,
    }

    if resolution.status == "UNCONFIGURED":
        return CheckerAssignmentResult(
            None, False, "UNCONFIGURED", **metadata, source="NONE",
            reason="No effective Checker assignment configuration exists for this department.",
        )

    if resolution.status != "EFFECTIVE" or not department_id:
        return CheckerAssignmentResult(
            None, False, "NO_ELIGIBLE_CHECKER", **metadata, source="NONE",
            reason="No active Checker assignment is effective for this department.",
        )

    value = resolution.value or {}
    match = next((item for item in value.get("defaults", []) if item.get("department") == department_id), None)
    default_id = UUID(match["checker_id"]) if match else None
    may_choose = value.get("maker_may_select_other") is True

    if default_id is None:
        return CheckerAssignmentResult(
            None, False, "NO_ELIGIBLE_CHECKER", **metadata, source="NONE",
            reason="No default Checker is configured for this department.",
        )

    if selected_checker_id is None:
        candidate_id = default_id
        source: Literal["DEFAULT", "MAKER_SELECTED", "EXPLICIT_UNCONFIGURED", "NONE"] = "DEFAULT" if candidate_id else "NONE"
    elif selected_checker_id == default_id:
        candidate_id = default_id
        source = "DEFAULT"
    elif may_choose:
        candidate_id = selected_checker_id
        source = "MAKER_SELECTED"
    else:
        return CheckerAssignmentResult(
            None, False, "NO_ELIGIBLE_CHECKER", **metadata, source="NONE",
            reason="The effective assignment policy does not allow the selected Checker.",
        )

    if candidate_id is None or candidate_id == maker_id or not _eligible_checker(
        session, candidate_id, lock=lock_eligible_checker,
    ):
        return CheckerAssignmentResult(
            None, False, "NO_ELIGIBLE_CHECKER", **metadata, source="NONE",
            reason="The configured Checker is missing, inactive, lacks Checker role, or is the Maker.",
        )

    return CheckerAssignmentResult(
        candidate_id, True, "CONFIGURED", **metadata, source=source,
        reason="The Checker matches the effective department assignment policy.",
    )
