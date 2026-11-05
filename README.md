# RAEE-Lite

**The evidence layer for AI-assisted coding.**

> Your coding agent wrote the code. RAEE-Lite helps you see what was actually checked—and what remains unproven.

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [Deutsch](docs/README.de-DE.md) · [Español](docs/README.es-ES.md)

**Release:** `v0.10.0rc2` candidate · **License:** MIT · **Python:** 3.10+ · **No AI API key required for core offline checks**

### Try the public release candidate

**Status: public source release candidate, not a stable or security-certified release.** This repository includes the CLI source and installation metadata. See [PR #13 and its validation runs](https://github.com/jinxinche/RAEE/pull/13) for the dependency audit and cross-platform regression evidence. Independent provenance verification and branch-protection acceptance remain separate release gates.

Try it from a **disposable Python environment**, after inspecting the source:

```bash
git clone https://github.com/jinxinche/RAEE.git
cd RAEE
python -m venv .venv
# Activate the venv using your platform's standard command
python -m pip install --no-deps .
raee-lite --version
```

Inside a fresh, disposable project directory:

```bash
raee-lite init
raee-lite add "Signup rejects invalid email addresses"
raee-lite expect --for R1 --kind unit
raee-lite status
raee-lite check
```

**Expected:** `R1: UNTESTED` and an evidence-gap report. `status` intentionally returns exit code 1 while the requirement has no matching verification evidence; this is not a crash. The nonexecuting `check` command does not run repository-owned tests.

**What makes it useful:** Coding agents' statements, changed files, executed checks and unresolved requirements are *different evidence types*. RAEE-Lite keeps them separate rather than treating a green test as proof that a requested feature works.

[Reproduction details](examples/DEMO.md) · [Security boundaries](SECURITY.md) · [Early-access feedback](https://github.com/jinxinche/RAEE/issues/7) · [Local validation and pending release gates](https://github.com/jinxinche/RAEE/pull/2)

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

**Publication status:** Install from a reviewed checkout of this repository. This remains a release candidate; no stable release, independently verified provenance or PyPI publication is claimed.

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

**Current status: public source release candidate with recorded experimental cross-platform results; protected-main acceptance and independent provenance verification remain pending.** Please do not interpret the README as a claim of production readiness.

The dependency-completeness experiment defines twelve regression jobs: Linux Python 3.10–3.15; Windows and macOS Intel Python 3.10/3.15; macOS ARM64 Python 3.10/3.15. Every job builds and exercises an installed package and runs the full regression gate. Check the [candidate PR and run results](https://github.com/jinxinche/RAEE/pull/13) for the exact validated commit; a workflow definition alone is not passing evidence. This matrix is separate from protected-main acceptance.

Scoped evidence now fails closed when the bounded Python audit finds omitted local imports or cannot finish confidently. It never certifies dependency closure. See [the dependency audit policy](docs/DEPENDENCY_COMPLETENESS_AUDIT.md) for states and limits, and [CONTRIBUTING](CONTRIBUTING.md) for the reproducible development and package checks.

## Community discussion

Have a reproducible example of an AI agent claiming "done" without matching evidence? Join the [early-access feedback thread](https://github.com/jinxinche/RAEE/issues/7). Please share only minimal, sanitized examples.

For developers who wish to write about this project, see the [technical explainer](docs/green-tests-not-verified-requirements.md) and [multilingual community outreach guide](docs/COMMUNITY_OUTREACH_EARLY_ACCESS.md). The latter contains drafts, **not published posts or verified reach metrics**.

## Contributing and license

Issues, reproduction cases, accessibility improvements and translations are welcome. Please never submit credentials, private agent conversations, or proprietary code in a public issue.

The repository's software license is [MIT](LICENSE). The linked research preprint has its own publication license.
