# Launch kit for RAEE-Lite

**Positioning:** “Your AI coding assistant says done. RAEE-Lite separates observed checks from unverified claims — offline, free, provider-neutral.”

## Launch sequence

1. Publish a tagged source release with a reproducible demo and checks; add Topics `ai-coding`, `coding-agents`, `testing`, `cli`, `code-review`, `verification`, `devtools`.
2. Include a short screen recording demonstrating a green `npm test` while a user requirement remains UNTESTED; demonstrate code edit making evidence STALE.
3. Submit a technical **Show HN** with a working local demo. Ask for feedback on the UX, not upvotes or Stars.
4. Share engineering details and reproducible limits on DEV, relevant Reddit threads subject to subreddit rules, Python discussions, and LinkedIn/X.
5. Propose Awesome List additions only when the project meets each list's acceptance criteria; don't mass-submit.
6. Publish one high-signal bug fix or usability improvement every 1–2 weeks based on Issues.

## Launch copy (draft)

### Show HN

**Show HN: RAEE-Lite — an offline evidence firewall for AI-generated code**

My coding assistant said the change was done because tests passed. But the tests didn't cover the behavior I'd asked for. I built a small Python CLI to keep those facts separate. `raee-lite check` discovers available checks without running them; `raee-lite check --run` executes opt-in checks and ties the results to a source fingerprint. Declared acceptance requirements and discovered checks are reported independently. Editing code marks old check evidence stale.

It's offline and needs no model calls or API keys. It doesn't prove software correctness or automatically judge test coverage. I'd particularly value feedback on which check integrations are worth implementing next.

### Reddit/DEV angle

**Green tests ≠ verified feature: a tiny offline tool for AI-assisted coding.**

Include one real reproducible example and a clear limitations section. Do not cross-post identical promotional messages to many communities.

## Goals and metrics (hypotheses, not forecasts)

| Stage | Product metric | Community metric |
|---|---|---|
| Alpha | 20 public-repo exercises; document misdetections | 10 constructive developer interviews |
| v0.3 | CI workflow usable from tagged release | 20 independent real Issues/PRs |
| v0.5 | Agent-specific integration with consent | Repeat users and community contributions |
| v1.0 | Release hardening and documented threat model | If adoption warrants, pursue 1,000+ and eventually 10,000 Stars |

Stars are an attention metric, not proof of value. Never buy Stars or coordinate vote exchanges.
