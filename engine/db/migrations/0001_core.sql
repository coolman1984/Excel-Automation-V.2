-- Core engine tables. Project data lives in tables created per source
-- (stg__<source>, clean__<source>, hist__<source>, view v_<source>).

CREATE TABLE IF NOT EXISTS schema_migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,            -- RUNNING | PASS | WARNING | BLOCK
    rows_in      INTEGER NOT NULL DEFAULT 0,
    rows_clean   INTEGER NOT NULL DEFAULT 0,
    rows_rejected INTEGER NOT NULL DEFAULT 0,
    message      TEXT NOT NULL DEFAULT '',
    manifest_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS run_files (
    run_id       TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    file_name    TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    modified_at  TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    rows_read    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, source_id, file_name)
);

CREATE TABLE IF NOT EXISTS quarantine (
    run_id      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    excel_row   INTEGER NOT NULL,
    rule        TEXT NOT NULL,
    field       TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'reject',
    row_json    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_quarantine_run ON quarantine(run_id);

CREATE TABLE IF NOT EXISTS reconciliation (
    run_id      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    check_name  TEXT NOT NULL,
    expected    TEXT NOT NULL,
    actual      TEXT NOT NULL,
    difference  TEXT NOT NULL DEFAULT '0',
    status      TEXT NOT NULL,             -- PASS | WARNING | BLOCK
    PRIMARY KEY (run_id, source_id, check_name)
);

CREATE TABLE IF NOT EXISTS metrics (
    run_id      TEXT NOT NULL,
    metric_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,             -- kpi | series | table
    title       TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, metric_id)
);

CREATE TABLE IF NOT EXISTS insights (
    run_id      TEXT NOT NULL,
    insight_id  TEXT NOT NULL,
    severity    TEXT NOT NULL,             -- info | watch | action
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, insight_id)
);

CREATE TABLE IF NOT EXISTS run_events (
    run_id     TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    at         TEXT NOT NULL,
    step       TEXT NOT NULL,
    percent    INTEGER NOT NULL,
    message    TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
