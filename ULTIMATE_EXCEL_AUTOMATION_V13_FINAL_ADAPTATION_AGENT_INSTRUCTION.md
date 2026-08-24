# Ultimate Excel Automation V13
## Final Adaptation Agent Instruction for ChatGPT / Claude

**Status:** End-stage adaptation authority — implemented template contract  
**Purpose:** Use only after the reusable Template ZIP already exists  
**Primary AI user:** ChatGPT, Claude, or another capable coding/adaptation agent  
**Final human user:** Non-technical business user  
**Language:** English  
**Supersedes:** V11/V12 for the final adaptation stage. V13 implementation state and tests are the current technical evidence.

---

# 0. The operating mode

You are **NOT building an Excel automation platform**.

You are receiving an already-built reusable Template ZIP and adapting it to one business case.

Your job is:

```text
INPUT
Ready Template ZIP
+ New Excel files
+ Plain business explanation / required logic

        ↓

AI ADAPTATION AGENT
Understand the files and business meaning
Reuse the existing engine
Configure mappings and rules
Add only the smallest project-specific logic
Run focused verification
Build the final offline package

        ↓

OUTPUT
ProjectName.zip

        ↓

FINAL USER
Extract ZIP
Double-click START
Use the finished local web application
```

The template already contains the reusable technical foundation.

Do not redesign it.
Do not rebuild it from zero.
Do not replace it with a smaller unrelated solution.
Do not remove proven capabilities just to reduce implementation effort.

---

# 1. Non-negotiable objective

The adaptation must produce a unique working project while preserving the reusable engine.

The expected adaptation order is always:

```text
1. Reuse an existing capability as-is.
2. Change project configuration and mappings.
3. Add or change project-owned SQL.
4. Add isolated project-owned Python only if SQL is unsuitable.
5. Change shared engine code only if a genuine reusable gap is proven.
```

For a normal project, the expected shared-engine change count is:

```text
ZERO
```

The business logic changes.
The reusable platform does not.

---

# 2. What the AI receives

The user provides:

1. the reusable Template ZIP;
2. one or more representative Excel files;
3. a plain-language explanation of the business process;
4. the expected KPIs, calculations, checks, outputs, and decisions;
5. the expected update frequency: daily, weekly, monthly, or manual.

The AI must extract the business meaning from these inputs and use the existing template architecture.

Do not ask the user to choose technical architecture.

Do not ask about:

- DuckDB versus another local database;
- Python packages;
- JavaScript libraries;
- local ports;
- server frameworks;
- packaging tools;
- folder structure;
- migrations;
- runtime installation;
- Git;
- command-line tools.

Ask only business questions that are genuinely blocking correctness.

---

# 3. First actions after receiving the files

Use this order:

```text
1. Extract the Template ZIP into a working directory.
2. Read PROJECT_SKILL.md.
3. Read .ai/CURRENT_STATE.md.
4. Read .ai/PROJECT_MAP.md.
5. Read only the files routed by the map.
6. Inspect the provided Excel files safely.
7. Read the user's business explanation.
8. Build a small adaptation plan.
9. Adapt the project-owned surface first.
```

Do not mass-read the repository.

Do not scan every source file unless a proven dependency requires it.

Do not edit any file before understanding its responsibility and related tests.

---

# 4. Understand the new Excel files

For each source, determine:

- business role;
- workbook identity;
- expected filename pattern;
- required sheet, table, named range, or used range;
- header row;
- row meaning;
- required columns;
- aliases;
- data types;
- business key;
- event date or snapshot date;
- update mode;
- correction behavior;
- duplicate behavior;
- disappearance/deletion meaning;
- relationships to other sources;
- source precedence;
- control totals;
- data-quality rules;
- refresh frequency.

When the workbook is protected and requires Microsoft Excel, use the existing authorized Excel extraction path in the template.

Never bypass the approved protected-file path merely because another parser is easier.

---

# 5. Required recurring runtime behavior

A finished recurring report should behave like this:

1. New source file is detected or selected.
2. The pipeline identifies the report/source type.
3. It confirms the file is stable and ready.
4. Excel opens it through the approved authorized user session when required.
5. The configured worksheet/table/range is discovered.
6. Data is read in large rectangular chunks, never cell-by-cell.
7. Each chunk is staged safely in DuckDB with lineage.
8. Source structure and data quality are checked.
9. New, changed, duplicate, historical, corrected, or snapshot rows are resolved.
10. Trusted history is updated atomically.
11. SQL Server is synchronized when configured and available.
12. Trusted calculations and KPIs run deterministically, normally in SQL.
13. Deterministic insight rules detect meaningful changes.
14. Compact dashboard datasets and JSON are generated.
15. A single optimized self-contained `dashboard.html` is generated.
16. Automated dashboard and reconciliation checks run.
17. The run is marked `COMPLETE` and lineage/evidence is retained.

Canonical visual flow:

```text
📁 New Excel appears
        ↓
🔐 Excel opens protected workbook when required
        ↓
📦 Extract sheets in large chunks
        ↓
✅ Validate structure and source identity
        ↓
🦆 Stage safely in DuckDB
        ↓
🧹 Clean and standardize
        ↓
🕒 Compare with trusted history
        ↓
🗄 Synchronize SQL Server when enabled
        ↓
🧮 Run trusted calculations
        ↓
🔎 Detect meaningful changes and exceptions
        ↓
📊 Generate dashboard datasets
        ↓
📄 Build compact optimized JSON
        ↓
🎨 Generate dashboard.html
        ↓
✅ Run focused automatic checks
        ↓
📁 Publish final trusted report
```

This runtime should work repeatedly without an AI coding agent.

The AI adaptation agent is needed again only when the source structure, business meaning, KPIs, or required output changes.

---

# 6. Excel extraction rules

The existing extraction engine must be reused.

For Excel desktop extraction:

```text
authorized logged-in Windows user
→ Microsoft Excel desktop
→ approved automation path
→ read-only workbook
→ large rectangular reads
→ local staging
```

Mandatory behavior:

- preserve the original workbook;
- record source hash and lineage;
- open read-only;
- never edit the source workbook;
- never use slow cell-by-cell loops for large data;
- read only necessary sheets and columns after discovery;
- use chunk/block reads suitable for large files;
- handle formulas and displayed/cached values consistently;
- handle dates, percentages, currency, blanks, leading zeroes, and large IDs correctly;
- close workbook and Excel safely;
- fail clearly if the authorized Excel session cannot open a protected source.

---

# 7. DuckDB is the local processing foundation

The template should already contain the DuckDB processing engine.

Use it for:

- raw staging;
- typed clean data;
- joins;
- filtering;
- aggregation;
- history comparison;
- KPI calculation;
- dashboard datasets;
- evidence queries;
- fast analytical processing.

Do not move ordinary calculations into browser JavaScript.

Do not reproduce the same trusted formula in several technologies.

The authoritative formula must exist once.

---

# 8. History and recurring updates

The project must correctly support the chosen source behavior:

```text
APPEND
UPSERT
SNAPSHOT
REPLACE_PERIOD
```

For recurring daily, weekly, or monthly files:

- identical reruns must not create duplicates;
- old corrections must update according to approved business rules;
- late-arriving records must behave predictably;
- disappeared records must follow the approved deletion/snapshot rule;
- partial periods must not silently replace complete periods;
- failed processing must not corrupt trusted history;
- the last approved result must remain available after failure.

The user should be able to keep providing the same type of file every period without reconfiguration.

---

# 9. SQL Server synchronization is optional, not the calculation authority

If SQL Server is configured:

```text
Local trusted processing completes
→ synchronization starts
→ row counts and controls reconcile
→ synchronization succeeds
```

If SQL Server is temporarily unavailable:

- do not lose the local trusted run;
- keep the local result available;
- record synchronization as pending/failed;
- retry through the existing template mechanism;
- do not re-extract Excel only because SQL Server synchronization failed.

SQL Server is an optional enterprise synchronization target.

It must not create a second version of business logic.

---

# 10. Trusted calculations

Calculation priority:

```text
project configuration
→ reusable SQL pattern
→ project-owned SQL
→ isolated approved project-owned Python
→ minimal shared-engine improvement
```

Use SQL for most:

- joins;
- sums;
- averages;
- ratios;
- variances;
- targets;
- trends;
- rankings;
- Pareto;
- aging;
- comparisons;
- period logic;
- KPI calculations.

Use Python only when SQL is genuinely unsuitable.

Python must be isolated, deterministic, testable, and use the template's approved project-rule interface.

Never ask an AI model to calculate trusted KPIs from raw business data.

AI may explain verified outputs.
AI may not become the trusted calculation engine.

---

# 11. Deterministic insight engine

Insights should be generated from verified calculations and rules.

Useful insight types include:

- largest increase or decrease;
- unusual deviation from target;
- top contributor;
- worsening category;
- improving category;
- new exception;
- repeated exception;
- abnormal concentration;
- major mix shift;
- threshold breach;
- trend reversal;
- missing or late data;
- data-quality warning.

Each insight should retain evidence such as:

- metric ID;
- period;
- current value;
- comparison value;
- absolute difference;
- percentage difference;
- dimension/category;
- supporting query or row reference;
- quality state.

Do not invent root causes unless the data proves them.

Use wording such as:

```text
"Requires investigation"
```

when the cause is unknown.

---

# 12. Dashboard is already a reusable product feature

Do not build a new dashboard framework for every project.

Reuse the template dashboard system and configure it for the new business case.

The final dashboard should be a modern 2026-style local web dashboard with:

- responsive one-page layout;
- KPI cards;
- interactive charts;
- trend charts;
- comparison charts;
- bar/ranking charts;
- Pareto when useful;
- heatmaps when useful;
- detail tables;
- search;
- dropdown pickers;
- date/period pickers;
- multi-select filters;
- reset filters;
- drill-down or drill-through when configured;
- tooltips;
- insight panel;
- exception panel;
- quality/reconciliation state;
- run history;
- export;
- print;
- light/dark support when available;
- Arabic/English support when configured;
- right-to-left support when Arabic is enabled;
- keyboard accessibility;
- reduced-motion behavior;
- clear empty/loading/error states.

The visual style should feel polished, fast, simple, and business-focused.

Do not expose technical architecture to the final user.

---

# 13. Dashboard data contract

The processing layer should create a compact, optimized dashboard package.

Preferred flow:

```text
trusted calculations
→ approved aggregates
→ dashboard datasets
→ compact JSON
→ dashboard.html
```

The dashboard may filter approved precomputed datasets.

It must not recalculate trusted financial, operational, or quality logic independently.

The displayed number must reconcile to the trusted processing result.

---

# 14. Self-contained offline dashboard

The generated `dashboard.html` should be self-contained for the final report whenever the template supports this mode.

Requirements:

- no CDN;
- no external runtime downloads;
- no internet dependency;
- required scripts/styles/assets embedded or bundled locally;
- optimized JSON size;
- fast opening;
- no broken external references;
- no hidden network calls;
- works from the local application in the approved browser.

The local web application may also serve the dashboard through the existing loopback application boundary.

---

# 15. Fast testing strategy

Do not run the entire heavy test suite after every tiny configuration change.

Use the smallest proof that protects correctness.

## During adaptation

Run focused tests for:

- source mapping;
- required columns and types;
- business keys;
- duplicate handling;
- trusted control totals;
- project calculations;
- relevant history mode;
- dashboard dataset generation.

## Before final delivery

Run the required final gates:

1. representative source extraction;
2. schema validation;
3. population reconciliation;
4. control-total reconciliation;
5. duplicate/history behavior;
6. trusted KPI golden checks;
7. dashboard value reconciliation;
8. dashboard render check;
9. offline/no-external-network check;
10. identical rerun check;
11. failure preserves last-good output;
12. final package verification.

Only run full shared-engine regression when:

- shared engine code changed;
- dependencies changed;
- runtime packaging changed;
- a reusable framework contract changed.

The goal is:

```text
FAST ADAPTATION
+ HIGH CONFIDENCE
+ NO REDUNDANT TESTING
```

Never reduce correctness merely to make tests faster.

---

# 16. Failure safety

A failed run must never replace trusted results.

Required behavior:

```text
build in temporary state
→ validate
→ reconcile
→ publish atomically only after success
```

On failure:

- source remains unchanged;
- trusted history remains safe;
- last-good dashboard remains available;
- failed run is recorded;
- user receives a plain-language reason;
- support detail is available without overwhelming the user.

---

# 17. Final user experience

The final operator package should remain simple:

```text
ProjectName/
    START.bat
    QUICK_START.html
    Application/
```

Normal operation:

```text
Extract ZIP
→ double-click START
→ browser opens automatically
→ add/select new Excel files
→ press Process
→ see real progress
→ review PASS / WARNING / BLOCK
→ use dashboard
→ filter and investigate
→ export/print if needed
```

The user must not need:

- internet;
- system Python;
- Node.js;
- package managers;
- Git;
- terminal;
- editor;
- administrator rights;
- manual server setup;
- manual port selection.

---

# 18. Adaptation rules for ChatGPT / Claude

The AI agent must:

- treat the existing template as valuable working software;
- preserve reusable architecture;
- use project map before reading broadly;
- infer structure from representative Excel files;
- ask only blocking business questions;
- configure first;
- use SQL before Python;
- keep formulas deterministic;
- keep the browser presentation-only for trusted numbers;
- keep recurring runs AI-independent;
- preserve last-good outputs;
- use focused tests during adaptation;
- run final acceptance gates before delivery;
- package the final application;
- return one downloadable `ProjectName.zip`.

The AI agent must not:

- rebuild the whole engine;
- replace the project with a simple script;
- replace the local web application with an Excel workbook;
- replace the application with a static non-interactive report;
- remove DuckDB because another tool seems simpler;
- remove protected Excel support;
- introduce runtime internet requirements;
- calculate KPIs in AI prompts;
- duplicate formulas in SQL, Python, JavaScript, and Excel;
- expose technical setup to the final user;
- claim success when a required environmental proof was not actually run.

---

# 19. Business ambiguity rule

If the user's explanation and Excel files do not prove a business rule:

```text
DO NOT INVENT IT
```

Mark it as:

```text
PENDING_APPROVAL
```

The AI may propose a likely interpretation, but the human business owner approves the meaning.

Examples:

- what defines a duplicate;
- what identifies the same business record;
- whether old records can be corrected;
- what a disappearing record means;
- which source wins;
- which total is authoritative;
- KPI formula meaning;
- target/threshold meaning.

Technical implementation decisions remain the responsibility of the template and the AI adaptation agent.

---

# 20. Final package build

After adaptation:

```text
prepare private application
→ include project configuration
→ include required SQL/Python project logic
→ include runtime and offline assets
→ include local data/bootstrap structures
→ build operator package
→ verify package
→ return ProjectName.zip
```

The package verification must confirm:

- launcher exists;
- application exists;
- no developer junk is exposed at root;
- no package manager is required;
- no system Python is required;
- no runtime internet is required;
- no unsafe path exists;
- startup works as standard user.

---

# 21. Completion checklist

The project is complete only when all applicable items are true:

- [ ] Template reused rather than rebuilt.
- [ ] New Excel sources are understood and mapped.
- [ ] Business keys and update rules are approved.
- [ ] Protected Excel path is preserved when required.
- [ ] Large-range chunk extraction is used.
- [ ] DuckDB staging works.
- [ ] Quality and reconciliation rules pass.
- [ ] History mode behaves correctly.
- [ ] SQL Server synchronization works when enabled or is clearly optional.
- [ ] Trusted calculations pass.
- [ ] Deterministic insights are generated.
- [ ] Dashboard datasets are compact and reconciled.
- [ ] Filters, pickers, charts, details, and insights work.
- [ ] `dashboard.html` works offline.
- [ ] Identical rerun creates no duplicates.
- [ ] Failure preserves last-good trusted output.
- [ ] Final operator package starts without installation.
- [ ] Final user sees only the simple operating experience.
- [ ] `ProjectName.zip` is returned.

---

# 22. Final instruction to the AI agent

When you receive:

```text
Template ZIP
+ Excel files
+ user business logic
```

your role is not to invent a new application.

Your role is to transform the existing reusable template into the user's unique automation project with the smallest correct changes.

The expected outcome is:

```text
New Excel arrives repeatedly
→ source is recognized
→ Excel opens it safely when required
→ data is extracted in chunks
→ data is validated
→ DuckDB processes and preserves trusted history
→ optional SQL Server synchronization occurs
→ deterministic calculations run
→ meaningful changes are detected
→ dashboard datasets are generated
→ optimized JSON is created
→ modern interactive dashboard.html is produced
→ automatic focused checks pass
→ trusted report is published
→ lineage is retained
```

Then return:

```text
ProjectName.zip
```

The non-technical user should only need to:

```text
extract
→ double-click START
→ process the new period's Excel file
→ use the dashboard
```

That is the product.
