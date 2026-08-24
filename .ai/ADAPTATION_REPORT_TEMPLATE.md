# Adaptation report - <ProjectName>

**Date:** <date>  ·  **Business owner:** <name>  ·  **Agent session:** <id>

## 1. What was asked for

<one paragraph in the business owner's own words>

## 2. Business meaning confirmed

| Question | Answer | Approved by |
|---|---|---|
| What one row represents | | |
| What identifies the same record | | |
| Corrections allowed | | |
| Meaning of a disappearing record | | |
| Totals that prove correctness | | |
| Decision the page supports | | |

Anything still `PENDING_APPROVAL`: <list, or "none">

## 3. What was changed

| Level | Changed? | What |
|---|---|---|
| Reused as-is | | |
| `project.json` | | |
| `sql/metrics.sql` | | |
| Project-owned Python | | |
| Shared engine | **should be "no"** | |

If the shared engine was changed, state the evidence that no configuration could
express the need, and which tests were added.

## 4. Proof

| Gate | Result |
|---|---|
| `PROJECT_TOOL doctor` | |
| `PROJECT_TOOL run` (status, rows, totals) | |
| Control totals matched the owner's own figure | |
| Identical rerun created no duplicates | |
| `PROJECT_TOOL test` | |
| `PROJECT_TOOL package verify` | |
| Private runtime included | |
| Started on a clean Windows machine | PASS / CONDITIONAL - <why> |

Any gate that could not be run here is marked `CONDITIONAL` and named. It is
never reported as passed.

## 5. Delivered

- `release/<ProjectName>.zip`
- What the user does: extract → double-click `START.bat` → browser opens.

## 6. Known limits and next steps

<list>
