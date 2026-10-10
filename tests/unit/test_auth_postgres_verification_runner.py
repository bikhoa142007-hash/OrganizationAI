import os
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "run_auth_postgres_verification.py"
SPEC = importlib.util.spec_from_file_location("auth_postgres_verification_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload
        self.json_called = False

    def json(self):
        self.json_called = True
        return self.payload


def test_concurrent_token_response_evidence_captures_only_status_and_error_code():
    response = FakeResponse(422, {
        "code": "VALIDATION_ERROR",
        "message": "token=synthetic-secret-token must not be recorded",
    })

    evidence = runner._concurrent_token_evidence("token-use-1", response=response)

    assert evidence == {
        "request_id": "token-use-1", "http_status": 422,
        "error_code": "VALIDATION_ERROR", "exception": None,
    }
    assert "synthetic-secret-token" not in repr(evidence)


def test_concurrent_token_success_does_not_try_to_decode_empty_204_body():
    response = FakeResponse(204)

    evidence = runner._concurrent_token_evidence("token-use-2", response=response)

    assert evidence == {
        "request_id": "token-use-2", "http_status": 204,
        "error_code": None, "exception": None,
    }
    assert not response.json_called


def test_concurrent_token_exception_is_redacted_and_has_no_request_url():
    exception = RuntimeError(
        "POST http://testserver/api/auth/activate token=synthetic-token "
        "password=synthetic-password"
    )

    evidence = runner._concurrent_token_evidence(
        "token-use-1", exception=exception,
        sensitive_values=("synthetic-token", "synthetic-password"),
    )

    serialized = repr(evidence)
    assert evidence["exception"]["type"] == "RuntimeError"
    assert "[REDACTED_URL]" in evidence["exception"]["message"]
    assert "synthetic-token" not in serialized
    assert "synthetic-password" not in serialized
    assert "http://testserver" not in serialized


def test_postgres_diagnostics_redact_failing_rows_and_sql_parameters_but_keep_location():
    token_hash = "fc16469c9aede5d72253c2c5fe05722bc2771b3e33d08b23ef3d571a47c004b4"
    diagnostic = (
        "psycopg.errors.CheckViolation: violates check constraint "
        "ck_auth_management_tokens_purpose\n"
        f"DETAIL: Failing row contains (synthetic-row, {token_hash}, UNKNOWN).\n"
        "[SQL: UPDATE auth_management_tokens SET purpose=%(purpose)s]\n"
        f"[parameters: {{'purpose': 'UNKNOWN', 'token_hash': '{token_hash}'}}]\n"
        "  File \"scripts/run_auth_postgres_verification.py\", line 1446, in helper\n"
    )

    safe = runner._redact(diagnostic, [])

    assert "ck_auth_management_tokens_purpose" in safe
    assert "Failing row contents redacted" in safe
    assert "[SQL: [REDACTED]" in safe
    assert "[parameters: [REDACTED]" in safe
    assert "scripts/run_auth_postgres_verification.py\", line 1446" in safe
    assert token_hash not in safe
    assert "synthetic-row" not in safe


def test_purpose_constraint_gate_accepts_only_expected_postgres_check_violation():
    from contextlib import nullcontext
    from types import SimpleNamespace

    from sqlalchemy.exc import IntegrityError

    from src.backend.db.models import AuthManagementToken

    class CheckViolation:
        def __init__(self, constraint_name):
            self.sqlstate = "23514"
            self.diag = SimpleNamespace(constraint_name=constraint_name)

    class FakeSession:
        def __init__(self, constraint_name):
            self.constraint_name = constraint_name

        def begin_nested(self):
            return nullcontext()

        def execute(self, _statement):
            original = CheckViolation(self.constraint_name)
            raise IntegrityError("synthetic update", {}, original)

        def expire_all(self):
            return None

        def get(self, _model, _token_id):
            return SimpleNamespace(purpose="RESET", consumed_at=None)

    result = runner._verify_management_token_purpose_constraint(
        FakeSession("ck_auth_management_tokens_purpose"), AuthManagementToken, "synthetic-id",
    )
    assert result["status"] == "PASS"
    assert result["sqlstate"] == "23514"
    assert result["constraint_name"] == "ck_auth_management_tokens_purpose"

    with pytest.raises(AssertionError, match="unexpected database constraint"):
        runner._verify_management_token_purpose_constraint(
            FakeSession("ck_auth_management_tokens_user_id_fkey"), AuthManagementToken, "synthetic-id",
        )


def test_concurrent_token_evidence_keeps_http_status_when_exception_is_also_present():
    response = FakeResponse(503, {"code": "UNAVAILABLE", "message": "internal details"})
    exception = RuntimeError("request failed for http://testserver/private?token=synthetic-token")

    evidence = runner._concurrent_token_evidence(
        "token-use-2", response=response, exception=exception,
        sensitive_values=("synthetic-token",),
    )

    assert evidence["http_status"] == 503
    assert evidence["error_code"] == "UNAVAILABLE"
    assert evidence["exception"]["type"] == "RuntimeError"
    assert "synthetic-token" not in repr(evidence)
    assert "http://testserver" not in repr(evidence)


def test_employee_admin_login_payload_matches_login_endpoint_json_openapi_and_schema():
    from src.backend.api.app import create_app
    from src.backend.api.auth_schemas import LoginRequest
    from src.backend.api.dependencies import Settings
    from src.backend.db.models import User

    password = "0123456789abcdef" * 4
    payload = runner._employee_admin_login_payload("0123abcd", "admin", password)
    validated = LoginRequest.model_validate(payload)
    openapi = create_app(Settings(app_env="demo")).openapi()
    operation = openapi["paths"]["/api/auth/login"]["post"]
    body = operation["requestBody"]
    media_types = body["content"]
    schema_ref = media_types["application/json"]["schema"]["$ref"]
    schema_name = schema_ref.rsplit("/", 1)[1]
    login_schema = openapi["components"]["schemas"][schema_name]

    assert payload == {"identifier": "pgemp_0123abcd_admin", "password": password}
    assert validated.identifier == "pgemp_0123abcd_admin"
    assert validated.password == password
    assert set(login_schema["properties"]) == {"identifier", "password", "remember_me"}
    assert set(login_schema["required"]) == {"identifier", "password"}
    assert "application/x-www-form-urlencoded" not in media_types
    assert len(payload["identifier"]) <= User.__table__.c.username.type.length
    assert len(payload["identifier"]) <= login_schema["properties"]["identifier"]["maxLength"]
    assert len(password) <= login_schema["properties"]["password"]["maxLength"]


def test_employee_and_account_create_contract_keeps_profile_id_distinct_from_account_id():
    from uuid import uuid4

    from src.backend.api.auth_workflow_schemas import (
        EmployeeAccountCreateResponse, WorkflowEmployeeResponse,
    )

    employee_id = str(uuid4())
    account_id = str(uuid4())
    employee_payload = {
        "id": employee_id, "account_id": None, "user_code": "SYNTHETIC-EMP",
        "username": None, "display_name": "Synthetic Employee", "email": "employee@example.invalid",
        "phone": None, "department": None, "job_title": None, "employment_start_date": None,
        "employment_status": "ACTIVE", "status": None, "account_status": None,
        "roles": [], "effective_permissions": [],
    }
    account_payload = {
        "employee": {
            **employee_payload, "account_id": account_id, "username": "synthetic-account",
            "status": "DISABLED", "account_status": "PENDING_ACTIVATION",
        },
        "handover_token": "synthetic-only-handover-token-value-123456",
        "purpose": "ACTIVATE", "expires_at": "2026-10-10T14:00:00Z",
    }

    created_employee = WorkflowEmployeeResponse.model_validate(employee_payload)
    created_account = EmployeeAccountCreateResponse.model_validate(account_payload)
    resolved_employee_id, resolved_account_id = runner._employee_account_ids(
        created_employee.model_dump(mode="json"), created_account.model_dump(mode="json"),
    )

    assert resolved_employee_id == employee_id
    assert resolved_account_id == account_id
    assert resolved_employee_id != resolved_account_id


def test_account_lookup_uses_linked_account_id_not_employee_profile_id():
    from uuid import UUID, uuid4

    employee_id = str(uuid4())
    account_id = str(uuid4())
    expected_account = object()

    class IndependentSession:
        def __init__(self):
            self.lookups = []

        def get(self, model, identity):
            self.lookups.append((model, identity))
            return expected_account if identity == UUID(account_id) else None

    marker_model = object()
    session = IndependentSession()

    actual = runner._require_account_visible_from_session(
        session, marker_model, employee_id=employee_id, account_id=account_id,
        label="synthetic race account",
    )

    assert actual is expected_account
    assert session.lookups == [(marker_model, UUID(account_id))]
    assert session.lookups[0][1] != UUID(employee_id)


def test_employee_admin_database_override_resolves_real_login_request_parameter():
    from threading import Lock

    from fastapi.dependencies.utils import get_dependant

    from src.backend.api.app import create_app
    from src.backend.api.auth import get_auth_db, router as auth_router
    from src.backend.api.dependencies import Settings

    def factory():
        raise AssertionError("The dependency graph check must not open a database session.")

    app = create_app(Settings(app_env="demo"))
    override = runner._make_employee_admin_database_dependency(factory, {}, {}, Lock())
    app.dependency_overrides[get_auth_db] = override
    runner._install_employee_admin_diagnostic_handlers(
        app, {}, Lock(), {}, {},
    )
    login_route = next(route for route in auth_router.routes if route.path == "/api/auth/login")
    login_db_dependency = next(
        dependency for dependency in login_route.dependant.dependencies
        if dependency.call is get_auth_db
    )
    resolved_override = app.dependency_overrides[login_db_dependency.call]
    # FastAPI rebuilds the dependant from the installed override during request
    # dependency resolution; this is the stage that misclassified `request`.
    override_dependant = get_dependant(
        path=login_db_dependency.path,
        call=resolved_override,
        name=login_db_dependency.name,
        parent_oauth_scopes=login_db_dependency.parent_oauth_scopes,
        scope=login_db_dependency.scope,
    )

    assert resolved_override is override
    assert override_dependant.request_param_name == "request"
    assert not override_dependant.query_params
    assert login_route.dependant.request_param_name == "request"


def test_safe_validation_diagnostics_keep_only_location_type_and_redacted_message():
    secret = "synthetic-login-password-secret"
    details = runner._safe_validation_details([{
        "loc": ("body", "password"),
        "type": "string_too_short",
        "msg": f"Invalid value {secret}",
        "input": secret,
    }], sensitive_values=(secret,))

    assert details == [{
        "loc": ["body", "password"],
        "type": "string_too_short",
        "message": "Invalid value [REDACTED]",
    }]
    assert secret not in repr(details)


def test_synthetic_login_failure_reports_status_code_and_safe_validation_only():
    secret = "synthetic-login-password-secret"
    response = FakeResponse(422, {
        "code": "VALIDATION_ERROR",
        "message": f"must not be copied: {secret}",
    })
    safe_details = [{"loc": ["body", "password"], "type": "string_too_short", "message": "Too short"}]

    with pytest.raises(AssertionError) as error:
        runner._require_synthetic_login(response, "synthetic admin login", validation_details=safe_details)

    message = str(error.value)
    assert "HTTP 422" in message
    assert '"error_code": "VALIDATION_ERROR"' in message
    assert '"loc": ["body", "password"]' in message
    assert secret not in message
    assert "must not be copied" not in message


def test_employee_page_parser_checks_status_and_paged_envelope_before_items():
    response = FakeResponse(200, {
        "items": [{
            "id": "employee-1", "account_id": "user-1", "user_code": "U1", "username": "maker",
            "display_name": "Maker", "email": None, "phone": None,
            "department": None, "job_title": None, "employment_start_date": None,
            "employment_status": "ACTIVE", "status": "ACTIVE", "account_status": "ACTIVE", "roles": ["MAKER"],
            "effective_permissions": ["MARKETING_PLAN_CREATE"],
        }, {
            "id": "employee-2", "account_id": None, "user_code": "U2", "username": None,
            "display_name": "Profile without Login", "email": None, "phone": None,
            "department": None, "job_title": None, "employment_start_date": None,
            "employment_status": "ACTIVE", "status": None, "account_status": None, "roles": [],
            "effective_permissions": [],
        }],
        "offset": 0, "limit": 1, "total": 1,
    })

    page = runner._employee_page_payload(response, "admin employee page")

    assert page["total"] == 1
    assert page["items"][0]["id"] == "employee-1"
    assert page["items"][1]["account_status"] is None
    assert response.json_called


def test_employee_page_parser_rejects_non_200_before_decoding_error_body():
    response = FakeResponse(500, {"detail": "server error"})

    with pytest.raises(AssertionError, match="HTTP 200"):
        runner._employee_page_payload(response, "admin employee page")

    assert not response.json_called


def test_employee_page_parser_rejects_non_object_items():
    response = FakeResponse(200, {"items": ["malformed"], "offset": 0, "limit": 1, "total": 1})

    with pytest.raises(AssertionError, match=r"items\[0\].*object"):
        runner._employee_page_payload(response, "admin employee page")


def test_checker_list_parser_requires_list_of_checker_objects():
    response = FakeResponse(200, ["checker-id"])

    with pytest.raises(AssertionError, match="checker list item 0.*object"):
        runner._checker_list_payload(response, "Maker checker picker")


def test_checker_list_parser_checks_http_error_before_reading_error_envelope():
    response = FakeResponse(403, {"detail": "Maker role required"})

    with pytest.raises(AssertionError, match="HTTP 200"):
        runner._checker_list_payload(response, "Maker checker picker")

    assert not response.json_called


def test_only_known_starlette_testclient_deprecation_warning_is_allowed():
    known_warning = (
        "C:\\venv\\site-packages\\fastapi\\testclient.py:1: StarletteDeprecationWarning: "
        "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.\n"
        "  from starlette.testclient import TestClient as TestClient  # noqa\n"
    )

    assert runner._strip_known_helper_warnings(known_warning) == ""
    assert runner._strip_known_helper_warnings(known_warning + "unexpected failure\n") == "unexpected failure\n"


def test_docker_named_pipe_permission_failure_is_classified_as_blocked_precheck():
    assert runner._is_docker_access_blocked(
        "permission denied while trying to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine"
    )
    assert not runner._is_docker_access_blocked("PostgreSQL migration failed with an invalid column")


def test_directory_helper_imports_project_from_outside_repo_with_repo_root_argument():
    with tempfile.TemporaryDirectory(prefix="auth postgres helper outside repo ") as temp_dir:
        assert not Path(temp_dir).resolve().is_relative_to(ROOT)
        assert " " in temp_dir
        helper_path = Path(temp_dir) / "run_auth_postgres_verification.py"
        shutil.copy2(RUNNER_PATH, helper_path)

        helper_env = os.environ.copy()
        helper_env["DATABASE_URL"] = (
            "postgresql+psycopg://synthetic:synthetic@127.0.0.1:1/synthetic"
            "?connect_timeout=1"
        )
        helper_env["AUTH_SEED_PASSWORD"] = "synthetic-only-password"
        completed = subprocess.run(
            [
                sys.executable,
                str(helper_path),
                "--repo-root",
                str(ROOT),
                "--helper-mode",
                "directory",
            ],
            cwd=temp_dir,
            env=helper_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        output = completed.stdout + completed.stderr
        assert "ModuleNotFoundError: No module named 'src'" not in output
        assert "OperationalError" in output, output
        assert "Traceback (most recent call last)" in output, output
        assert "_verify_directory" in output, output
        assert "synthetic-only-password" not in output
        assert "postgresql+psycopg://" not in output
