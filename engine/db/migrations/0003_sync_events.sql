CREATE TABLE IF NOT EXISTS sync_events (
    run_id       TEXT NOT NULL,
    target       TEXT NOT NULL,
    status       TEXT NOT NULL,
    "at"         TEXT NOT NULL,   -- quoted: AT is a reserved word in DuckDB
    detail_json  TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, target)
);
