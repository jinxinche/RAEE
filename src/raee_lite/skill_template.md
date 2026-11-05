---
name: raee-lite
description: Use RAEE-Lite after AI-assisted code edits to separate what changed, which repository checks actually ran, and what is still unverified. Especially useful before saying a task is done, committing, or preparing a PR.
---

# RAEE-Lite evidence check

Use the locally installed `raee-lite` CLI to create evidence-backed handoffs. If the CLI is not installed, explain this and do not claim to have checked anything.

1. Clarify the **user's actual acceptance criteria**. Never replace them with easier proxies merely because an existing test is green.
2. Run `raee-lite doctor` to see what check commands are available. This does not execute project scripts.
3. Run `raee-lite check` to get an initial offline evidence report. It does not execute repository checks.
4. Before using `raee-lite check --run`, obtain the user's authorization for **executing local project scripts** when that permission has not already been given. These scripts are not sandboxed and may access network or secrets. Never bypass consent with the existing shell tool.
5. When appropriate, add a requirement using `raee-lite add "<user acceptance criterion>"`, inspect `raee-lite plan`, ask the user to specify relevant evidence scope via `raee-lite expect --for R1 --kind e2e` when applicable, and run an actual check via `raee-lite run --for R1 --kind e2e -- <command>`. Do **not** label a generic smoke command as end-to-end evidence just to satisfy the contract. An observed exit code of zero is *not* proof the command covers the criterion.
6. Read `.raee/report.md` / `report.json` / `report.sarif` and summarize: confirmed file changes, observed checks, stale or failed results, untested requirements, affected environments, and untested boundaries.
7. When source files change again, run `raee-lite status` to check freshness. Never cite evidence for an earlier source fingerprint as current.

## Reporting rule

Always say **observed pass** rather than **verified correct** unless an independent, scoped behavioral test supports that stronger statement. Missing evidence stays `UNTESTED` or `INSUFFICIENT_EVIDENCE`. High-impact auth, billing, migration or deployment code requires additional human review. Do not invent confidence scores or certifications.
