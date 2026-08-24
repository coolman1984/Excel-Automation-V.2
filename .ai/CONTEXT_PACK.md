# V14 context pack

## Product in one sentence

Adapt this existing offline Excel automation engine to the user's files and business meaning; do
not rebuild it.

## Runtime flow

```text
New Excel → authorized extraction → validation → local analytical staging → standardization
→ transactional history → deterministic KPIs → evidence-backed insights → compact JSON
→ self-contained dashboard.html → automatic verification → atomic publication
→ optional SQL Server synchronization
```

Persisted states:
`DETECTED → OPENING → EXTRACTING → VALIDATING → LOADING → MERGING → CALCULATING → GENERATING_JSON → GENERATING_DASHBOARD → VERIFYING → COMPLETE`.

## Existing reusable capabilities

- direct `.xlsx`/`.csv` reader and Windows Excel COM adapter;
- large-block extraction and lineage;
- DuckDB production database with SQLite dev/test fallback;
- APPEND, UPSERT, SNAPSHOT, REPLACE_PERIOD history;
- quality rules, quarantine, population/control reconciliation;
- deterministic SQL metrics;
- pre-aggregated analytical cube checked independently;
- evidence-backed configured + automatic insights;
- optional SQL Server synchronization after local success;
- responsive one-page web dashboard, filters, charts, tables, export, print, bilingual/RTL, themes;
- self-contained offline HTML;
- rollback, archive, last-good recovery;
- strict operator ZIP verifier.

## Adaptation surface

Prefer changing only:

1. `projects/<name>/project.json`
2. `projects/<name>/sql/metrics.sql`
3. `projects/<name>/sql/fact.sql`

Use project-owned Python only if SQL is genuinely unsuitable. Shared-engine changes require proof
of a reusable gap.

## Business facts the agent must not invent

Row meaning, business key, correction behavior, disappearance meaning, source precedence,
authoritative totals, KPI formula, target/threshold, and source relationship meaning.

## Delivery rule

Final user receives only a verified `<Name>.zip`; no package manager, internet, terminal, system
Python/Node, Git, or admin rights.
