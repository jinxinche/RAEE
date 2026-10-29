# RAEE-Lite

**The evidence layer for AI-assisted coding.**

> Your coding agent wrote the code. RAEE-Lite helps you see what was actually checked—and what remains unproven.

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [Deutsch](docs/README.de-DE.md) · [Español](docs/README.es-ES.md)

**Release:** `v0.10.0rc2` candidate · **License:** MIT · **Python:** 3.10+ · **No AI API key required for core offline checks**

### A 30-second evidence-gap demo

Install the reviewed candidate from [PR #2](https://github.com/jinxinche/RAEE/pull/2) in a disposable Python environment first, then try this inside an empty temporary project directory:

```bash
raee-lite init
raee-lite add "Signup rejects invalid email addresses"
raee-lite expect --for R1 --kind unit
raee-lite status
raee-lite check
```

Expected result: `R1: UNTESTED` and `EVIDENCE_GAPS`. **No repository-owned tests are executed.** With an unverified requirement, `raee-lite status` intentionally exits with status **1**; that is an evidence-gap signal, not a CLI crash. The subsequent nonexecuting `raee-lite check` returns status **0** in the demonstrated case. A stated requirement is not evidence of its completion. See the [longer reproducible demo](examples/DEMO.md).

<details>
<summary>Where to find the source while this release is under review</summary>

The CLI source currently lives in the review branch [`release/raee-lite-v0.10.0rc2`](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2), not yet on default `main`. Review the code and PR before installing:

```bash
git clone --branch release/raee-lite-v0.10.0rc2 https://github.com/jinxinche/RAEE.git
cd RAEE
python -m venv .venv
# Activate .venv, then run:
python -m pip install --no-deps .
raee-lite --version
```

This is a source release candidate; **no PyPI availability or production security assurance is claimed**. The default nonexecuting commands are suitable for inspection; running project-owned checks requires explicit opt-in and a trusted environment.
</details>

### New: proof-obligation trace (experimental)

`raee-lite trace --for R1 --json` emits a **read-only evidence graph** connecting user intent, each declared verification scope, its last self-labelled execution receipt, and source fingerprint relevance. Missing, stale, partial and failed scopes remain explicit; even an `OBSERVED_PASS` never becomes a semantic correctness proof. [Trace example and graph semantics](docs/PROOF_OBLIGATION_TRACE.md).

### What you get—and what you do not

| Observed evidence | What RAEE-Lite can report | What it cannot conclude |
| --- | --- | --- |
| Coding agent says a fix is done | Historical, **unverified** agent claim | That the code works |
| Files changed | Diff and source-state fingerprint | That the requirement was satisfied |
| Unit test returns exit 0 | Which test ran, on which source state | That the test covered the required behavior |
| Source modified after testing | Previously observed evidence becomes stale | That all hidden failures are detected |
| CI provenance signature verified | Authenticity of an attested claim | General absence of defects |

**Why this matters:** In AI-assisted coding, green tests are often mistaken for verified user intent. RAEE-Lite deliberately reports the **unverified gap** instead of manufacturing confidence.

[How the evidence model works](examples/EVIDENCE_CONTRACTS.md) · [Security boundaries](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Release review](docs/SOLO_MAINTAINER_VALIDATION.md)



## Why this project?

AI coding agents can generate, change, and test code quickly. But a successful command, a reassuring agent message, or a green checkmark does **not** necessarily establish that a user's requirement was fulfilled.

**RAEE-Lite** applies *role-aware evidence engineering* to software development. Instead of collapsing different signals into a single “verified” label, it keeps five evidence roles separate:

| Evidence role | Question | Boundary |
| --- | --- | --- |
| **Intent** | What did the user request? | A written requirement is not proof of implementation. |
| **Change** | What code and repository revision changed? | A diff does not prove correctness. |
| **Verification** | What checks actually ran, and what were their results? | An exit code of zero does not guarantee meaningful coverage. |
| **Environment** | Where and under which conditions were checks executed? | An environment description alone is not a trusted identity. |
| **Boundary** | What is missing, stale, excluded, or untested? | Unobserved behavior must not be represented as verified. |

## Intended workflows

The development candidate includes:

- **Read-only preflight checks** for repository and CI configuration risks.
- **Evidence contracts** connecting user-stated requirements to expected check categories.
- **Selected Codex / Claude Code log import**, with agent transcripts explicitly marked as historical, unverified evidence.
- **Local check recording** and source-state freshness detection.
- **Base/Head evidence comparisons** for pull-request review.
- **HTML, Markdown, JSON and SARIF reports**, plus optional isolated execution and provenance verification paths.

The design distinguishes **an agent's claim**, **a locally observed command**, and **an externally authenticated CI provenance statement**. None of these alone proves that software is free of defects.

## Getting started

**Publication status:** Source code is public on the review branch linked above; the default branch still awaits reviewed release integration. Do not claim stable release, independently verified provenance, or PyPI publication.

After installing a reviewed release candidate:

```bash
raee-lite preflight     # Read-only inspection
raee-lite doctor        # Discover plausible checks without executing them
raee-lite check         # Generate an evidence-gap report
```

The default workflow does not run project-owned scripts. Executing tests is an explicit opt-in and must be limited to code and environments you trust.

## Privacy and trust boundaries

- Imported agent logs are **untrusted input**, not instructions.
- The importer is designed to retain limited summaries, rather than raw prompts or terminal outputs. Sanitize logs before sharing them.
- Static checks and report generation are **not** security certification.
- Docker-based isolation is **not** a substitute for a hardened virtual machine or independently reviewed sandbox.
- A digital signature authenticates a statement's provenance; it does **not** prove that the statement or its tests are sufficient.
- Real-world Codex/Claude compatibility, cloud CI attestations, and independent security validation remain acceptance work—not completed guarantees.

## Research origin

RAEE-Lite takes inspiration from the **role-aware evidence organisation** principle proposed in a separate oncology AI research preprint:

> Hu, J., Jin, X., Song, Y., Chen, Z., & Xin, L. (2026). *Restricted Multimodal Oncology AI: Role-Aware Evidence Organisation and Cross-Domain Transfer Boundaries*. Research Square, preprint, version 1. DOI: [10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1).

In that study, evidence roles are assigned to biological data sources before multimodal integration. **RAEE-Lite translates the principle of non-interchangeable evidence roles into a software-engineering workflow.** The preprint does **not** present or experimentally validate this coding tool, its security architecture, or its performance.

See [the research citation](REFERENCES.bib). If you use the software, cite the software repository separately from the research preprint.

## Roadmap and project status

The near-term priorities are a reviewed public source release, real GitHub Actions results on Linux/Windows/macOS, authentic artifact attestations, consented real-world agent-log benchmarks, and external security review.

**Current status: public source under PR review; real cross-platform trusted CI and independent provenance acceptance remain pending.** Please do not interpret the README as a claim of production readiness.

## Contributing and license

Issues, reproduction cases, accessibility improvements and translations will be welcome after the source release. Please never submit credentials, private agent conversations, or proprietary code in a public issue.

The repository's software license is [MIT](LICENSE). The linked research preprint has its own publication license.
