from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_auth_migration_rehearsal.ps1"


def _source() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_tls_probe_keeps_postgres_boolean_type_for_psql_output() -> None:
    source = _source()
    match = re.search(
        r"\$sourceProbeSql\s*=\s*@'\s*(.*?)\s*'@",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, "the source database TLS probe must remain explicit"

    sql = " ".join(match.group(1).split()).casefold()
    assert "coalesce((select ssl from pg_stat_ssl where pid = pg_backend_pid()), false)" in sql
    assert "ssl::text" not in sql
    assert "$tlsactive = $probefields[10]" in source.casefold()
    assert "if ($tlsactive -cne 't')" in source.casefold()


def test_source_tls_is_required_and_verified_on_the_probed_backend() -> None:
    source = _source()
    assert re.search(
        r"Set-PostgresEnvironment\s+\$sourceHost\s+\$sourcePort\s+\$sourceUser\s+"
        r"\$sourceDatabase\s+\$sourcePassword\s+'require'",
        source,
    )
    assert "Set-ProcessEnvironment 'PGSSLMODE' $SslMode" in source
    assert "Set-ProcessEnvironment 'PGGSSENCMODE' 'disable'" in source
    assert "WHERE pid = pg_backend_pid()" in source
