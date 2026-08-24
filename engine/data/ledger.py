"""The processed-file ledger.

Without it, every run reprocesses every file ever supplied: the inbox never
empties, the same bytes get re-extracted and re-merged run after run, and the
"rows read from your files" figure shown to the operator grows without bound
even though nothing new has happened. Two consecutive runs against the same
single file used to report double the row count of the file itself.

Skipping is keyed on content (``sha256``), not file name, so a renamed but
otherwise identical file is still recognised, and a file whose content
genuinely changed - even under an unchanged name - is never skipped.

A source with nothing new this run is not processed at all: its staging,
clean and history steps are simply not called, leaving trusted history
exactly as it was. Calling ``history.apply`` with zero rows would be actively
wrong for a SNAPSHOT or REPLACE_PERIOD source - both close every record not
touched by the current run, so an empty run would read as "everything just
disappeared" and close the entire trusted table. Skipping the source
altogether, rather than running it on an empty file list, is what keeps a
quiet day quiet instead of destructive.
"""

from __future__ import annotations

import datetime as _dt

PROCESSED = "PROCESSED"
FAILED = "FAILED"


def already_processed(connection, source_id: str, sha256: str) -> bool:
    row = connection.execute(
        "SELECT outcome FROM processed_files WHERE sha256 = ? AND source_id = ?",
        (sha256, source_id)).fetchone()
    return row is not None and row["outcome"] == PROCESSED


def record(connection, source_id: str, file_name: str, sha256: str, run_id: str,
          rows_read: int, outcome: str = PROCESSED, now: str | None = None) -> None:
    now = now or _dt.datetime.now().isoformat(timespec="seconds")
    existing = connection.execute(
        "SELECT first_run FROM processed_files WHERE sha256 = ? AND source_id = ?",
        (sha256, source_id)).fetchone()
    first_run = existing["first_run"] if existing is not None else run_id
    connection.execute(
        "INSERT OR REPLACE INTO processed_files(sha256, source_id, file_name, first_run,"
        " last_run, rows_read, outcome) VALUES (?,?,?,?,?,?,?)",
        (sha256, source_id, file_name, first_run, run_id, rows_read, outcome))


def has_ever_succeeded(connection, source_id: str) -> bool:
    """True once at least one file has ever been successfully processed for
    this source, in this run or any earlier one.

    This is what lets a required source stay required only for its first
    file: once trusted history exists, a day with nothing new - the file
    already archived away, or genuinely not re-supplied - is a quiet, safe
    skip rather than a block. Blocking every day a rarely-changing master-data
    file is not re-uploaded would be exactly the kind of AI-in-the-loop
    babysitting this feature exists to remove.
    """

    row = connection.execute(
        "SELECT 1 FROM processed_files WHERE source_id = ? AND outcome = ? LIMIT 1",
        (source_id, PROCESSED)).fetchone()
    return row is not None


def split(connection, source_id: str, files: list, reprocess_identical: bool
         ) -> tuple[list, list]:
    """Split discovered files into ``(new, already_processed)``.

    ``files`` is a list of :class:`engine.excel.discovery.DiscoveredFile`.
    ``reprocess_identical`` opts a source out of skipping entirely, for a
    source where the same bytes are expected to legitimately mean something
    different each time it arrives (rare; off by default).
    """

    if reprocess_identical:
        return list(files), []
    new_files, seen_before = [], []
    for item in files:
        (seen_before if already_processed(connection, source_id, item.sha256) else new_files
        ).append(item)
    return new_files, seen_before
