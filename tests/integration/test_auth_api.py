from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import jwt
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.api.app import create_app
from src.backend.api.dependencies import Settings
from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, require_any_role, require_role
from src.backend.api.auth_rate_limit import AuthAttemptLimiter
from src.backend.db.base import Base
from src.backend.db.models.role import Role, UserRole
from src.backend.db.models.user import User
from src.backend.db.security import hash_password


@pytest.fixture
def auth_client(monkeypatch) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    monkeypatch.setenv("JWT_SECRET", "test-only-auth-secret-that-is-at-least-32-bytes")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(Role(id=uuid4(), code="MAKER", name="Maker", description=None))
    app = create_app(Settings(app_env="demo", cors_origins=("http://localhost:5173",)))

    def override_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_auth_db] = override_db

    @app.get("/test/maker")
    def maker_only(user: AuthenticatedPrincipal = Depends(require_role("MAKER"))):
        return {"user_code": user.user_code}

    @app.get("/test/checker-or-admin")
    def checker_or_admin(user: AuthenticatedPrincipal = Depends(require_any_role("CHECKER", "ADMIN"))):
        return {"user_code": user.user_code}

    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def create_user(factory: sessionmaker[Session], *, user_code: str, email: str | None,
                password: str = "Local-demo-password-123", role_codes: tuple[str, ...] = ("MAKER",),
                status: str = "ACTIVE", username: str | None = None,
                phone: str | None = None) -> User:
    with factory.begin() as session:
        roles = {}
        for code in {"MAKER", "CHECKER", "ADMIN"}:
            role = session.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(id=uuid4(), code=code, name=code.title(), description=None)
                session.add(role)
            roles[code] = role
        user = User(id=uuid4(), user_code=user_code, username=username or (email or user_code).split("@")[0].lower(),
                    email=email, phone=phone,
                    password_hash=hash_password(password), display_name="Demo User", status=status)
        session.add(user)
        session.flush()
        for code in role_codes:
            session.add(UserRole(user_id=user.id, role_id=roles[code].id, assigned_by=None))
        session.flush()
        session.expunge(user)
    return user


def test_login_by_user_code_sets_http_only_cookie_and_me_returns_database_roles(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")

    response = client.post("/api/auth/login", json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })

    assert response.status_code == 200
    assert response.json() == {"user": {
        "id": response.json()["user"]["id"], "user_code": "USR-000001",
        "username": "maker", "email": "maker@example.com", "phone": None,
        "display_name": "Demo User", "status": "ACTIVE", "roles": ["MAKER"],
    }}
    assert "access_token" not in response.json()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == response.json()


def test_public_auth_configuration_reports_registration_without_exposing_credentials(auth_client, monkeypatch):
    client, _ = auth_client

    enabled = client.get("/api/auth/config")
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
    disabled = client.get("/api/auth/config")

    assert enabled.status_code == 200
    assert enabled.json() == {"registration_enabled": True}
    assert disabled.status_code == 200
    assert disabled.json() == {"registration_enabled": False}


def test_registration_is_rate_limited_by_client_ip(auth_client):
    client, _ = auth_client
    client.app.state.auth_attempt_limiter = AuthAttemptLimiter(register_per_ip=1)
    payload = {
        "username": "first.maker", "contact": "first@example.com",
        "password": "New-local-password-123",
    }

    first = client.post("/api/auth/register", json=payload)
    second = client.post("/api/auth/register", json={
        **payload, "username": "second.maker", "contact": "second@example.com",
    })

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"
    assert "New-local-password-123" not in second.text


def test_auth_database_readiness_uses_the_configured_session(auth_client):
    client, _ = auth_client

    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json()["auth_database"] == "postgresql"


def test_login_by_email_is_case_insensitive(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")

    response = client.post("/api/auth/login", json={
        "identifier": "MAKER@EXAMPLE.COM", "password": "Local-demo-password-123",
    })

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "maker@example.com"


def test_login_by_username_is_case_insensitive(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com", username="maker.one")

    response = client.post("/api/auth/login", json={
        "identifier": "MAKER.ONE", "password": "Local-demo-password-123",
    })

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "maker.one"


def test_register_by_email_normalizes_values_and_assigns_only_maker(auth_client):
    client, factory = auth_client

    response = client.post("/api/auth/register", json={
        "username": "  Maker.One ", "contact": " Maker@Example.COM ",
        "password": "New-local-password-123",
    })

    assert response.status_code == 201
    account = response.json()["user"]
    assert account["username"] == "maker.one"
    assert account["email"] == "maker@example.com"
    assert account["phone"] is None
    assert account["user_code"].startswith("USR-")
    assert account["roles"] == ["MAKER"]
    assert "set-cookie" not in response.headers
    with factory() as session:
        stored = session.scalar(select(User).where(User.username == "maker.one"))
        assert stored is not None
        assert stored.password_hash.startswith("$argon2id$")
        assert stored.password_hash != "New-local-password-123"


def test_register_by_international_phone_normalizes_contact_and_phone_cannot_login(auth_client):
    client, factory = auth_client

    response = client.post("/api/auth/register", json={
        "username": "phone.maker", "contact": "+84 (90) 123-4567",
        "password": "New-local-password-123",
    })

    assert response.status_code == 201
    account = response.json()["user"]
    assert account["username"] == "phone.maker"
    assert account["email"] is None
    assert account["phone"] == "+84901234567"
    assert account["roles"] == ["MAKER"]

    by_username = client.post("/api/auth/login", json={
        "identifier": "phone.maker", "password": "New-local-password-123",
    })
    client.post("/api/auth/logout")
    by_phone = client.post("/api/auth/login", json={
        "identifier": "+84901234567", "password": "New-local-password-123",
    })
    assert by_username.status_code == 200
    assert by_phone.status_code == 401
    with factory() as session:
        assert session.scalar(select(User).where(User.username == "phone.maker")).email is None


def test_database_requires_exactly_one_email_or_phone_contact(auth_client):
    _, factory = auth_client

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(User(
                user_code="USR-INVALID-CONTACT", username="invalid.contact",
                email="both@example.com", phone="+84901234567",
                password_hash=hash_password("Local-demo-password-123"),
                display_name="Invalid Contact", status="ACTIVE",
            ))


@pytest.mark.parametrize("duplicate_field", ["username", "email", "phone"])
def test_database_unique_constraints_protect_registration_races(auth_client, duplicate_field):
    _, factory = auth_client
    first = {
        "user_code": "USR-RACE-000001", "username": "race.first",
        "email": "race.first@example.com", "phone": None,
    }
    second = {
        "user_code": "USR-RACE-000002", "username": "race.second",
        "email": "race.second@example.com", "phone": None,
    }
    if duplicate_field == "phone":
        first["email"] = second["email"] = None
        first["phone"] = second["phone"] = "+84901234567"
    else:
        first[duplicate_field] = second[duplicate_field]

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            for values in (first, second):
                session.add(User(
                    **values,
                    password_hash=hash_password("Local-demo-password-123"),
                    display_name=values["username"],
                    status="ACTIVE",
                ))


def test_registration_rejects_client_role_and_invalid_contact(auth_client):
    client, factory = auth_client

    elevated = client.post("/api/auth/register", json={
        "username": "unsafe.user", "contact": "unsafe@example.com",
        "password": "New-local-password-123", "role": "ADMIN",
    })
    bad_phone = client.post("/api/auth/register", json={
        "username": "bad.phone", "contact": "0901234567",
        "password": "New-local-password-123",
    })

    assert elevated.status_code == 422
    assert bad_phone.status_code == 422
    with factory() as session:
        assert session.scalar(select(User).where(User.username == "unsafe.user")) is None


def test_registration_rejects_duplicate_normalized_username_or_contact(auth_client):
    client, _ = auth_client

    first = client.post("/api/auth/register", json={
        "username": "Unique.User", "contact": "unique@example.com",
        "password": "New-local-password-123",
    })
    duplicate = client.post("/api/auth/register", json={
        "username": "unique.user", "contact": "other@example.com",
        "password": "New-local-password-123",
    })
    contact_duplicate = client.post("/api/auth/register", json={
        "username": "other.user", "contact": " UNIQUE@EXAMPLE.COM ",
        "password": "New-local-password-123",
    })

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert contact_duplicate.status_code == 409
    assert duplicate.json()["message"] == contact_duplicate.json()["message"]


def test_registration_rejects_duplicate_normalized_phone(auth_client):
    client, _ = auth_client
    first = client.post("/api/auth/register", json={
        "username": "phone.first", "contact": "+84 (90) 123-4567",
        "password": "New-local-password-123",
    })
    duplicate = client.post("/api/auth/register", json={
        "username": "phone.second", "contact": "+84901234567",
        "password": "New-local-password-123",
    })

    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_registration_rejects_untrusted_origin_and_can_be_disabled(auth_client, monkeypatch):
    client, factory = auth_client
    rejected_origin = client.post("/api/auth/register", headers={"Origin": "https://untrusted.example"}, json={
        "username": "origin.user", "contact": "origin@example.com",
        "password": "New-local-password-123",
    })
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
    disabled = client.post("/api/auth/register", json={
        "username": "disabled.user", "contact": "disabled@example.com",
        "password": "New-local-password-123",
    })

    assert rejected_origin.status_code == 403
    assert disabled.status_code == 403
    with factory() as session:
        assert session.scalar(select(User).where(User.username == "origin.user")) is None
        assert session.scalar(select(User).where(User.username == "disabled.user")) is None


def test_remember_me_sets_a_longer_persistent_cookie(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")

    session_login = client.post("/api/auth/login", json={
        "identifier": "maker", "password": "Local-demo-password-123",
    })
    session_cookie = session_login.headers["set-cookie"].lower()
    session_token = client.cookies.get("organizationai_access_token")
    client.post("/api/auth/logout")
    remembered_login = client.post("/api/auth/login", json={
        "identifier": "maker", "password": "Local-demo-password-123", "remember_me": True,
    })
    remembered_cookie = remembered_login.headers["set-cookie"].lower()
    remembered_token = client.cookies.get("organizationai_access_token")
    settings = "test-only-auth-secret-that-is-at-least-32-bytes"
    session_claims = jwt.decode(session_token, settings, algorithms=["HS256"])
    remembered_claims = jwt.decode(remembered_token, settings, algorithms=["HS256"])

    assert "max-age=" not in session_cookie
    assert "max-age=1209600" in remembered_cookie
    assert 1700 <= session_claims["exp"] - session_claims["iat"] <= 1800
    assert 1209500 <= remembered_claims["exp"] - remembered_claims["iat"] <= 1209600


def test_authenticated_postgres_user_does_not_become_a_demo_workflow_actor(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")
    login = client.post("/api/auth/login", json={
        "identifier": "maker", "password": "Local-demo-password-123",
    })
    assert login.status_code == 200

    response = client.get("/api/plans")

    assert response.status_code == 401


def test_wrong_password_and_unknown_user_return_same_unauthorized_error(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")
    payloads = [
        {"identifier": "USR-000001", "password": "incorrect-password"},
        {"identifier": "USR-999999", "password": "incorrect-password"},
    ]

    responses = [client.post("/api/auth/login", json=payload) for payload in payloads]

    assert [response.status_code for response in responses] == [401, 401]
    assert responses[0].json()["code"] == responses[1].json()["code"]
    assert responses[0].json()["message"] == responses[1].json()["message"]
    assert responses[0].json()["message"] == "Invalid credentials."


def test_disabled_user_cannot_login(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com", status="DISABLED")

    response = client.post("/api/auth/login", json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })

    assert response.status_code == 401
    assert response.json()["message"] == "Invalid credentials."


def test_me_requires_authentication(auth_client):
    client, _ = auth_client

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_and_expired_cookie_sessions(auth_client):
    client, _ = auth_client
    client.cookies.set("organizationai_access_token", "not-a-jwt")
    invalid = client.get("/api/auth/me")
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode({
        "sub": str(uuid4()), "iss": "organizationai",
        "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1),
    }, "test-only-auth-secret-that-is-at-least-32-bytes", algorithm="HS256")
    client.cookies.set("organizationai_access_token", expired_token)
    expired = client.get("/api/auth/me")

    assert invalid.status_code == 401
    assert expired.status_code == 401


def test_me_returns_all_roles_and_backend_role_dependency_enforces_them(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com",
                role_codes=("MAKER", "CHECKER"))
    client.post("/api/auth/login", json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })

    assert client.get("/api/auth/me").json()["user"]["roles"] == ["CHECKER", "MAKER"]
    assert client.get("/test/maker").status_code == 200
    assert client.get("/test/checker-or-admin").status_code == 200

    checker = create_user(factory, user_code="USR-000002", email="checker@example.com",
                          role_codes=("CHECKER",))
    client.cookies.clear()
    client.post("/api/auth/login", json={
        "identifier": checker.user_code, "password": "Local-demo-password-123",
    })
    assert client.get("/test/maker").status_code == 403
    assert client.get("/test/checker-or-admin").status_code == 200


def test_database_stores_argon2id_hash_and_api_never_returns_it(auth_client):
    client, factory = auth_client
    user = create_user(factory, user_code="USR-000001", email="maker@example.com")

    with factory() as session:
        stored = session.get(User, user.id)
    assert stored.password_hash.startswith("$argon2id$")
    assert stored.password_hash != "Local-demo-password-123"

    response = client.post("/api/auth/login", json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })
    assert "password_hash" not in str(response.json())


def test_logout_clears_the_auth_cookie(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")
    client.post("/api/auth/login", json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })
    assert client.get("/api/auth/me").status_code == 200

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_browser_login_rejects_untrusted_origin(auth_client):
    client, factory = auth_client
    create_user(factory, user_code="USR-000001", email="maker@example.com")

    response = client.post("/api/auth/login", headers={"Origin": "https://untrusted.example"}, json={
        "identifier": "USR-000001", "password": "Local-demo-password-123",
    })

    assert response.status_code == 403


def test_missing_postgres_auth_configuration_fails_closed_with_service_status(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-only-auth-secret-that-is-at-least-32-bytes")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app(Settings(app_env="demo", cors_origins=("http://localhost:5173",)))

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={
            "identifier": "maker", "password": "Local-demo-password-123",
        })

    assert response.status_code == 503
    assert response.json()["message"] == "Authentication database is not configured."
