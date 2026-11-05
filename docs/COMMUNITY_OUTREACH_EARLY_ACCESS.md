# RAEE-Lite — Early-access community outreach kit

**Campaign state (29 October 2026):** Public open-source preview, **v0.10.0rc2 source on a review branch**, not yet merged into default `main`. This is an editorial kit, **not evidence that any off-GitHub post has been published**.

Canonical destination: https://github.com/jinxinche/RAEE

Working source: https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2

Technical explainer: https://github.com/jinxinche/RAEE/blob/main/docs/green-tests-not-verified-requirements.md

Community feedback: https://github.com/jinxinche/RAEE/issues/7

Scientific inspiration: https://doi.org/10.21203/rs.3.rs-10194336/v1 (the preprint **does not validate this tool**).

## What actually makes the project interesting

AI coding assistants often treat “command exited 0” and “user's feature is verified” as the same event. RAEE-Lite treats them as **different evidence**. A declared requirement can be `UNTESTED` even while an unrelated unit test is green. Changed source can invalidate past check evidence, producing `STALE`. The default inspection workflow runs locally and does not need a model API key or execute repository-owned tests.

Never claim that RAEE-Lite proves correctness, calculates complete semantic test coverage, guarantees deployment security, or possesses a verified GitHub cloud attestation. **There is an early-access source checkout, not a stable package/PyPI release.**

## Ready-to-submit channel copy (post each at most once, tailored to channel)

### Hacker News — Show HN

**Title:** Show HN: RAEE-Lite – an offline evidence-gap checker for AI-generated code

**URL:** https://github.com/jinxinche/RAEE

**Optional author comment:**

I kept seeing a coding agent describe a change as done because a test returned zero, even when the test didn't exercise the requested behavior. I built a small Python CLI to keep five roles separate: requirements, code changes, checks actually run, execution context, and untested boundaries.

There's a runnable v0.10.0rc2 source candidate linked directly from the README. You can reproduce an `UNTESTED` requirement in a throwaway directory without any API key or running repository-owned scripts. The project is early access: cloud provenance and independent security review are pending. I'm especially interested in examples where this taxonomy gives a false sense of assurance or misses valid evidence. What would you want from a code-review tool like this?

**Eligibility:** HN's Show HN guidelines require something users can actually run, not only a writeup. The RC checkout is available; verify the demo just before submitting. Submit once through https://news.ycombinator.com/submit from the author's account; don't solicit votes.

### DEV Community — developer article

**Title:** My AI coding agent said “done.” The tests never covered the requirement.

**Tags (editorial suggestions, subject to channel policy):** `ai`, `python`, `testing`, `opensource`

**Opening:**

A passing check is not a proof of the feature you requested. Here's a common failure mode: a smoke test asserts `1 + 1 == 2`, a coding agent reports green tests, and a sign-up validation requirement has never been exercised. A useful evidence report should say `UNTESTED`, not `VERIFIED`.

I built RAEE-Lite as a local-first Python CLI to separate the requested behavior, repository changes, observed commands, the execution context, and unresolved evidence. The CLI intentionally doesn't infer comprehensive test coverage. Its job is narrower: make absent and stale checks visible.

**Full source article:** [Green tests are not the same as verified requirements](green-tests-not-verified-requirements.md). Adapt and expand it with genuine test output before publishing; don't make the published DEV piece a mechanical duplicate of the README. Include the public RC status and feedback link.

Editor: https://dev.to/new (requires author's logged-in account).

### Reddit — only a community that explicitly permits the post

**Title:** I built a local Python CLI that reports UNTESTED when an AI agent's green tests don't cover the requirement

**Body:**

I work on AI-assisted coding, and I keep running into the gap between “a test passed” and “the user's request was actually validated.” My open-source v0.10.0rc2 prototype, RAEE-Lite, treats requirements, code changes, observed checks, and unknowns as separate evidence roles. There's a runnable 30-second demo on GitHub. The project is early access; I haven't independently verified cross-platform signed CI, and I'm looking for actual false-positive/false-negative examples rather than votes. Would this sort of evidence-gap report be useful in code review? Source and demo: https://github.com/jinxinche/RAEE

**Rules:** Read each subreddit's current rules and use its dedicated promotion/share thread if required. Don't mass-post across subreddits, automate comments, ask for karma, or conceal ownership. If self-promotion is forbidden, don't submit.

### LinkedIn — engineering discussion

**Opening:** A green test is a useful signal. It is not a verified user requirement.

**Post:**

I'm sharing an early open-source project called RAEE-Lite. AI coding agents can generate convincing completion summaries without showing whether the right behavior was actually tested.

RAEE-Lite keeps five evidence roles separate: intent, code changes, observed checks, execution environment and unverified boundaries. In the demo, a sign-up requirement stays UNTESTED even when an unrelated check is green.

This is a local-first Python CLI and a public **release candidate**, not a correctness prover or a security certification. I'd welcome a small, anonymized example of where an agent's “done” claim exceeded the evidence.

Source + quick demo: https://github.com/jinxinche/RAEE

#SoftwareTesting #AICoding #OpenSource

### X / Twitter — single post, brief

Green tests ≠ verified requirements. I built RAEE-Lite, a local Python CLI that separates AI coding-agent claims from actual checks and flags UNTESTED evidence gaps. Public v0.10 RC source + demo (not security-certified): https://github.com/jinxinche/RAEE

### Bluesky — single post, brief

An AI coding agent can say “done” while its passing test never checks your requirement. RAEE-Lite is a local CLI that makes UNTESTED evidence visible. Public source RC, not a correctness proof. Demo: https://github.com/jinxinche/RAEE

### 中文 — 技术社区 / 朋友圈 / 博客

**标题：** AI 编程助手说“修好了”，但绿灯测试真的覆盖了需求吗？

我正在开放测试 RAEE-Lite：一个本地优先、开源的 Python CLI，将需求、代码变更、真实执行过的检查、运行环境和未验证边界分开记录。比如“注册接口必须拒绝非法邮箱”，即使无关的单元测试全绿，需求仍会标注 `UNTESTED`。源码候选版已经公开，README 提供可运行的 30 秒演示。它并不能证明程序正确或已通过独立安全审计；我希望征集真实的误报、漏报和易用性反馈：https://github.com/jinxinche/RAEE

### Deutsch — technische Community

**Titel:** Grüne Tests bedeuten nicht, dass die Anforderung geprüft wurde

RAEE-Lite ist ein lokales Open-Source-Python-CLI zur Trennung von Nutzeranforderungen, Quellcodeänderungen, tatsächlich ausgeführten Prüfungen und offenen Evidenzlücken. Eine Anforderung bleibt `UNTESTED`, selbst wenn ein unpassender Test grün ist. Der Quellcode ist als öffentliche Release-Candidate-Version mit kurzer Demo verfügbar – keine Sicherheitszertifizierung oder Korrektheitsgarantie. Rückmeldungen zu reproduzierbaren Fehlfällen sind willkommen: https://github.com/jinxinche/RAEE

### Español — comunidad de programación

**Título:** Pruebas en verde no son lo mismo que requisitos verificados

RAEE-Lite es una CLI local y de código abierto para separar los requisitos de usuario, los cambios de código, las pruebas que realmente se ejecutaron y lo que todavía falta verificar. Un requisito sigue en estado `UNTESTED` aunque pase una prueba irrelevante. El código está disponible como versión candidata pública con una demostración breve; no es una certificación de seguridad. Se agradecen reproducciones mínimas de falsos positivos y negativos: https://github.com/jinxinche/RAEE

## Product Hunt — **prepare a draft, postpone featured launch**

**Name:** RAEE-Lite

**Tagline:** See what your AI coding agent actually verified

**Description:** An offline Python CLI that keeps requested behavior, source changes and observed checks separate, highlighting stale or missing evidence instead of treating green tests as proof of a feature.

**Maker comment:** I built this because “the agent says it passed” isn't the same as “the requested feature was covered.” A reproducible local demo shows a requirement remaining UNTESTED. This is an early source-release candidate with deliberately limited claims. I want feedback about missing evidence and usability, not coordinated upvotes.

**Hold launch until:** tested release/archive, reliable independent installation, cross-platform CI proof, demo capture and authentic product visuals. Product Hunt emphasizes working, immediately usable products and prohibits asking for upvotes. No launch is currently claimed.

## Practical publication sequence / attribution

**Phase A — public beta feedback:** Main-branch README and a genuine GitHub issue first. Then **one** relevant technical channel (e.g. DEV or Show HN) with an immediately runnable source demo. Be available to answer genuine questions.

**Phase B — social distribution:** LinkedIn, Bluesky and X only from the owner's actually connected accounts; vary framing rather than publishing identical blocks simultaneously. If using Metricool, connect the intended social networks to the brand first. Publishing to a social tool is not achieved by merely writing the copy.

**Phase C — full release launch:** After protected-main CI, authentic artifact signing and independent verification, run a separate Product Hunt launch; do not call a source-review preview a stable trusted release.

Track **actual** repository views and unique visitors (GitHub Insights), issue reports, attempted installations, meaningful replies and repeat contributors. No fabricated traffic, stars or engagement. A number is an observed metric only when retrieved from the provider.

## Owner action links

- Connect Metricool accounts: https://app.metricool.com/brands/connections?blogId=7736413
- Hacker News submit: https://news.ycombinator.com/submit
- DEV article editor: https://dev.to/new
- Reddit: choose a specific subreddit and inspect its live rules before posting
- Product Hunt launch guide: https://help.producthunt.com/en/articles/17350772-launch-guide
