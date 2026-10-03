from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import re
from secrets import token_hex
import unicodedata
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from src.backend.application.workflow import ApplicationError
from src.backend.db.models import Role, User, UserRole
from src.backend.db.security import (
    dummy_password_hash,
    hash_password,
    password_hash_needs_rehash,
    verify_password,
)
from src.backend.db.session import get_db
from .auth_schemas import AuthResponse, AuthenticatedUser, LoginRequest, RegisterRequest

AUTH_COOKIE_NAME = "organizationai_access_token"
TOKEN_ISSUER = "organizationai"
INVALID_CREDENTIALS = "Invalid credentials."
router = APIRouter(prefix="/api/auth", tags=["authentication"])


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    access_token_minutes: int
    remember_token_days: int
    cookie_secure: bool

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        secret = os.getenv("JWT_SECRET", "")
        if len(secret.encode("utf-8")) < 32 or secret.lower().startswith(("replace-", "change-me")):
            raise ValueError("JWT_SECRET must be a non-placeholder secret of at least 32 bytes.")
        try:
            expires = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30"))
        except ValueError as exc:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES must be an integer.") from exc
        if not 1 <= expires <= 1440:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES must be between 1 and 1440.")
        try:
            remember_days = int(os.getenv("AUTH_REMEMBER_TOKEN_DAYS", "14"))
        except ValueError as exc:
            raise ValueError("AUTH_REMEMBER_TOKEN_DAYS must be an integer.") from exc
        if not 1 <= remember_days <= 90:
            raise ValueError("AUTH_REMEMBER_TOKEN_DAYS must be between 1 and 90.")

        secure_value = os.getenv("AUTH_COOKIE_SECURE", "true").strip().lower()
        if secure_value not in {"true", "false"}:
            raise ValueError("AUTH_COOKIE_SECURE must be true or false.")
        return cls(secret, expires, remember_days, secure_value == "true")


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    id: UUID
    user_code: str
    username: str
    email: str | None
    phone: str | None
    display_name: str
    status: str
    roles: tuple[str, ...]

    def as_response(self) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=str(self.id), user_code=self.user_code, username=self.username,
            email=self.email, phone=self.phone, display_name=self.display_name,
            status=self.status, roles=list(self.roles),
        )


def _error(request: Request, code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message, getattr(request.state, "correlation_id", "auth-request"))


def _auth_settings(request: Request) -> AuthSettings:
    try:
        return AuthSettings.from_environment()
    except ValueError as exc:
        raise _error(request, "UNAVAILABLE", "Authentication is not configured.") from exc


def get_auth_db(request: Request) -> Iterator[Session]:
    try:
        yield from get_db()
    except RuntimeError as exc:
        raise _error(request, "UNAVAILABLE", "Authentication database is not configured.") from exc
    except SQLAlchemyError as exc:
        raise _error(request, "UNAVAILABLE", "Authentication database is unavailable.") from exc


def _check_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed_origins = set(getattr(request.app.state, "allowed_origins", ()))
    if origin and origin not in allowed_origins:
        raise _error(request, "FORBIDDEN", "Request origin is not allowed.")


def _user_roles(user: User) -> tuple[str, ...]:
    return tuple(sorted({link.role.code for link in user.user_roles}))


def _principal(user: User) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=user.id, user_code=user.user_code, username=user.username,
        email=user.email, phone=user.phone, display_name=user.display_name,
        status=user.status, roles=_user_roles(user),
    )


def _user_query():
    return select(User).options(selectinload(User.user_roles).selectinload(UserRole.role))


def _new_access_token(user_id: UUID, settings: AuthSettings, remember_me: bool) -> str:
    now = datetime.now(timezone.utc)
    lifetime = (timedelta(days=settings.remember_token_days) if remember_me
                else timedelta(minutes=settings.access_token_minutes))
    return jwt.encode(
        {"sub": str(user_id), "iss": TOKEN_ISSUER, "iat": now,
         "exp": now + lifetime},
        settings.jwt_secret,
        algorithm="HS256",
    )


def _set_auth_cookie(response: Response, token: str, settings: AuthSettings,
                     remember_me: bool) -> None:
    options = dict(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    if remember_me:
        options["max_age"] = settings.remember_token_days * 24 * 60 * 60
    response.set_cookie(**options)


def _normalize_username(value: str) -> str:
    username = unicodedata.normalize("NFKC", value).strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", username):
        raise ValueError("Tên đăng nhập phải dài 3–80 ký tự và chỉ gồm chữ, số, dấu chấm, gạch dưới hoặc gạch nối.")
    return username


def _normalize_contact(value: str) -> tuple[str | None, str | None]:
    contact = unicodedata.normalize("NFKC", value).strip()
    if "@" in contact:
        local, separator, domain = contact.rpartition("@")
        local_pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
        labels = domain.split(".")
        valid_domain = (
            len(domain) <= 253 and len(labels) >= 2 and len(labels[-1]) >= 2
            and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                    for label in labels)
        )
        if (not separator or len(local) > 64 or not re.fullmatch(local_pattern, local)
                or local.startswith(".") or local.endswith(".") or ".." in local
                or not valid_domain):
            raise ValueError("Email không hợp lệ.")
        return f"{local.casefold()}@{domain.casefold()}", None

    phone = re.sub(r"[ .()\-]", "", contact)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
        raise ValueError("Số điện thoại phải ở định dạng quốc tế, ví dụ +84901234567.")
    return None, phone


def _registration_enabled() -> bool:
    return os.getenv("AUTH_REGISTRATION_ENABLED", "false").strip().lower() == "true"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit_login_attempt(request: Request, identifier: str) -> None:
    retry_after = request.app.state.auth_attempt_limiter.record_login(
        _client_ip(request), identifier,
    )
    if retry_after is not None:
        raise _error(request, "RATE_LIMITED", "Too many login attempts. Please wait before trying again.")


def _limit_registration_attempt(request: Request) -> None:
    retry_after = request.app.state.auth_attempt_limiter.record_registration(_client_ip(request))
    if retry_after is not None:
        raise _error(request, "RATE_LIMITED", "Too many registration attempts. Please wait before trying again.")


def get_current_principal(
    request: Request,
    session: Session = Depends(get_auth_db),
    settings: AuthSettings = Depends(_auth_settings),
) -> AuthenticatedPrincipal:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise _error(request, "UNAUTHENTICATED", "Authentication is required.")
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
        user_id = UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise _error(request, "UNAUTHENTICATED", "Authentication is required.") from exc

    user = session.scalar(_user_query().where(User.id == user_id))
    if user is None or user.status != "ACTIVE":
        raise _error(request, "UNAUTHENTICATED", "Authentication is required.")
    return _principal(user)


def require_role(role: str):
    def dependency(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if role not in principal.roles:
            raise _error(request, "FORBIDDEN", "You do not have permission to perform this action.")
        return principal

    return dependency


def require_any_role(*roles: str):
    required = frozenset(roles)

    def dependency(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if not required.intersection(principal.roles):
            raise _error(request, "FORBIDDEN", "You do not have permission to perform this action.")
        return principal

    return dependency


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_auth_db),
    settings: AuthSettings = Depends(_auth_settings),
) -> AuthResponse:
    _check_browser_origin(request)
    identifier = body.identifier.strip().casefold()
    _limit_login_attempt(request, identifier)
    users = session.scalars(
        _user_query().where(
            or_(func.lower(User.user_code) == identifier,
                func.lower(User.username) == identifier,
                func.lower(User.email) == identifier)
        )
    ).all()
    user = users[0] if len(users) == 1 else None
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    valid_password = verify_password(password_hash, body.password)
    if user is None or not valid_password or user.status != "ACTIVE":
        raise _error(request, "UNAUTHENTICATED", INVALID_CREDENTIALS)

    if password_hash_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        session.commit()
    _set_auth_cookie(response, _new_access_token(user.id, settings, body.remember_me),
                     settings, body.remember_me)
    return AuthResponse(user=_principal(user).as_response())


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    session: Session = Depends(get_auth_db),
) -> AuthResponse:
    _check_browser_origin(request)
    if not _registration_enabled():
        raise _error(request, "FORBIDDEN", "Self-registration is currently disabled.")
    _limit_registration_attempt(request)
    _auth_settings(request)

    try:
        username = _normalize_username(body.username)
        email, phone = _normalize_contact(body.contact)
    except ValueError as exc:
        raise _error(request, "VALIDATION_ERROR", str(exc)) from exc

    maker_role = session.scalar(select(Role).where(Role.code == "MAKER"))
    if maker_role is None:
        raise _error(request, "UNAVAILABLE", "Account registration is not configured.")

    identity_checks = [func.lower(User.username) == username]
    identity_checks.append(func.lower(User.email) == email if email is not None else User.phone == phone)
    existing = session.scalar(select(User.id).where(or_(*identity_checks)))
    if existing is not None:
        raise _error(request, "CONFLICT", "Tên đăng nhập hoặc thông tin liên hệ đã được sử dụng.")

    user = User(
        user_code=f"USR-{token_hex(14).upper()}",
        username=username,
        email=email,
        phone=phone,
        password_hash=hash_password(body.password),
        display_name=username,
        status="ACTIVE",
    )
    try:
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=maker_role.id, assigned_by=None))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _error(request, "CONFLICT", "Tên đăng nhập hoặc thông tin liên hệ đã được sử dụng.") from exc

    session.refresh(user)
    return AuthResponse(user=_principal(user).as_response())


@router.get("/config")
def auth_config() -> dict[str, bool]:
    """Return public Auth feature switches only; secrets and service settings stay server-side."""
    return {"registration_enabled": _registration_enabled()}


@router.get("/me", response_model=AuthResponse)
def me(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> AuthResponse:
    return AuthResponse(user=principal.as_response())


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    _check_browser_origin(request)
    response.delete_cookie(
        key=AUTH_COOKIE_NAME, path="/",
        secure=os.getenv("AUTH_COOKIE_SECURE", "true").strip().lower() == "true",
        httponly=True, samesite="lax",
    )
    response.status_code = 204
    return response
