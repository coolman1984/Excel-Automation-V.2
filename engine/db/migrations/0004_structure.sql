-- Layout rows the source file used for presentation rather than data, and the
-- totals the file states about itself. Both are recorded so an excluded row is
-- always visible, and so a stated total can be reconciled against the rows the
-- engine actually kept.

CREATE TABLE IF NOT EXISTS excluded_rows (
    run_id     TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    excel_row  INTEGER NOT NULL,
    row_class  TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    row_json   TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, source_id, file_name, excel_row)
);
CREATE INDEX IF NOT EXISTS ix_excluded_run ON excluded_rows(run_id);

CREATE TABLE IF NOT EXISTS source_totals (
    run_id     TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    excel_row  INTEGER NOT NULL,
    field      TEXT NOT NULL,
    declared   TEXT NOT NULL,
    data_sum   TEXT NOT NULL,
    covers     TEXT NOT NULL DEFAULT '',
    matched    INTEGER NOT NULL DEFAULT 0,
    confirmed  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, source_id, file_name, excel_row, field)
);

ALTER TABLE run_files ADD COLUMN rows_seen INTEGER DEFAULT 0;
ALTER TABLE run_files ADD COLUMN rows_excluded INTEGER DEFAULT 0;
