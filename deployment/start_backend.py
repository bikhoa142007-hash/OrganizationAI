"""Render startup: validate hosted settings, seed ephemeral demo SQLite, then serve."""
import ipaddress
import os
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import urlsplit


def validate_environment(env):
    if env.get('APP_ENV') != 'demo':
        raise ValueError('Public Judge Demo requires APP_ENV=demo')
    public_judge_only = env.get('PUBLIC_JUDGE_ONLY', 'false').strip().lower()
    if public_judge_only not in {'true', 'false'}:
        raise ValueError('PUBLIC_JUDGE_ONLY must be true or false.')
    if public_judge_only == 'true' and env.get('DATABASE_URL', '').strip():
        raise ValueError('PUBLIC_JUDGE_ONLY must not configure DATABASE_URL.')
    origin = env.get('CORS_ORIGINS', '')
    url = urlsplit(origin)
    if (url.scheme != 'https' or not url.hostname or url.path or url.query or url.fragment
            or url.username or url.password or ',' in origin or '*' in origin
            or url.hostname == 'localhost' or url.hostname.endswith('.localhost')):
        raise ValueError('CORS_ORIGINS must be one exact public HTTPS frontend origin')
    try:
        address = ipaddress.ip_address(url.hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError('CORS_ORIGINS cannot be a private or loopback address')
    database = None
    if public_judge_only != 'true':
        database_path = PurePosixPath(env.get('DEMO_DATABASE', ''))
        if (not database_path.is_absolute() or database_path.parent != PurePosixPath('/tmp/organizationai')
                or not database_path.name.startswith('demo-') or database_path.suffix != '.sqlite3'):
            raise ValueError('DEMO_DATABASE must be /tmp/organizationai/demo-*.sqlite3 for the free demo')
        database = Path(database_path)
    port = int(env.get('PORT', '10000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    return database, port


def initialize_demo_database(database):
    """Recreate deterministic fixtures after ephemeral storage has been lost."""
    from src.backend.seed_demo import seed
    database.parent.mkdir(parents=True, exist_ok=True)
    # Seed also safely replays existing intents, recovering an interrupted first boot.
    return seed(database, 'demo')


def main():
    database, port = validate_environment(os.environ)
    from src.backend.api.dependencies import Settings
    Settings.from_environment().validate()
    if os.environ.get('PUBLIC_JUDGE_ONLY', 'false').strip().lower() != 'true':
        initialize_demo_database(database)
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn',
             'src.backend.api.app:app', '--host', '0.0.0.0', '--port', str(port),
             '--workers', '1', '--limit-concurrency', '32'])


if __name__ == '__main__':
    main()
