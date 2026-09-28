"""Seed local authentication users without overwriting existing accounts."""
import os

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.backend.db.models import Role, User, UserRole
from src.backend.db.security import hash_password
from src.backend.db.session import get_session_factory

ROLE_SEEDS = (
    ("MAKER", "Maker", "Creates and revises marketing plans."),
    ("CHECKER", "Checker", "Reviews assigned marketing plans."),
    ("ADMIN", "Administrator", "Administrative role foundation."),
)
USER_SEEDS = (
    ("USR-000001", "maker", "maker@example.com", None, "Demo Maker", "MAKER"),
    ("USR-000002", "checker", "checker@example.com", None, "Demo Checker", "CHECKER"),
    ("USR-000003", "admin", "admin@example.com", None, "Demo Admin", "ADMIN"),
)


def seed_development_users(
    session_factory: sessionmaker[Session], password: str
) -> tuple[str, ...]:
    if not password:
        raise ValueError("A local AUTH_SEED_PASSWORD is required.")

    with session_factory.begin() as session:
        roles: dict[str, Role] = {}
        for code, name, description in ROLE_SEEDS:
            role = session.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, name=name, description=description)
                session.add(role)
            roles[code] = role
        session.flush()

        user_codes = []
        for user_code, username, email, phone, display_name, role_code in USER_SEEDS:
            user = session.scalar(select(User).where(User.user_code == user_code))
            if user is None:
                user = User(
                    user_code=user_code,
                    username=username,
                    email=email,
                    phone=phone,
                    password_hash=hash_password(password),
                    display_name=display_name,
                    status="ACTIVE",
                )
                session.add(user)
                session.flush()

            assignment = session.get(UserRole, (user.id, roles[role_code].id))
            if assignment is None:
                session.add(UserRole(user_id=user.id, role_id=roles[role_code].id))
            user_codes.append(user_code)
    return tuple(user_codes)


def main() -> None:
    environment = os.getenv("APP_ENV", "production").strip().lower()
    if environment not in {"development", "demo", "test"}:
        raise RuntimeError("Development auth users can only be seeded in development, demo, or test.")
    if os.getenv("AUTH_SEED_ENABLED") != "true":
        raise RuntimeError("Set AUTH_SEED_ENABLED=true explicitly before seeding local auth users.")
    password = os.getenv("AUTH_SEED_PASSWORD", "")
    if not password:
        raise RuntimeError("Set AUTH_SEED_PASSWORD before running the development auth seed.")
    users = seed_development_users(get_session_factory(), password)
    print(f"Ensured {len(users)} local authentication users.")


if __name__ == "__main__":
    main()
