# V13 completion report

## Product outcome

This template now implements the reusable end-stage contract for adapting new Excel business cases
without rebuilding the engine.

### Canonical run

```text
DETECTED → OPENING → EXTRACTING → VALIDATING → LOADING → MERGING → CALCULATING
→ GENERATING_JSON → GENERATING_DASHBOARD → VERIFYING → COMPLETE
```

### Completed reusable capabilities

- authorized Windows Excel COM adapter for protected workbooks;
- direct `.xlsx` / `.csv` reader and large-block extraction;
- DuckDB production backend with development SQLite fallback;
- APPEND / UPSERT / SNAPSHOT / REPLACE_PERIOD history modes;
- transactional trusted history and last-good rollback protection;
- quality checks, quarantine, population and control-total reconciliation;
- deterministic SQL metrics;
- evidence-backed automatic insight generation;
- compact dashboard JSON + automatic self-contained `dashboard.html`;
- modern responsive 2026 dashboard UI with decision signals, KPI cards, health/status, interactive
  filters, charts, searchable/sortable details, exceptions, reconciliation evidence, run history,
  export, print, bilingual RTL and dark/light themes;
- optional SQL Server synchronization after local success with PENDING-safe failure behavior;
- strict operator package verifier, including runtime dependency checks;
- pinned Windows runtime preparation tool for Python, DuckDB, pywin32 and pyodbc;
- V13 agent instructions, project map, context pack and configuration reference aligned to code.

## Verified here

- **159 automated tests passed** in the final V13 suite; one browser-navigation test was skipped because this environment blocks that navigation path.
- The example project has already been run end to end during V13 hardening.
- The redesigned dashboard has been rendered in Chromium at desktop, tablet and mobile widths,
  including Arabic and dark mode, without horizontal overflow or page errors.

## Environment proofs that cannot be substituted by this build environment

A specific customer package is not allowed to claim these as environment-proven until tested there:

1. a real protected corporate workbook opened through Microsoft Excel COM on the authorized Windows
   account;
2. DuckDB running inside the prepared private Windows runtime;
3. real SQL Server synchronization if that project enables it;
4. two runs plus one recovery performed by a representative non-technical operator.

These are acceptance proofs, not missing architecture. The package verifier and Windows checklist
exist to keep them visible rather than pretending they passed.
