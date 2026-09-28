from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.backend.db.base import Base
from src.backend.db.models import Role, User, UserRole
from src.backend.seed_auth import seed_development_users


def test_development_seed_creates_hashed_users_and_is_idempotent():
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    seed_development_users(factory, "Local-demo-password-123")
    seed_development_users(factory, "Local-demo-password-123")

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 3
        assert session.scalar(select(func.count()).select_from(Role)) == 3
        assert session.scalar(select(func.count()).select_from(UserRole)) == 3
        maker = session.scalar(select(User).where(User.user_code == "USR-000001"))
        assert maker.email == "maker@example.com"
        assert maker.password_hash.startswith("$argon2id$")
        assert maker.password_hash != "Local-demo-password-123"
        assert {
            user.user_code: user.user_roles[0].role.code
            for user in session.scalars(select(User)).all()
        } == {
            "USR-000001": "MAKER",
            "USR-000002": "CHECKER",
            "USR-000003": "ADMIN",
        }

    engine.dispose()
