"""Read-only Auth schema diagnostic pinned to a user-supplied deployment SHA.

Prompts for the deployment SHA visibly, then the PostgreSQL URL with getpass.
Fetches ORM/migration source from that exact public GitHub commit without
executing it. The database transaction is read-only and explicitly rolled back.
"""
from __future__ import annotations

import ast
import getpass
import json
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

REPOSITORY = "bikhoa142007-hash/OrganizationAI"
RAW_HOST = "raw.githubusercontent.com"
API_HOST = "api.github.com"
MAX_SOURCE_BYTES = 1_000_000
HTTP_TIMEOUT_SECONDS = 12
CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 10_000
CURRENT_PHASE = "manifest"

AUTH_LOGIN_TABLES = {"users", "roles", "user_roles", "role_permissions"}


class DiagnosticFailure(Exception):
    """A safe-to-report diagnostic failure without an attached secret."""


def fetch_https(url: str, allowed_host: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != allowed_host:
        raise DiagnosticFailure("unexpected_source")
    request = Request(url, headers={"User-Agent": "OrganizationAI-readonly-schema-diagnostic"})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != allowed_host:
            raise DiagnosticFailure("unexpected_redirect")
        payload = response.read(MAX_SOURCE_BYTES + 1)
    if len(payload) > MAX_SOURCE_BYTES:
        raise DiagnosticFailure("source_too_large")
    return payload


def fetch_raw(sha: str, path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    url = f"https://{RAW_HOST}/{REPOSITORY}/{sha}/{encoded_path}"
    return fetch_https(url, RAW_HOST).decode("utf-8")


def fetch_migration_index(sha: str) -> list[dict[str, str]]:
    url = (
        f"https://{API_HOST}/repos/{REPOSITORY}/contents/"
        f"alembic/versions?ref={quote(sha, safe='')}"
    )
    payload = fetch_https(url, API_HOST)
    entries = json.loads(payload.decode("utf-8"))
    if not isinstance(entries, list):
        raise DiagnosticFailure("invalid_migration_index")
    return [
        {"name": item["name"], "path": item["path"]}
        for item in entries
        if isinstance(item, dict)
        and item.get("type") == "file"
        and str(item.get("name", "")).endswith(".py")
    ]


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _string_constant(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _assigned_value(tree: ast.Module, variable: str):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == variable:
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return None
    return None


def _class_table_name(class_node: ast.ClassDef) -> str | None:
    for statement in class_node.body:
        if isinstance(statement, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__tablename__"
                   for target in statement.targets):
                return _string_constant(statement.value)
        if isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == "__tablename__":
                return _string_constant(statement.value)
    return None


def _mapped_column_name(statement: ast.stmt) -> str | None:
    if isinstance(statement, ast.AnnAssign):
        target = statement.target
        value = statement.value
    elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        value = statement.value
    else:
        return None

    if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
        return None
    if _call_name(value) not in {"mapped_column", "Column"}:
        return None
    for keyword in value.keywords:
        if keyword.arg == "name":
            explicit = _string_constant(keyword.value)
            if explicit:
                return explicit
    if value.args:
        explicit = _string_constant(value.args[0])
        if explicit:
            return explicit
    return target.id


def load_model_manifest(sha: str) -> dict[str, set[str]]:
    package = ast.parse(fetch_raw(sha, "src/backend/db/models/__init__.py"))
    modules = sorted({
        node.module
        for node in package.body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    })
    if not modules:
        raise DiagnosticFailure("model_manifest_unavailable")

    manifest: dict[str, set[str]] = {}
    for module in modules:
        source_path = f"src/backend/db/models/{module}.py"
        tree = ast.parse(fetch_raw(sha, source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            table = _class_table_name(node)
            if not table:
                continue
            columns = {
                column
                for statement in node.body
                if (column := _mapped_column_name(statement)) is not None
            }
            if not columns:
                raise DiagnosticFailure("model_columns_unavailable")
            manifest.setdefault(table, set()).update(columns)

    if not AUTH_LOGIN_TABLES.issubset(manifest):
        raise DiagnosticFailure("auth_login_manifest_incomplete")
    return manifest


def _migration_column_calls(call: ast.Call) -> list[str]:
    names = []
    for argument in call.args[1:]:
        if _call_name(argument) == "Column" and argument.args:
            name = _string_constant(argument.args[0])
            if name:
                names.append(name)
    return names


def _column_from_add_call(call: ast.Call, batch_table: str | None) -> tuple[str, str] | None:
    function = _call_name(call)
    if function != "add_column":
        return None

    if batch_table:
        table = batch_table
        column_call = call.args[0] if call.args else None
    else:
        table = _string_constant(call.args[0]) if call.args else None
        column_call = call.args[1] if len(call.args) > 1 else None

    if not table or not isinstance(column_call, ast.Call) or _call_name(column_call) != "Column":
        return None
    column = _string_constant(column_call.args[0]) if column_call.args else None
    return (table, column) if column else None


def _scan_upgrade(node: ast.AST, revision: str, additions: dict, batch_table=None) -> None:
    if isinstance(node, (ast.With, ast.AsyncWith)):
        nested_table = batch_table
        for item in node.items:
            call = item.context_expr
            if _call_name(call) == "batch_alter_table" and call.args:
                nested_table = _string_constant(call.args[0])
        for statement in node.body:
            _scan_upgrade(statement, revision, additions, nested_table)
        return

    if isinstance(node, ast.Call):
        function = _call_name(node)
        if function == "create_table" and node.args:
            table = _string_constant(node.args[0])
            if table:
                additions["tables"].setdefault(table, (revision, additions["filename"]))
                for column in _migration_column_calls(node):
                    additions["columns"].setdefault(
                        (table, column), (revision, additions["filename"])
                    )
        elif function == "add_column":
            found = _column_from_add_call(node, batch_table)
            if found:
                additions["columns"].setdefault(
                    found, (revision, additions["filename"])
                )

    for child in ast.iter_child_nodes(node):
        _scan_upgrade(child, revision, additions, batch_table)


def load_migration_manifest(sha: str):
    entries = fetch_migration_index(sha)
    if not entries:
        raise DiagnosticFailure("migration_manifest_unavailable")

    migrations = {}
    additions = {"tables": {}, "columns": {}}

    for entry in entries:
        tree = ast.parse(fetch_raw(sha, entry["path"]))
        revision = _assigned_value(tree, "revision")
        down_revision = _assigned_value(tree, "down_revision")
        if not isinstance(revision, str):
            raise DiagnosticFailure("migration_revision_unavailable")
        if down_revision is None:
            parents = ()
        elif isinstance(down_revision, str):
            parents = (down_revision,)
        elif isinstance(down_revision, (tuple, list)) and all(
            isinstance(parent, str) for parent in down_revision
        ):
            parents = tuple(down_revision)
        else:
            raise DiagnosticFailure("migration_parent_unavailable")

        migrations[revision] = {
            "parents": parents,
            "filename": entry["name"],
        }
        additions["filename"] = entry["name"]
        upgrade = next(
            (node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == "upgrade"),
            None,
        )
        if upgrade is not None:
            _scan_upgrade(upgrade, revision, additions)

    referenced = {
        parent
        for item in migrations.values()
        for parent in item["parents"]
    }
    heads = sorted(set(migrations) - referenced)
    return migrations, heads, additions


def ordered_revision_chain(migrations: dict, head: str) -> list[str]:
    chain = []
    current = head
    visited = set()
    while current and current in migrations and current not in visited:
        visited.add(current)
        chain.append(current)
        parents = migrations[current]["parents"]
        if len(parents) != 1:
            break
        current = parents[0]
    return list(reversed(chain))


def pending_revisions(revisions: list[str], heads: list[str], migrations: dict) -> str:
    if len(revisions) != 1:
        return "unknown"
    if len(heads) != 1:
        return "multiple_heads"
    chain = ordered_revision_chain(migrations, heads[0])
    current = revisions[0]
    if current not in chain:
        return "revision_not_in_deployed_chain"
    index = chain.index(current)
    pending = chain[index + 1:]
    return ",".join(pending) if pending else "none"


def migration_hint(table: str, column: str | None, additions: dict) -> str:
    created = additions["tables"].get(table)
    if column is None:
        return f"{created[0]}:{created[1]}" if created else "unmapped"
    added = additions["columns"].get((table, column))
    if added:
        return f"{added[0]}:{added[1]}"
    if created:
        return f"{created[0]}:{created[1]}"
    return "unmapped"


def safe_sqlstate(exc: Exception) -> str:
    original = getattr(exc, "orig", None)
    value = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return value if isinstance(value, str) and re.fullmatch(r"[0-9A-Z]{5}", value) else "unavailable"


def normalized_database_url(raw: str):
    parsed = make_url(raw)
    if parsed.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise DiagnosticFailure("postgresql_url_required")

    # Remove user-supplied connection overrides, then enforce TLS and finite timeouts.
    query = {
        key: value
        for key, value in parsed.query.items()
        if key.lower() not in {"sslmode", "connect_timeout", "options"}
    }
    return parsed.set(drivername="postgresql+psycopg", query=query)


def database_diagnostic(url, model_manifest: dict[str, set[str]], migration_data):
    global CURRENT_PHASE
    migrations, heads, additions = migration_data
    engine = create_engine(
        url,
        connect_args={
            "sslmode": "require",
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        },
        pool_pre_ping=False,
        echo=False,
        hide_parameters=True,
    )
    connection = None
    transaction = None
    phase = "connect"
    CURRENT_PHASE = phase
    try:
        connection = engine.connect()
        transaction = connection.begin()
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        phase = "schema"
        CURRENT_PHASE = phase

        tls = connection.execute(text("""
            SELECT ssl
            FROM pg_catalog.pg_stat_ssl
            WHERE pid = pg_backend_pid()
        """)).scalar_one_or_none()
        if tls is not True:
            raise DiagnosticFailure("tls_not_confirmed")

        database_name, current_schema, search_path = connection.execute(text("""
            SELECT current_database(), current_schema(), current_setting('search_path')
        """)).one()

        relation_rows = connection.execute(text("""
            SELECT n.nspname, c.relname, a.attname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_attribute a
              ON a.attrelid = c.oid
             AND a.attnum > 0
             AND NOT a.attisdropped
            WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_toast%%'
        """)).all()

        physical_columns: dict[tuple[str, str], set[str]] = {}
        schemas_by_table: dict[str, set[str]] = {}
        for schema, table, column in relation_rows:
            physical_columns.setdefault((schema, table), set())
            schemas_by_table.setdefault(table, set()).add(schema)
            if column is not None:
                physical_columns[(schema, table)].add(column)

        resolved: dict[str, str] = {}
        missing_tables = []
        missing_columns = []
        tables_elsewhere = []

        for table, expected_columns in sorted(model_manifest.items()):
            relation = connection.execute(text("""
                SELECT n.nspname
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE c.oid = pg_catalog.to_regclass(CAST(:table_name AS text))
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
            """), {"table_name": table}).scalar_one_or_none()

            if relation is None:
                missing_tables.append(table)
                elsewhere = sorted(schemas_by_table.get(table, set()))
                if elsewhere:
                    tables_elsewhere.append(f"{table}@{','.join(elsewhere)}")
                continue

            resolved[table] = relation
            actual = physical_columns.get((relation, table), set())
            for column in sorted(expected_columns - actual):
                missing_columns.append((table, column))

        version_schema = connection.execute(text("""
            SELECT n.nspname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.oid = pg_catalog.to_regclass('alembic_version')
              AND c.relkind IN ('r', 'p')
        """)).scalar_one_or_none()

        if version_schema is None:
            revision_values = []
            revision_status = "TABLE_MISSING"
        else:
            version_columns = physical_columns.get((version_schema, "alembic_version"), set())
            if "version_num" not in version_columns:
                revision_values = []
                revision_status = "VERSION_COLUMN_MISSING"
            else:
                preparer = connection.dialect.identifier_preparer
                quoted_schema = preparer.quote_schema(version_schema)
                revision_values = connection.execute(text(
                    f"SELECT version_num FROM {quoted_schema}.alembic_version ORDER BY version_num"
                )).scalars().all()
                revision_status = ",".join(revision_values) if revision_values else "EMPTY"

        current_revisions = revision_values
        missing_table_hints = [
            f"{table}->{migration_hint(table, None, additions)}"
            for table in missing_tables
        ]
        missing_column_hints = [
            f"{table}.{column}->{migration_hint(table, column, additions)}"
            for table, column in missing_columns
        ]

        resolved_text = ",".join(
            f"{table}@{schema}" for table, schema in sorted(resolved.items())
        ) or "none"
        missing_tables_text = ",".join(missing_tables) if missing_tables else "none"
        missing_columns_text = (
            ",".join(f"{table}.{column}" for table, column in missing_columns)
            if missing_columns else "none"
        )
        elsewhere_text = ",".join(tables_elsewhere) if tables_elsewhere else "none"
        heads_text = ",".join(heads) if heads else "unresolved"
        pending_text = pending_revisions(current_revisions, heads, migrations)
        if len(heads) == 1 and revision_status == heads[0] and (
            missing_tables or missing_columns
        ):
            drift = "YES"
        elif revision_status == "TABLE_MISSING" or revision_status == "EMPTY":
            drift = "UNKNOWN"
        else:
            drift = "not_detected"

        transaction.rollback()
        print("diagnostic=OK")
        print("tls=encryption_confirmed")
        print("deployed_sha=" + SHA)
        print("database_name=" + str(database_name))
        print("current_schema=" + str(current_schema))
        print("search_path=" + str(search_path))
        print("alembic_revision=" + revision_status)
        print("deployed_alembic_head=" + heads_text)
        print("pending_revisions=" + pending_text)
        print("resolved_auth_tables=" + resolved_text)
        print("missing_tables=" + missing_tables_text)
        print("missing_columns=" + missing_columns_text)
        print("tables_outside_search_path=" + elsewhere_text)
        print("migration_hints_tables=" + (
            ",".join(missing_table_hints) if missing_table_hints else "none"
        ))
        print("migration_hints_columns=" + (
            ",".join(missing_column_hints) if missing_column_hints else "none"
        ))
        print("head_with_missing_schema_drift=" + drift)

    finally:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        if connection is not None:
            connection.close()
        engine.dispose()


def main() -> int:
    global SHA, CURRENT_PHASE
    SHA = input("Deployment SHA (40-character commit from Render): ").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", SHA):
        print("diagnostic=ERROR")
        print("phase=deployment_sha")
        print("exception_type=InvalidDeploymentSHA")
        print("sqlstate=unavailable")
        return 2

    phase = "manifest"
    CURRENT_PHASE = phase
    try:
        model_manifest = load_model_manifest(SHA)
        migration_data = load_migration_manifest(SHA)
        if len(migration_data[1]) != 1:
            raise DiagnosticFailure("deployed_migration_head_not_unique")
        print("manifest=loaded_from_deployment_sha")
    except KeyboardInterrupt:
        print("diagnostic=cancelled")
        return 130
    except Exception as exc:
        print("diagnostic=ERROR")
        print("phase=" + CURRENT_PHASE)
        print("exception_type=" + type(exc).__name__)
        print("sqlstate=" + safe_sqlstate(exc))
        return 1

    phase = "connect"
    CURRENT_PHASE = phase
    engine_url = None
    try:
        raw_url = getpass.getpass("External PostgreSQL URL (hidden input): ")
        engine_url = normalized_database_url(raw_url.strip())
        raw_url = ""
        database_diagnostic(engine_url, model_manifest, migration_data)
        return 0
    except KeyboardInterrupt:
        print("diagnostic=cancelled")
        return 130
    except Exception as exc:
        print("diagnostic=ERROR")
        print("phase=" + CURRENT_PHASE)
        print("exception_type=" + type(exc).__name__)
        print("sqlstate=" + safe_sqlstate(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
