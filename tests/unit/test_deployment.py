import pytest
from deployment.start_backend import validate_environment, initialize_demo_database


def environment():
    return dict(APP_ENV='demo', CORS_ORIGINS='https://judge.example.com',
                DEMO_DATABASE='/tmp/organizationai/demo-organization.sqlite3', PORT='10000')


def test_public_configuration_accepts_https_and_ephemeral_database_path():
    database, port = validate_environment(environment())
    assert database.name == 'demo-organization.sqlite3'
    assert port == 10000


def test_public_judge_only_configuration_rejects_any_auth_database_url():
    env = environment()
    env["PUBLIC_JUDGE_ONLY"] = "true"
    env["DATABASE_URL"] = "postgresql://synthetic.invalid/should-not-be-used"

    with pytest.raises(ValueError, match="must not configure DATABASE_URL"):
        validate_environment(env)


def test_public_judge_only_configuration_needs_no_database_path():
    env = environment()
    env["PUBLIC_JUDGE_ONLY"] = "true"
    env.pop("DEMO_DATABASE")
    database, port = validate_environment(env)

    assert database is None
    assert port == 10000


def test_public_judge_only_startup_does_not_seed_or_open_shared_demo_database(monkeypatch):
    from deployment import start_backend

    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PUBLIC_JUDGE_ONLY", "true")
    monkeypatch.delenv("DEMO_DATABASE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    called = {}

    def forbidden_seed(_database):
        raise AssertionError("Public Judge-only startup must not seed the shared demo database")

    monkeypatch.setattr(start_backend, "initialize_demo_database", forbidden_seed)
    monkeypatch.setattr(start_backend.os, "execv", lambda executable, args: called.update(executable=executable, args=args))

    start_backend.main()

    assert called["args"][1:3] == ["-m", "uvicorn"]
    assert "src.backend.api.app:app" in called["args"]


@pytest.mark.parametrize('key,value', [
    ('APP_ENV', 'production'), ('CORS_ORIGINS', '*'),
    ('CORS_ORIGINS', 'http://judge.example.com'),
    ('CORS_ORIGINS', 'https://judge.example.com/'),
    ('CORS_ORIGINS', 'https://judge.example.com,https://other.example.com'),
    ('CORS_ORIGINS', 'https://localhost'), ('CORS_ORIGINS', 'https://127.0.0.1'),
    ('CORS_ORIGINS', 'https://user:password@judge.example.com'),
    ('DEMO_DATABASE', 'runtime/demo-organization.sqlite3'),
    ('DEMO_DATABASE', '/var/data/company.sqlite3'),
    ('DEMO_DATABASE', '/var/data/demo-organization.sqlite3'),
    ('DEMO_DATABASE', '/tmp/organizationai/../demo-organization.sqlite3'),
    ('DEMO_DATABASE', '/tmp/organizationai/company.sqlite3'),
    ('PORT', '0'), ('PORT', '65536'), ('PORT', 'invalid'),
])
def test_public_configuration_rejects_unsafe_values(key, value):
    env = environment(); env[key] = value
    with pytest.raises(ValueError):
        validate_environment(env)


def test_start_creates_and_seeds_missing_database(tmp_path):
    from src.backend.repositories.approval import ApprovalRepository
    database = tmp_path / 'nested' / 'demo-free.sqlite3'
    assert not database.exists()
    first = initialize_demo_database(database)
    assert len(first['created']) == 8
    repo = ApprovalRepository(database)
    try:
        before = repo.connection.execute('SELECT body FROM wp3_audit ORDER BY rowid').fetchall()
        assert repo.connection.execute('SELECT count(*) FROM wp3_plans').fetchone()[0] == 8
    finally:
        repo.close()
    second = initialize_demo_database(database)
    assert not second['created']
    repo = ApprovalRepository(database)
    try:
        assert repo.connection.execute('SELECT body FROM wp3_audit ORDER BY rowid').fetchall() == before
    finally:
        repo.close()
    database.unlink()  # Simulate loss of the temporary test-only ephemeral filesystem.
    assert len(initialize_demo_database(database)['created']) == 8
