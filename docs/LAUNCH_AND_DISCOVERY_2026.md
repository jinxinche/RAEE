# RAEE-Lite — discoverability and launch playbook (2026-10-29)

**Status:** Public v0.10.0rc2 **candidate** under [PR #2](https://github.com/jinxinche/RAEE/pull/2). Do not announce an independently security-certified product, a stable v1.0, published PyPI package, or a cryptographically verified CI run until those facts have been checked.

## Positioning: one understandable problem

**One-sentence headline:** RAEE-Lite makes unverified requirements visible when AI coding agents say the work is done.

**Long-form pitch:** AI coding agents can say “done” after running a test that does not cover the feature you asked for. RAEE-Lite is a local-first, provider-neutral Python CLI that separates user intent, code changes, actual verification, execution environment and unknowns. It can detect when old evidence is stale after code changes and generates machine-readable reports. It does **not** prove code correctness and does **not** automatically infer test coverage.

## GitHub About — ready to paste

**Repository description (English):**
Offline evidence firewall for AI-assisted coding. Track what was checked, what changed, and what remains unverified.

**Suggested topics (10, all lowercase):**
`ai-coding` · `coding-agents` · `developer-tools` · `code-review` · `testing` · `verification` · `cli` · `python` · `reproducibility` · `trustworthy-ai`

**Website (until an official documentation site exists):**
`https://github.com/jinxinche/RAEE#readme`

Set these under the repository's **About** gear. Repository metadata cannot be changed just by adding this file.

Once you've reviewed and installed the source candidate locally, use `bash scripts/configure_discovery.sh --check` to inspect GitHub's actual About/Topics. After explicit owner consent, `bash scripts/configure_discovery.sh --apply` updates the metadata and reads it back. **The existence of the script does not mean the About/Topics are already configured.**

**Repository naming:** The public URL is currently `jinxinche/RAEE`, while the application is called **RAEE-Lite**. Consider renaming the repository to `raee-lite` **after** updating code, CI identity checks, citations, links and provenance rules. Do not rename silently during a release candidate: current attestation verification pins `jinxinche/RAEE`.

**Social preview asset:** Once a tested preview asset exists, use GitHub Settings → Social preview; prefer 1280 × 640 px, under 1 MB. Do not insert fabricated usage screenshots or synthetic “verified” badges.

## Four-language social introduction (ready to adapt)

### English — Show HN / DEV (after a working public release)

**Headline:** Show HN: RAEE-Lite — a local evidence gap checker for AI-generated code

> A coding agent says “done.” But the tests it ran might not cover the requirement you actually asked for. I built RAEE-Lite to keep user intent, changed files, observed checks, and untested boundaries separate. It runs locally, requires no LLM API key for the core workflow, and intentionally marks a requirement UNTESTED when no matching evidence is declared. The first public build is a release candidate; this is not a security audit or a correctness prover. The reproducible demo is in the README. Feedback on blind spots and supported agent-log formats is welcome: https://github.com/jinxinche/RAEE

### 简体中文 — 开发者社区

**标题：** AI 编程助手说“已完成”，测试通过真的等于需求已验证吗？

> 我在开发一个开源的本地工具 RAEE-Lite，把用户需求、代码变更、真实执行过的检查、运行环境与未验证边界分别记录。即使某个测试是绿的，只要没有对应需求的证据，仍会显示 UNTESTED。核心流程不需要调用大模型 API。它目前是候选版本，不是安全认证，也不会自动证明代码正确。欢迎开发者用可复现案例指出误报和漏报：https://github.com/jinxinche/RAEE

### Deutsch — Entwickler-Community

**Titel:** Grün ist nicht automatisch verifiziert: RAEE-Lite für KI-generierten Code

> Wenn ein Coding-Agent „fertig“ meldet, ist damit noch nicht bewiesen, dass die Nutzeranforderung getestet wurde. RAEE-Lite trennt Anforderungen, Änderungen, ausgeführte Prüfungen und offene Evidenzlücken. Der Kern funktioniert lokal ohne LLM-API-Schlüssel und zeigt ausdrücklich UNTESTED, wenn ein Nachweis fehlt. Noch Release Candidate, kein Sicherheitszertifikat. Rückmeldungen zu reproduzierbaren Fehlfällen sind willkommen: https://github.com/jinxinche/RAEE

### Español — comunidad de desarrollo

**Título:** Pruebas en verde no significan requisitos verificados: RAEE-Lite

> Que un agente de programación diga «terminado» no demuestra que haya probado lo que pediste. RAEE-Lite separa requisitos, cambios, comprobaciones ejecutadas y evidencias que faltan. Funciona localmente y la función básica no necesita claves de una API de IA. Si falta evidencia de un requisito, se indica UNTESTED. Todavía es una versión candidata, no una certificación de seguridad. Agradecemos casos reproducibles y comentarios: https://github.com/jinxinche/RAEE

## Release-day launch sequence (do not publish before these gates)

1. Merge the trusted inspector hotfix; verify its Git blob on `main`.
2. Review and merge the release source under effective branch protections without bypassing failed required checks.
3. Obtain actual GitHub Actions pass/fail evidence for Python 3.10 and 3.13 across Linux, Windows and macOS.
4. Obtain real GitHub Artifact Attestation and independently verify the repo, signer workflow, source ref, full commit SHA, and report hash.
5. Tag a GitHub **Pre-release** with a source archive, wheel if properly built, SHA-256 sums, limitations, and link to test run IDs.
6. Publish a 30–60 second **real CLI demo** showing a requirement labeled `UNTESTED` after a green unrelated test and the source fingerprint becoming stale after a code edit. No fabricated screenshots or performance claims.
7. Share once in appropriate communities (Show HN, DEV, a relevant Reddit community if permitted by its rules, Python forums, LinkedIn), and reply to actual bugs. Do not spam, buy stars, or manipulate rankings.

## What to measure

Track a 7-day release window with unique repository visits (GitHub Insights → Traffic), demo completions, reproducible bug reports, repeat contributors and stars as a **secondary** indicator. GitHub traffic has limited retention; export real numbers, not estimates. The objective is **useful installations and honest technical feedback**, not an invented star-count goal.

## Preprint citation and claims

The research preprint [Hu et al. (2026), DOI:10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1) motivated **role-aware evidence separation** in another domain. It **did not evaluate** RAEE-Lite. Cite the research origin and the software repository separately. Do not imply medical validity transfers to software security.
