-- Which file content has already been processed for each source, so a run
-- reprocesses only what is actually new. Keyed on content, not file name: a
-- renamed-but-identical file is still recognised, and identical bytes under an
-- unchanged name are never re-extracted or re-merged.

CREATE TABLE IF NOT EXISTS processed_files (
    sha256      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    first_run   TEXT NOT NULL,
    last_run    TEXT NOT NULL,
    rows_read   INTEGER NOT NULL DEFAULT 0,
    outcome     TEXT NOT NULL DEFAULT 'PROCESSED',
    PRIMARY KEY (sha256, source_id)
);
CREATE INDEX IF NOT EXISTS ix_processed_files_source ON processed_files(source_id);
