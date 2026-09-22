import pytest
from deployment.start_backend import validate_environment, main


def environment():
    return dict(APP_ENV='demo', CORS_ORIGINS='https://judge.example.com',
                DEMO_DATABASE='/var/data/demo-organization.sqlite3', PORT='10000')


def test_public_configuration_accepts_https_and_mounted_database_path():
    database, port = validate_environment(environment())
    assert database.name == 'demo-organization.sqlite3'
    assert port == 10000


@pytest.mark.parametrize('key,value', [
    ('APP_ENV', 'production'), ('CORS_ORIGINS', '*'),
    ('CORS_ORIGINS', 'http://judge.example.com'),
    ('CORS_ORIGINS', 'https://judge.example.com/'),
    ('CORS_ORIGINS', 'https://judge.example.com,https://other.example.com'),
    ('CORS_ORIGINS', 'https://localhost'), ('CORS_ORIGINS', 'https://127.0.0.1'),
    ('CORS_ORIGINS', 'https://user:password@judge.example.com'),
    ('DEMO_DATABASE', 'runtime/demo-organization.sqlite3'),
    ('DEMO_DATABASE', '/var/data/company.sqlite3'), ('PORT', '0'),
])
def test_public_configuration_rejects_unsafe_values(key, value):
    env = environment(); env[key] = value
    with pytest.raises(ValueError):
        validate_environment(env)


def test_start_refuses_ephemeral_disk(monkeypatch):
    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr('deployment.start_backend.os.path.ismount', lambda path: False)
    with pytest.raises(RuntimeError, match='Persistent disk'):
        main()
