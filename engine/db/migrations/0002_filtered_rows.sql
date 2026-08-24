-- Rows the business deliberately excluded (source filters). They are recorded
-- so reconciliation can prove where every single row went, instead of treating
-- the leftovers as "probably out of scope".

CREATE TABLE IF NOT EXISTS filtered_rows (
    run_id     TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    excel_row  INTEGER NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, source_id, file_name, excel_row)
);
