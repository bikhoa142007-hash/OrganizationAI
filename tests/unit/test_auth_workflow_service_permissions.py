from uuid import uuid4

import pytest

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application import auth_workflow
from src.backend.application.workflow import ApplicationError


def _principal(role: str, permissions: tuple[str, ...] = ()) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=uuid4(),
        user_code="TEST-USER",
        username="test-user",
        email=None,
        phone=None,
        display_name="Test User",
        status="ACTIVE",
        roles=(role,),
        permissions=permissions,
    )


def _assert_forbidden(call) -> None:
    with pytest.raises(ApplicationError) as error:
        call()
    assert error.value.code == "FORBIDDEN"


def test_create_service_requires_catalog_permission_before_database_access():
    _assert_forbidden(lambda: auth_workflow.create_plan(
        None, _principal("MAKER"), {}, None, "permission-create",
    ))


def test_plan_list_requires_read_permission_before_database_access():
    _assert_forbidden(lambda: auth_workflow.list_plans(
        None, _principal("MAKER"), "permission-list",
    ))


def test_checker_review_queue_requires_assigned_review_permission():
    _assert_forbidden(lambda: auth_workflow.list_plans(
        None, _principal("CHECKER"), "permission-review-queue", reviews_only=True,
    ))


def test_admin_plan_list_requires_view_all_permission():
    _assert_forbidden(lambda: auth_workflow.list_plans(
        None, _principal("ADMIN", ("MARKETING_PLAN_READ",)), "permission-admin-list",
    ))


def test_plan_detail_requires_history_permission_even_when_plan_read_is_granted():
    _assert_forbidden(lambda: auth_workflow.get_plan(
        None, _principal("MAKER", ("MARKETING_PLAN_READ",)), uuid4(), "permission-detail",
    ))


def test_plan_update_requires_owner_edit_permission_before_database_access():
    _assert_forbidden(lambda: auth_workflow.update_plan(
        None, _principal("MAKER"), uuid4(), {}, None, False, 0, "permission-update",
    ))


def test_attachment_upload_requires_attachment_permission_before_file_validation():
    _assert_forbidden(lambda: auth_workflow.upload_attachment(
        None, _principal("MAKER"), uuid4(), "image.png", "image/png", b"",
        0, "permission-upload",
    ))


def test_submission_requires_submit_permission_before_database_access():
    _assert_forbidden(lambda: auth_workflow.submit_plan(
        None, _principal("MAKER"), uuid4(), 0, "permission-submit",
        provider_name="MOCK_VLM", model_version=None, configuration=None,
    ))


@pytest.mark.parametrize(
    ("action", "reason", "permission"),
    [
        ("APPROVED", "Reviewed.", "MARKETING_APPROVE"),
        ("REJECTED", "Needs revision.", "MARKETING_REJECT"),
    ],
)
def test_checker_decision_service_requires_action_specific_permission(action, reason, permission):
    _assert_forbidden(lambda: auth_workflow.decide_plan(
        None, _principal("CHECKER"), uuid4(), 1, action, reason, "Override reason.",
        f"permission-{permission}",
    ))


def test_audit_service_requires_catalog_permission_even_for_admin_role():
    _assert_forbidden(lambda: auth_workflow.list_audit_events(
        None, _principal("ADMIN"), "permission-audit",
    ))


def test_attachment_read_requires_plan_read_permission_before_database_access():
    _assert_forbidden(lambda: auth_workflow.get_attachment(
        None, _principal("MAKER"), uuid4(), uuid4(), "permission-attachment-read",
    ))
