# Green tests are not the same as verified requirements

*An engineering note about RAEE-Lite, a public, local-first release candidate for AI-assisted coding.*

A coding agent reports that a change is complete. The terminal shows a green test. The feature appears to be fixed.

But what, precisely, has been verified?

A green test establishes only that **a particular command, in a particular environment, on a particular source state, returned an observed result**. It does not prove that a separate user requirement was exercised by that test.

This is a practical problem in AI-assisted software development: natural-language claims, modified source, shell output, CI metadata, and user acceptance criteria are routinely compressed into the same label — *done*.

## A small, reproducible example

Suppose you ask your coding agent to make a signup function reject invalid email addresses. Your repository already contains this passing smoke test:

```python
def test_smoke():
    assert 1 + 1 == 2
```

That test tells us nothing about input validation. Neither does a successful `pytest` invocation make the coverage gap disappear.

[RAEE-Lite](https://github.com/jinxinche/RAEE) is a Python CLI that maintains **separate roles** for requirement intent, source changes, checks actually performed, the execution environment, and untested boundaries.

The [v0.10.0rc2 source candidate](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2) is public for review; it is **not** yet a stable, independently security-audited release. Install only after reviewing the code, preferably in a disposable virtual environment.

In a clean temporary project directory, try:

```bash
raee-lite init
raee-lite add "Signup rejects invalid email addresses"
raee-lite expect --for R1 --kind unit
raee-lite status
raee-lite check
```

The requirement remains `UNTESTED`; the CLI produces an evidence-gap report. `raee-lite status` intentionally exits with code 1 to surface the gap. The default `check` in this demonstration does **not execute project-owned tests**.

The tool does **not** claim to solve test generation, prove program correctness, or infer complete semantic coverage. Instead, it tries to prevent *missing evidence* from being quietly rebranded as *successful validation*.

## Why keep evidence types distinct?

**Intent is not implementation.** A natural-language requirement helps define a target behavior; it cannot certify the code.

**A diff is not a proof.** Seeing changed files documents what moved, not whether the change meets the requirement.

**An agent transcript is not an execution receipt.** Agent logs can be useful historical records, but they are untrusted and potentially incomplete.

**One passing check is not all passing checks.** Even a real test result is meaningful only for its assertions, source revision, environment, and execution context.

**Environment and provenance matter.** A signed CI claim may authenticate *who issued a statement*, yet it does not automatically establish that the tests were well designed or comprehensive.

**Uncertainty is a first-class output.** Untested requirements, stale observations, missing modalities of evidence, and unsupported external claims must remain visible.

## Source-state freshness is a useful second demonstration

An observed check should be tied to the code state on which it actually ran. If the user edits the code afterward, a tool should not automatically reuse the old result as if the new revision were tested.

The project's [longer reproducible demo](https://github.com/jinxinche/RAEE/blob/release/raee-lite-v0.10.0rc2/examples/DEMO.md) demonstrates the separation between an unrelated green check and a requirement that remains untested, then modifies the source to make previous evidence stale.

This is **a narrower goal than automated software verification**. Narrower, explicit claims make a verification workflow more auditable.

## What this project is—and is not—ready for

The public v0.10.0rc2 branch contains Python source, tests, CLI workflows and a candidate GitHub Actions provenance chain. Local tests and synthetic attack cases have been executed, but the release has **not yet completed independent security review, protected-main cross-platform CI acceptance, or a real GitHub Artifact Attestation verified from another environment**.

No proof of these missing steps is implied by this article or by a green PR risk-inventory job. This is an **early-access, source-review project**. The goal of this public preview is to discover where the evidence taxonomy and importers produce false confidence or miss legitimate signals.

If you use Codex, Claude Code, or another coding agent, I would be interested in one **sanitized minimal reproduction** of an agent claiming completion while the actual executed checks fail to cover the requirement. Avoid sharing raw agent logs, secrets, private repository code, or access tokens.

- [Project and four-language README](https://github.com/jinxinche/RAEE)
- [Public source release candidate](https://github.com/jinxinche/RAEE/pull/2)
- [Open a reproducible issue](https://github.com/jinxinche/RAEE/issues/new)

## Research inspiration — not software validation

The name RAEE derives from the **role-aware evidence organisation** principle in a separate research preprint: Hu, J., Jin, X., Song, Y., Chen, Z. & Xin, L. (2026), *Restricted Multimodal Oncology AI: Role-Aware Evidence Organisation and Cross-Domain Transfer Boundaries*, Research Square, [DOI:10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1).

That study concerns restricted oncology AI. It did **not** experimentally evaluate RAEE-Lite, secure GitHub workflows, or certify this coding tool.

*Document status: technical preview prepared for community discussion. Avoid reposting it unchanged to many communities; tailor the discussion to the community's own rules and interests.*
