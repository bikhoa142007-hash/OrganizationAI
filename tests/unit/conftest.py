from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.backend.db.base import Base
from src.backend.db.models.role import Role, UserRole
from src.backend.db.models.user import User


@pytest.fixture
def admin_db():
    """Provide a synthetic isolated database for unit-only workflow tests."""
    import src.backend.db.models

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        for code in ("MAKER", "CHECKER", "ADMIN"):
            session.add(Role(code=code, name=code.title(), is_builtin=True))
    with factory() as session:
        admin = User(
            user_code="U-ADMIN",
            username="admin.user",
            email="admin@example.test",
            phone=None,
            password_hash="unused",
            display_name="Admin",
            status="ACTIVE",
        )
        session.add(admin)
        session.flush()
        session.add(UserRole(
            user_id=admin.id,
            role_id=session.scalar(select(Role.id).where(Role.code == "ADMIN")),
        ))
        session.flush()
        principal = SimpleNamespace(id=admin.id, roles=("ADMIN",), permissions=())
    try:
        yield factory, principal
    finally:
        engine.dispose()
