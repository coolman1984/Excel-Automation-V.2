# Single product goal

This template has one job:

```text
INPUT
Template ZIP + Excel files + business explanation

        ↓

CHATGPT WORK / AI AGENT
Understand the files and business meaning
Reuse the existing engine
Change configuration first
Add small project SQL or Python only when required
Run the tests
Build the final offline package

        ↓

OUTPUT
ProjectName.zip

        ↓

FINAL USER
Extract → double-click START → browser opens → work offline
```

## Product rule

> If the final user needs to understand how the engine works, the template has
> failed.

The engine remains complete and testable. Its database, SQL, Python runtime,
packages, local API, configuration, migrations, logs, ports, build tools, Git,
and agent instructions are internal implementation details. They are never
normal operating steps and never appear as choices the final user must make.

## Two different packages

| Package | Used by | Contents |
|---|---|---|
| Template ZIP | ChatGPT Work or another coding agent | Reusable engine, source, tests, project map, build tools |
| `ProjectName.zip` | Final non-technical user | `START.bat`, `QUICK_START.html`, and the internal ready-to-run application |

Do not put the source/update kit, wheelhouse, Git files, test commands, or
technical setup tools at the root of the final user's package. They belong to
the template/build package, not to the operating product.

## Adaptation order

```text
reuse as-is
→ configure mappings and rules
→ add project-owned SQL
→ add isolated project-owned Python only if SQL is unsuitable
→ change shared engine only after a proven reusable gap
```

Rebuilding is allowed only when code or dependencies require it. Rebuilding
must never mean asking the final user to install anything.

## Final acceptance

The adaptation is complete only when:

1. the business meaning and trusted totals are approved;
2. critical tests and reconciliations pass;
3. the package runs offline without system Python, Node, Git, a terminal,
   administrator rights, or runtime downloads;
4. the final ZIP has the simple operator shape enforced by
   `PROJECT_TOOL package verify`;
5. the final user can extract, double-click `START.bat`, and use the browser
application without seeing a technical decision.
