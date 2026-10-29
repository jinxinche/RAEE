# RAEE-Lite

**The evidence layer for AI-assisted coding.**

> Your coding agent wrote the code. RAEE-Lite helps you see what was actually checked—and what remains unproven.

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [Deutsch](docs/README.de-DE.md) · [Español](docs/README.es-ES.md)

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

**Publication status:** This newly created public repository is being prepared for its first source release. The CLI source and installable package are **not yet published in this repository**. The commands below document the development candidate's intended local workflow; do not treat them as an install-from-GitHub instruction yet.

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

**Current status: documentation and first public release preparation.** Please do not interpret the README as a claim of production readiness.

## Contributing and license

Issues, reproduction cases, accessibility improvements and translations will be welcome after the source release. Please never submit credentials, private agent conversations, or proprietary code in a public issue.

The repository's software license is [MIT](LICENSE). The linked research preprint has its own publication license.
