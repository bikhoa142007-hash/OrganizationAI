BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS wp3_migrations (version INTEGER PRIMARY KEY CHECK (version = 1));
CREATE TABLE IF NOT EXISTS wp3_plans (plan_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wp3_records (
    kind TEXT NOT NULL, record_id TEXT NOT NULL,
    plan_id TEXT NOT NULL REFERENCES wp3_plans(plan_id), round_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind, record_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS wp3_unique_version
ON wp3_records(plan_id, round_number) WHERE kind = 'version';
CREATE TABLE IF NOT EXISTS wp3_rounds (
    plan_id TEXT NOT NULL REFERENCES wp3_plans(plan_id), number INTEGER NOT NULL CHECK(number > 0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'CLOSED')),
    revision INTEGER NOT NULL CHECK(revision >= 0), configuration TEXT NOT NULL,
    configuration_hash TEXT NOT NULL, ticket TEXT NOT NULL,
    decision_id TEXT, final_id TEXT, PRIMARY KEY(plan_id, number)
);
CREATE UNIQUE INDEX IF NOT EXISTS wp3_one_active_round ON wp3_rounds(plan_id) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS wp3_finals (
    plan_id TEXT NOT NULL, round_number INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('engine_decision', 'human_decision')),
    decision_id TEXT NOT NULL, PRIMARY KEY(plan_id, round_number),
    FOREIGN KEY(plan_id, round_number) REFERENCES wp3_rounds(plan_id, number),
    FOREIGN KEY(kind, decision_id) REFERENCES wp3_records(kind, record_id)
);
CREATE TABLE IF NOT EXISTS wp3_intents (
    scope TEXT PRIMARY KEY, request_hash TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wp3_attachments (
    attachment_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES wp3_plans(plan_id),
    media_type TEXT NOT NULL, content BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS wp3_audit (
    sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
    plan_id TEXT NOT NULL REFERENCES wp3_plans(plan_id), body TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS wp3_records_no_update BEFORE UPDATE ON wp3_records
BEGIN SELECT RAISE(ABORT, 'immutable history'); END;
CREATE TRIGGER IF NOT EXISTS wp3_records_no_delete BEFORE DELETE ON wp3_records
BEGIN SELECT RAISE(ABORT, 'immutable history'); END;
CREATE TRIGGER IF NOT EXISTS wp3_audit_no_update BEFORE UPDATE ON wp3_audit
BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS wp3_audit_no_delete BEFORE DELETE ON wp3_audit
BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS wp3_intents_no_update BEFORE UPDATE ON wp3_intents
BEGIN SELECT RAISE(ABORT, 'immutable intent'); END;
CREATE TRIGGER IF NOT EXISTS wp3_intents_no_delete BEFORE DELETE ON wp3_intents
BEGIN SELECT RAISE(ABORT, 'immutable intent'); END;
CREATE TRIGGER IF NOT EXISTS wp3_finals_no_update BEFORE UPDATE ON wp3_finals
BEGIN SELECT RAISE(ABORT, 'immutable final decision'); END;
CREATE TRIGGER IF NOT EXISTS wp3_finals_no_delete BEFORE DELETE ON wp3_finals
BEGIN SELECT RAISE(ABORT, 'immutable final decision'); END;
CREATE TRIGGER IF NOT EXISTS wp3_attachments_no_update BEFORE UPDATE ON wp3_attachments
BEGIN SELECT RAISE(ABORT, 'immutable attachment'); END;
CREATE TRIGGER IF NOT EXISTS wp3_attachments_no_delete BEFORE DELETE ON wp3_attachments
BEGIN SELECT RAISE(ABORT, 'immutable attachment'); END;
CREATE TRIGGER IF NOT EXISTS wp3_rounds_guard BEFORE UPDATE ON wp3_rounds
WHEN OLD.status='CLOSED' OR NEW.plan_id != OLD.plan_id OR NEW.number != OLD.number
 OR NEW.configuration != OLD.configuration OR NEW.configuration_hash != OLD.configuration_hash
 OR NEW.ticket != OLD.ticket OR NEW.revision != OLD.revision + 1
BEGIN SELECT RAISE(ABORT, 'immutable round snapshot or closed round'); END;
CREATE TRIGGER IF NOT EXISTS wp3_rounds_no_delete BEFORE DELETE ON wp3_rounds
BEGIN SELECT RAISE(ABORT, 'immutable round history'); END;
INSERT OR IGNORE INTO wp3_migrations VALUES (1);
COMMIT;
