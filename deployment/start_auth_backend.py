"""Run checked Auth/PostgreSQL migrations before starting the staging API."""
import os
from urllib.parse import urlsplit

import uvicorn
from alembic import command
from alembic.config import Config

from src.backend.api.auth import AuthSettings
from src.backend.api.dependencies import Settings
from src.backend.db.session import normalize_database_url


def validate_staging_environment() -> None:
    if os.getenv("APP_ENV", "").strip().lower() != "production":
        raise RuntimeError("Auth staging requires APP_ENV=production; Judge Demo actors must remain disabled.")

    auth = AuthSettings.from_environment()
    if not auth.cookie_secure:
        raise RuntimeError("Auth staging requires AUTH_COOKIE_SECURE=true.")

    origins = Settings.from_environment().cors_origins
    if not origins or any(
        urlsplit(origin).scheme != "https"
        or not urlsplit(origin).netloc
        or urlsplit(origin).path
        or urlsplit(origin).query
        or urlsplit(origin).fragment
        for origin in origins
    ):
        raise RuntimeError("Auth staging requires exact HTTPS origins in CORS_ORIGINS.")

    normalize_database_url(os.getenv("DATABASE_URL", ""))


def main() -> None:
    validate_staging_environment()
    command.upgrade(Config("alembic.ini"), "head")
    uvicorn.run(
        "src.backend.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "*"),
    )


if __name__ == "__main__":
    main()
