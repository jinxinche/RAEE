# RAEE-Lite — Early-access community outreach kit

**Campaign state (9 November 2026):** Public open-source preview, **v0.10.0rc2 source merged into `main`**, including [PR #14](https://github.com/jinxinche/RAEE/pull/14) and the runnable showcase in [PR #15](https://github.com/jinxinche/RAEE/pull/15). This is an editorial kit, **not evidence that any off-GitHub post has been published**.

Canonical destination: https://github.com/jinxinche/RAEE

Working source: https://github.com/jinxinche/RAEE/tree/main

Runnable demo and expected output: https://github.com/jinxinche/RAEE/blob/main/examples/DEMO.md

## Repository discovery details

- **About:** Track what AI coding agents actually tested. A local Python CLI for requirement-linked evidence, stale-check detection, and reviewable reports. MIT licensed; no AI API key required for core checks.
- **Website field:** the runnable demo page above. It is a documentation link, not a separately deployed product site.
- **Topics:** `python`, `cli`, `developer-tools`, `ai-assisted-coding`, `coding-agents`, `evidence-tracking`, `software-testing`, `github-actions`, `provenance`, `reproducibility`.
- **First audience:** developers using coding agents and reviewers checking the evidence behind a change.
- **First action:** run the synthetic demo, then report an expected-versus-observed state with Python/OS details in the feedback issue.

GitHub's About and Topics fields are repository settings; editing this file alone does not update them.

## Reference links

Technical explainer: https://github.com/jinxinche/RAEE/blob/main/docs/green-tests-not-verified-requirements.md

Community feedback: https://github.com/jinxinche/RAEE/issues/7

Scientific inspiration: https://doi.org/10.21203/rs.3.rs-10194336/v1 (the preprint **does not validate this tool**).

## What actually makes the project interesting

AI coding assistants often treat “command exited 0” and “user's feature is verified” as the same event. RAEE-Lite treats them as **different evidence**. A declared requirement can be `UNTESTED` even while an unrelated unit test is green. Changed source can invalidate past check evidence, producing `STALE`. The default inspection workflow runs locally and does not need a model API key or execute repository-owned tests.

Never claim that RAEE-Lite proves correctness, calculates complete semantic test coverage, guarantees deployment security, or possesses a verified GitHub cloud attestation. **There is an early-access source checkout, not a stable package/PyPI release.**

## Channel drafts (unpublished; owner review before submission)

The complete [V2EX, DEV and Show HN drafts](launch/README.md) accompany a [40-second output replay, cover and subtitles](assets/launch/README.md). These are prepared materials, not completed off-GitHub publications.

### Hacker News — Show HN

Use the [complete submission draft](launch/show-hn.en.md), with a runnable repository URL and an optional author comment describing the four evidence states. The owner should be available to discuss it. Check the [current Show HN guidelines](https://news.ycombinator.com/showhn.html) before submitting.

### English technical article — DEV submission on hold

The [complete article draft](launch/dev.en.md) includes actual output, reproduction commands, the limitation of user-supplied requirement labels and an AI-assistance disclosure. Its front matter has `published: false` deliberately. [DEV's AI guidelines](https://dev.to/guidelines-for-ai-assisted-articles-on-dev) restrict promotional programs and social-presence campaigns, so do not submit this launch draft there in its current context. Keep it for owner review and a suitable, explicitly chosen channel.

### V2EX — 分享创造

Use the [Chinese draft](launch/v2ex.zh-CN.md) for the [分享创造 node](https://www.v2ex.com/go/create). It asks for installation problems and reproducible state-reporting errors, rather than votes.

### Reddit — only a community that explicitly permits the post

**Title:** I built a local Python CLI that reports UNTESTED when an AI agent's green tests don't cover the requirement

**Body:**

I’m sharing my open-source v0.10.0rc2 prototype, RAEE-Lite, treats requirements, code changes, observed checks, and unknowns as separate evidence roles. GitHub includes a runnable synthetic demo and a 40-second replay of its local output. The project is early access; I haven't independently verified cross-platform signed CI, and I'm looking for actual false-positive/false-negative examples rather than votes. Would this sort of evidence-gap report be useful in code review? Source and demo: https://github.com/jinxinche/RAEE

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

我正在开放测试 RAEE-Lite：一个本地优先、开源的 Python CLI，将需求、代码变更、真实执行过的检查、运行环境和未验证边界分开记录。比如“注册接口必须拒绝非法邮箱”，即使无关的单元测试全绿，需求仍会标注 `UNTESTED`。源码候选版已经公开，README 提供可运行的合成示例和 40 秒本地输出回放。它并不能证明程序正确或已通过独立安全审计；我希望征集真实的误报、漏报和易用性反馈：https://github.com/jinxinche/RAEE

### Deutsch — technische Community

**Titel:** Grüne Tests bedeuten nicht, dass die Anforderung geprüft wurde

RAEE-Lite ist ein lokales Open-Source-Python-CLI zur Trennung von Nutzeranforderungen, Quellcodeänderungen, tatsächlich ausgeführten Prüfungen und offenen Evidenzlücken. Eine Anforderung bleibt `UNTESTED`, selbst wenn ein unpassender Test grün ist. Der Quellcode ist als öffentliche Release-Candidate-Version mit kurzer Demo verfügbar – keine Sicherheitszertifizierung oder Korrektheitsgarantie. Rückmeldungen zu reproduzierbaren Fehlfällen sind willkommen: https://github.com/jinxinche/RAEE

### Español — comunidad de programación

**Título:** Pruebas en verde no son lo mismo que requisitos verificados

RAEE-Lite es una CLI local y de código abierto para separar los requisitos de usuario, los cambios de código, las pruebas que realmente se ejecutaron y lo que todavía falta verificar. Un requisito sigue en estado `UNTESTED` aunque pase una prueba irrelevante. El código está disponible como versión candidata pública con una demostración breve; no es una certificación de seguridad. Se agradecen reproducciones mínimas de falsos positivos y negativos: https://github.com/jinxinche/RAEE

## Product Hunt — **prepare a draft, postpone featured launch**

**Name:** RAEE-Lite

**Tagline:** Track what your AI coding agent actually tested

**Description:** An offline Python CLI that keeps requested behavior, source changes and observed checks separate, highlighting stale or missing evidence instead of treating green tests as proof of a feature.

**Maker comment:** “The agent says it passed” is not the same as “the requested feature was covered.” A reproducible local demo shows a requirement remaining UNTESTED. This is an early source-release candidate with deliberately limited claims. I want feedback about missing evidence and usability, not coordinated upvotes.

**Separate release-readiness checks:** versioned release/archive, independent installation, exact-release cross-platform CI, protected-main acceptance and independent provenance verification. Demo media are available; their presence does not complete the remaining checks. Product Hunt emphasizes working, immediately usable products and prohibits asking for upvotes. No launch is currently claimed.

## Practical publication sequence / attribution

**Phase A — public beta feedback:** Main-branch README and a genuine GitHub issue first. Then **one** relevant technical channel (e.g. V2EX 分享创造 or Show HN) with an immediately runnable source demo. Be available to answer genuine questions.

**Phase B — social distribution:** LinkedIn, Bluesky and X only from the owner's actually connected accounts; vary framing rather than publishing identical blocks simultaneously. If using Metricool, connect the intended social networks to the brand first. Publishing to a social tool is not achieved by merely writing the copy.

**Phase C — full release launch:** After protected-main CI, authentic artifact signing and independent verification, run a separate Product Hunt launch; do not call a source-review preview a stable trusted release.

Track **actual** repository views and unique visitors (GitHub Insights), issue reports, attempted installations, meaningful replies and repeat contributors. No fabricated traffic, stars or engagement. A number is an observed metric only when retrieved from the provider.

Use the private [Traffic dashboard](https://github.com/jinxinche/RAEE/graphs/traffic) to record the date range, views, unique visitors and referrers before and after a specific post. Keep account-only analytics out of public issue reports. Few visitors suggest limited exposure; visits without feedback are a prompt to investigate the onboarding, not proof that the project lacks value. Clone counts and unique cloners may include CI, automation and repeat infrastructure, so they are not adoption counts. Do not divide all-time stars by a rolling 14-day visitor count and call it a conversion rate.

## Owner action links

- Hacker News submit: https://news.ycombinator.com/submit
- DEV article editor: https://dev.to/new
- Reddit: choose a specific subreddit and inspect its live rules before posting
- Product Hunt launch guide: https://help.producthunt.com/en/articles/17350772-launch-guide
