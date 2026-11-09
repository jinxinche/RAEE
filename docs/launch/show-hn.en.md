# Show HN submission draft

Status: not submitted. The repository owner should review this copy and be available to discuss the project, as required by the [Show HN guidelines](https://news.ycombinator.com/showhn.html).

**Title:** Show HN: RAEE-Lite – track missing and stale checks for AI-written code

**URL:** https://github.com/jinxinche/RAEE

## Optional author comment

I'm sharing RAEE-Lite, a local Python CLI that links requirements to recorded checks and flags stale evidence after source changes.

The runnable example starts with a signup function that accepts everything and a passing arithmetic test. The requirement stays UNTESTED because it has no matching receipt. A linked unit check then fails; a toy fix makes its two assertions pass; a later edit makes that receipt STALE.

The important limitation: users supply the requirement links and check kinds. The tool does not infer semantic coverage. OBSERVED_PASS is a labelled command result, not a proof that the feature is correct.

The README has installation steps, a one-command synthetic demo and a 40-second output replay. Core checks need no model API key. This is an MIT-licensed v0.10.0rc2 source candidate; independent security review and provenance acceptance are still pending.

I'd welcome small examples where the state is misleading or the workflow is cumbersome. AI tools assisted development and preparation of this text; the demo's captured output is included for inspection.
