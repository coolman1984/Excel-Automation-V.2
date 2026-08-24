# Ultimate Excel Automation V11
## Simple Product Constitution and One-Shot Delivery Plan

**Status:** Approved product direction and implementation authority  
**Date:** 2026-08-19  
**Language:** English  
**Supersedes:** V10 where V10 exposes technical complexity to the final user or treats optional enterprise features as part of the primary product path

---

# 1. The single product goal

This product has one job:

```text
INPUT
Template ZIP
+ Excel files
+ plain business explanation

        ↓

CHATGPT WORK / AI ADAPTATION AGENT
Understand the Excel structure
Understand and confirm the business meaning
Reuse the existing engine
Change configuration and mappings first
Add small project SQL or Python only when required
Change shared engine code only after a proven reusable gap
Run all applicable tests and controls
Build the final offline operator package

        ↓

OUTPUT
ProjectName.zip

        ↓

FINAL USER
Extract ZIP
Double-click START
Browser opens
Use the finished offline web application
```

Everything else is internal machinery.

> If a non-technical user needs to understand how the engine works, the template has failed.

---

# 2. The two packages must never be confused

## 2.1 Template/build package

Used by ChatGPT Work or another coding agent.

It contains:

- reusable application engine;
- source code;
- configuration schemas;
- project map and agent instructions;
- tests and safe fixtures;
- offline build inputs;
- dependency locks;
- packaging and verification tools;
- recovery and release evidence.

This package is technical because the agent is its user.

## 2.2 Final operator package

Used by the non-technical business user.

Its visible root is only:

```text
ProjectName/
    START.bat
    QUICK_START.html
    Application/
```

`Application/` contains the complete private runtime and internal files. The final user does not edit or operate them.

The final package must not place source code, tests, Git files, build tools, wheelhouses, migrations, agent files, configuration editors, or technical setup commands at its root.

---

# 3. Final-user experience

The final user's complete journey is:

```text
Receive ZIP
→ extract once
→ double-click START
→ browser opens automatically
→ add approved Excel files
→ press Process
→ follow real progress
→ review PASS / WARNING / BLOCK
→ use dashboard, history, insights, and exports
```

The user must never be asked to choose or operate:

- Python;
- SQL or a database;
- packages or dependencies;
- a terminal;
- Git or branches;
- configuration files;
- migrations;
- agents or models;
- ports or servers;
- build or packaging tools;
- technical architecture.

Errors must state only:

1. what happened in plain language;
2. whether previous trusted data remains safe;
3. the one next action;
4. a support code with optional collapsed detail.

---

# 4. What remains inside the engine

Simplifying the product surface does not mean deleting capabilities.

The internal engine retains:

- authorized Excel desktop extraction for protected files;
- block-based reads, never cell-by-cell;
- source hashing and lineage;
- raw staging;
- typed clean data;
- quality checks and quarantine;
- exact reconciliation;
- idempotent connected history;
- local analytical database;
- recovery archive;
- deterministic SQL calculations;
- isolated project Python extension when justified;
- evidence-backed insights;
- one-page local web application;
- local loopback application boundary;
- offline assets and private runtime;
- logs, run manifests, recovery, and tests;
- optional enterprise connectors outside the primary path.

The user sees outcomes, not components.

---

# 5. Approved adaptation order

The adaptation agent must use this exact decision order:

```text
1. Reuse an existing capability as-is.
2. Change project configuration or mappings.
3. Add or change project-owned SQL.
4. Add isolated project-owned Python only when SQL is unsuitable.
5. Make the smallest reusable shared-engine change only when evidence proves a real gap.
```

Target for an ordinary project: zero shared-engine changes.

The agent must not:

- rebuild an existing feature unnecessarily;
- copy the engine into each report;
- place business values in shared code;
- calculate the same trusted formula in SQL, Python, JavaScript, Excel, and AI prompts;
- replace the complete application with a workbook, static page, script, or browser-only storage;
- remove dependencies merely to call the package simpler;
- ask the final user to finish installation or configuration.

---

# 6. What the business user provides during adaptation

Ask only questions that affect business correctness:

1. What work should be automated?
2. Which files are used?
3. What does each file contain?
4. What does one row represent?
5. Which values identify the same business record?
6. Can old records be corrected?
7. What does a disappearing record mean?
8. How are the sources related?
9. Which source wins when values disagree?
10. Which totals prove the result is correct?
11. Which KPIs and exceptions matter?
12. What decision should the dashboard support?
13. Who approves the meaning?
14. How often will it run?

Unknown business meaning remains `PENDING_APPROVAL`. The agent may suggest a value but may never approve its own interpretation.

Architecture, storage policy, access, and retention belong to the template and authorized IT/security owners, not to an ordinary business user.

---

# 7. Deterministic internal run

Every operating run follows one trusted order:

```text
discover and copy approved inputs safely
→ validate file identity and completeness
→ extract through the approved adapter
→ stage raw data with lineage
→ validate schema and values
→ quarantine permitted rejects
→ reconcile rows and control totals
→ create typed clean data
→ update history transactionally
→ calculate trusted metrics
→ create evidence-backed insights
→ build dashboard and reports in temporary locations
→ verify numbers, structure, browser, and offline behaviour
→ publish atomically
→ write logs, exceptions, metrics, and run manifest
```

A failed run never replaces the last approved dashboard and never corrupts trusted history.

---

# 8. Trusted calculation rule

Use this priority:

```text
configuration
→ reusable SQL pattern
→ project-owned SQL
→ approved isolated project-owned Python
→ minimal shared-engine change
```

The trusted formula exists once.

The browser displays approved results and filters approved pre-aggregations. It does not become a second calculation engine.

AI may explain verified evidence. AI may not create trusted KPI values, approve failed data, or invent missing meaning.

---

# 9. Offline and one-click rules

Offline means no runtime downloads. It does not mean no dependencies.

The final operator package includes every required runtime, library, native binary, local web asset, migration, schema, and application file.

Normal operation requires:

- no internet;
- no system Python;
- no Node.js;
- no package manager;
- no Git;
- no editor;
- no terminal;
- no administrator rights;
- no Windows Service;
- no firewall or URL-reservation change;
- no machine-wide installation.

The local application may use a loopback-only internal web boundary on `127.0.0.1`; the launcher selects and manages it automatically. The user never chooses a port or manages a server.

---

# 10. Package build contract

The adaptation agent builds in two stages:

## Stage A — private application

Create a complete one-folder Windows application from pinned local inputs. Include the private runtime, all dependencies, application assets, project configuration, and required internal support files.

## Stage B — simple operator ZIP

Assemble:

```text
PROJECT_TOOL package build --project-name "ProjectName" --app-dir <prepared-app> --output-dir release
PROJECT_TOOL package verify --zip release/ProjectName.zip
```

The package verifier must fail when:

- the expected executable is missing;
- an unexpected root entry exists;
- a developer folder is exposed at the root;
- `START.bat` invokes package managers, system Python, Git, elevation, firewall, or network setup;
- the ZIP contains an unsafe path.

---

# 11. Minimum test and acceptance gates

Before the final ZIP is returned:

## Business and data

- business meaning approved;
- required sources identified;
- source files remain unchanged;
- required columns and types validated;
- duplicate policy tested;
- row population reconciles;
- control totals reconcile exactly at the approved precision;
- rejected rows remain visible;
- source relationships validate;
- trusted metrics pass golden tests.

## History and recovery

- identical rerun creates no duplicates;
- late correction behaves as approved;
- a failure rolls back trusted changes;
- last approved dashboard survives failure;
- recovery path is demonstrated or safely simulated.

## Web application

- browser opens automatically;
- no unexpected network requests;
- no raw technical error is primary;
- dashboard values equal trusted calculation evidence;
- filters reconcile;
- Arabic/English, responsive layout, keyboard, focus, print, and reduced motion pass when required.

## Offline package

- complete private runtime included;
- no runtime download;
- standard-user start;
- no elevation or machine mutation;
- two stable production-like runs;
- final operator ZIP shape passes;
- a non-technical operator completes two runs and one recovery.

Any environmental proof that cannot run must remain explicitly `CONDITIONAL`; it may not be called passed.

---

# 12. Optional capabilities stay optional

These may be added later through the same contracts:

- watched folder;
- Data Hub;
- RPA acquisition;
- database or API acquisition;
- company server profile;
- SQL Server synchronization;
- Gauss or another approved AI review layer.

They must not block the local one-click product and must never create a second trusted formula.

---

# 13. Project intelligence stays internal

The template keeps a small map-first agent system so ChatGPT Work can adapt it without reading the whole repository:

- `PROJECT_SKILL.md`;
- `.ai/PROJECT_MAP.md`;
- `.ai/CURRENT_STATE.md`;
- `.ai/CONTEXT_PACK.md`;
- `.ai/ADAPTATION_REPORT.md` or equivalent.

These artifacts belong to the template/build package. They are not operating instructions for the final user.

---

# 14. Current repository reality on 2026-08-19

Repository: `coolman1984/Perfect-Project-Template`

Verified facts:

- the Golden Reference pipeline executes through dashboard JSON using safe fixtures;
- core quality, history, archive, reconciliation, and Factory adaptation logic exist;
- the Factory proves a second report can be generated without changing shared core files;
- the portable verification toolchain passes;
- the operator-package contract, builder, verifier, and tests now implement the simple final ZIP surface;
- the loopback API, complete web rendering, COM production proof, PyInstaller application build, browser verification, and clean Windows proof are not yet complete;
- therefore the template is not yet ready for final non-technical distribution.

No document may describe the project as release-ready until the remaining blocking gates pass.

---

# 15. Implementation order from now

1. Keep this V11 document and `docs/PRODUCT_GOAL.md` as the product authority.
2. Keep the existing deterministic engine; do not restart architecture design.
3. Complete the local application boundary and durable run APIs.
4. Complete the one-page dashboard rendering, filters, story, accessibility, and browser verification.
5. Complete generic authorized Excel COM extraction and prove it on real Windows/Excel files.
6. Pin and package all dependencies in the private one-folder application.
7. Assemble the simple operator ZIP.
8. Run clean offline Windows, identical rerun, failure recovery, and non-technical operator proofs.
9. Mark the template ready only when every release blocker is passed or formally not applicable.

Optional connectors begin only after the local product is ready.

---

# 16. Definition of done

The reusable template is ready only when a fresh ChatGPT Work session can receive:

```text
Template ZIP + representative Excel files + business explanation
```

and return:

```text
ProjectName.zip
```

where a non-technical user can:

```text
extract → double-click START → browser opens → process files → trust results
```

without installing anything, opening a terminal, editing configuration, or understanding the internal engine.

---

# 17. Final operating principle

> Build the technical foundation once. Let the business owner provide meaning. Let ChatGPT Work adapt the smallest necessary surface. Hide the machinery from the final user. Prove the numbers, prove recovery, prove offline startup, and return one ZIP that simply works.
