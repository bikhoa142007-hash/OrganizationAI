"""SQLite persistence for WP3, isolated from the WP2 snapshot-store schema.

One repository per request/worker. BEGIN IMMEDIATE serializes all command guards
and writes, including requests on separate connections. Never expose this trusted
storage interface directly to clients; use ApprovalWorkflow for authorization.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from src.shared.validation import canonical_hash, json_value


def encode(value):
    return json.dumps(json_value(value), ensure_ascii=False, allow_nan=False)


class ApprovalRepository:
    def __init__(self, path):
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.executescript(Path(__file__).with_name('migration_001.sql').read_text())

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def plan(self, plan_id):
        row = self.connection.execute('SELECT body FROM wp3_plans WHERE plan_id = ?',
                                      (plan_id,)).fetchone()
        return json.loads(row['body']) if row else None

    def save_plan(self, plan):
        self.connection.execute(
            'INSERT INTO wp3_plans VALUES (?, ?) ON CONFLICT(plan_id) DO UPDATE SET body=excluded.body',
            (plan['plan_id'], encode(plan)))

    def replay(self, scope):
        row = self.connection.execute('SELECT request_hash, body FROM wp3_intents WHERE scope = ?',
                                      (scope,)).fetchone()
        if not row:
            return None
        return row['request_hash'], json.loads(row['body'])

    def remember(self, scope, request_hash, result):
        self.connection.execute('INSERT INTO wp3_intents VALUES (?, ?, ?)',
                                (scope, request_hash, encode(result)))

    def append(self, kind, record_id, plan_id, round_number, record):
        self.connection.execute('INSERT INTO wp3_records VALUES (?, ?, ?, ?, ?, ?)',
                                (kind, record_id, plan_id, round_number,
                                 canonical_hash(record), encode(record)))

    def audit(self, event):
        self.connection.execute('INSERT INTO wp3_audit(event_id, plan_id, body) VALUES (?, ?, ?)',
                                (event.event_id, event.plan_id, encode(event)))

    def version(self, plan_id, number):
        row = self.connection.execute(
            "SELECT body, content_hash FROM wp3_records WHERE kind='version' AND plan_id=? AND round_number=?",
            (plan_id, number)).fetchone()
        return json.loads(row['body']), row['content_hash']

    def round(self, plan_id, number):
        row = self.connection.execute('SELECT * FROM wp3_rounds WHERE plan_id=? AND number=?',
                                      (plan_id, number)).fetchone()
        if row is None:
            return None
        return {**dict(row), 'configuration': json.loads(row['configuration']),
                'ticket': json.loads(row['ticket'])}

    def create_round(self, plan_id, number, config, ticket):
        self.connection.execute('INSERT INTO wp3_rounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (plan_id, number, 'ACTIVE', 0, encode(config),
                                 canonical_hash(config), encode(ticket), None, None))

    def update_round(self, plan_id, number, *, status, decision_id, final_id=None):
        self.connection.execute(
            'UPDATE wp3_rounds SET status=?, revision=revision+1, decision_id=?, final_id=? '
            'WHERE plan_id=? AND number=?', (status, decision_id, final_id, plan_id, number))

    def record(self, kind, record_id):
        row = self.connection.execute('SELECT body FROM wp3_records WHERE kind=? AND record_id=?',
                                      (kind, record_id)).fetchone()
        return json.loads(row['body']) if row else None

    def attachment(self, attachment_id):
        return self.connection.execute('SELECT * FROM wp3_attachments WHERE attachment_id=?',
                                       (attachment_id,)).fetchone()

    def add_attachment(self, attachment_id, plan_id, media_type, content):
        self.connection.execute('INSERT INTO wp3_attachments VALUES (?, ?, ?, ?)',
                                (attachment_id, plan_id, media_type, content))

    def finalize(self, plan_id, number, kind, decision_id):
        self.connection.execute('INSERT INTO wp3_finals VALUES (?, ?, ?, ?)',
                                (plan_id, number, kind, decision_id))

    def history(self, plan_id):
        records = [dict(row) for row in self.connection.execute(
            'SELECT kind, body FROM wp3_records WHERE plan_id=? ORDER BY rowid', (plan_id,))]
        versions = [json.loads(r['body']) for r in records if r['kind'] == 'version']
        return dict(
            plan=self.plan(plan_id), versions=versions,
            rounds=[self.round(plan_id, row['number']) for row in self.connection.execute(
                'SELECT number FROM wp3_rounds WHERE plan_id=? ORDER BY number', (plan_id,))],
            records=[{'kind': r['kind'], 'body': json.loads(r['body'])}
                     for r in records if r['kind'] != 'version'],
            audit=[json.loads(row['body']) for row in self.connection.execute(
                'SELECT body FROM wp3_audit WHERE plan_id=? ORDER BY sequence', (plan_id,))],
        )

    def list_visible_plans(self, actor, is_checker, offset, limit):
        rows = self.connection.execute(
            "SELECT body FROM wp3_plans WHERE json_extract(body, '$.maker_id') = ? "
            "OR (? AND json_extract(body, '$.payload.checker_id') = ?) ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (actor, is_checker, actor, limit, offset))
        return [json.loads(row['body']) for row in rows]
    def list_pending_reviews(self, actor, offset, limit):
        rows = self.connection.execute(
            "SELECT body FROM wp3_plans WHERE json_extract(body, '$.payload.checker_id') = ? "
            "AND json_extract(body, '$.maker_id') != ? "
            "AND json_extract(body, '$.state.plan_status') = 'PENDING_APPROVAL' "
            "AND json_extract(body, '$.state.processing_stage') = 'HUMAN_REVIEW_REQUIRED' "
            "ORDER BY rowid DESC LIMIT ? OFFSET ?", (actor, actor, limit, offset))
        return [json.loads(row['body']) for row in rows]
