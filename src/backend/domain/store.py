"""Optional local persistence adapter for WP2 immutable records and seed data.

This is not an approval command repository: it cannot commit live plan transitions.
The pure domain/rules modules do not import this adapter.
"""
import json
import sqlite3
from src.shared.validation import canonical_hash, json_value, require

MIGRATION_1 = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS snapshots (
    kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (kind, record_id)
);
CREATE TRIGGER IF NOT EXISTS snapshots_no_update
BEFORE UPDATE ON snapshots BEGIN SELECT RAISE(ABORT, 'immutable snapshot'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_delete
BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT, 'immutable snapshot'); END;
PRAGMA user_version = 1;
COMMIT;
"""


class SnapshotStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def migrate(self):
        version = self.connection.execute('PRAGMA user_version').fetchone()[0]
        require(version in (0, 1), 'Unsupported storage schema version')
        if version == 0:
            self.connection.executescript(MIGRATION_1)

    def append(self, kind, record_id, record):
        self.append_many(((kind, record_id, record),))

    def append_many(self, records):
        """Atomically append an immutable batch; same IDs/content are safe to replay."""
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            for kind, record_id, record in records:
                require(isinstance(kind, str) and bool(kind.strip()) and
                        isinstance(record_id, str) and bool(record_id.strip()), 'Invalid record identity')
                digest = canonical_hash(record)
                existing = self.connection.execute(
                    'SELECT content_hash FROM snapshots WHERE kind = ? AND record_id = ?',
                    (kind, record_id),
                ).fetchone()
                if existing:
                    require(existing[0] == digest, 'CONFLICT: immutable record identity reused')
                    continue
                self.connection.execute('INSERT INTO snapshots VALUES (?, ?, ?, ?)',
                                        (kind, record_id, digest,
                                         json.dumps(json_value(record), ensure_ascii=False, allow_nan=False)))

    def read(self, kind, record_id):
        row = self.connection.execute(
            'SELECT content_hash, body FROM snapshots WHERE kind = ? AND record_id = ?',
            (kind, record_id),
        ).fetchone()
        if row is None:
            return None
        record = json.loads(row[1])
        require(canonical_hash(record) == row[0], 'Stored snapshot hash mismatch')
        return record
