"""Render startup: validate hosted settings, seed mounted SQLite, then serve."""
import ipaddress
import os
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import urlsplit


def validate_environment(env):
    if env.get('APP_ENV') != 'demo':
        raise ValueError('Public Judge Demo requires APP_ENV=demo')
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
    database = PurePosixPath(env.get('DEMO_DATABASE', ''))
    if (not database.is_absolute() or database.parent != PurePosixPath('/var/data')
            or not database.name.startswith('demo-') or database.suffix != '.sqlite3'):
        raise ValueError('DEMO_DATABASE must be /var/data/demo-*.sqlite3 on the mounted disk')
    port = int(env.get('PORT', '10000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    return Path(database), port


def main():
    database, port = validate_environment(os.environ)
    # Refuse to seed the ephemeral filesystem when disk provisioning was omitted.
    if not os.path.ismount(database.parent):
        raise RuntimeError('Persistent disk must be mounted at /var/data before startup')
    from src.backend.api.dependencies import Settings
    from src.backend.seed_demo import seed
    Settings.from_environment().validate()
    seed(database, 'demo')
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn',
             'src.backend.api.app:app', '--host', '0.0.0.0', '--port', str(port),
             '--workers', '1', '--limit-concurrency', '32'])


if __name__ == '__main__':
    main()
