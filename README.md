# RAEE-Lite

**The evidence layer for AI-assisted coding.**

> Your coding agent wrote the code. RAEE-Lite helps you see what was actually checked—and what remains unproven.

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [Deutsch](docs/README.de-DE.md) · [Español](docs/README.es-ES.md)

### Try the public release candidate

**Status: public source preview, not a stable or security-certified release.** The code is available in the [v0.10.0rc2 review branch](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2) and [release PR #2](https://github.com/jinxinche/RAEE/pull/2), while the default `main` branch is still awaiting the reviewed source merge. The candidate has local test results, but protected-main cross-platform CI and independent GitHub attestation verification remain pending.

Try it from a **disposable Python environment**, after inspecting the source:

```bash
git clone --branch release/raee-lite-v0.10.0rc2 https://github.com/jinxinche/RAEE.git
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

[Reproduction details](https://github.com/jinxinche/RAEE/blob/release/raee-lite-v0.10.0rc2/examples/DEMO.md) · [Security boundaries](https://github.com/jinxinche/RAEE/blob/release/raee-lite-v0.10.0rc2/SECURITY.md) · [Report a reproducible issue](https://github.com/jinxinche/RAEE/issues/new) · [Local validation and pending release gates](https://github.com/jinxinche/RAEE/pull/2)



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

**Publication status:** The installable CLI source is accessible in the linked review branch, not yet merged into the default branch. No stable GitHub release or PyPI distribution is claimed.

After installing the release candidate from a reviewed local source package:

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

**Current status: public release candidate available for early feedback; independent security review and cross-platform signed CI acceptance remain pending.** Please do not interpret the README as a claim of production readiness.

## Contributing and license

Issues, reproduction cases, accessibility improvements and translations will be welcome after the source release. Please never submit credentials, private agent conversations, or proprietary code in a public issue.

The repository's software license is [MIT](LICENSE). The linked research preprint has its own publication license.
