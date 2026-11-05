# RAEE-Lite v0.9 — Real-world validation and release gates

## Honest status (2026-10-29)

- **Implemented and locally evaluated:** repeatable synthetic parser corpus, per-provider precision/recall and unknown-exit rates, rejected path traversal/symlink inputs, low-privilege PR review sample, trusted-branch regression matrix and GitHub Attestation verification policy.
- **NOT done:** real Codex/Claude user-session benchmarking; first authentic GitHub OIDC/Sigstore attestation; end-to-end GitHub PR validation; cloud matrix results on Windows/macOS; independent penetration test.
- **Blocker:** no repository named RAEE-Lite among accessible GitHub repositories; connected GitHub integration does not expose create-repository or branch protection/rulesets actions. Avoid using unrelated research repositories.

## I. Establish a dedicated, publicly accessible repository

1. Create public `OWNER/RAEE-Lite` (or preferred name), decide project governance and security contact, and upload vetted source. Avoid putting proprietary research, raw conversation logs, tokens or secrets in Git history. **This is a manual repository step until a suitable authenticated repository-management API is available.**
2. Repo **Settings → Rules → Rulesets** (or Branches → Branch protection): target `main`. Require pull requests and code review, disallow force pushes/deletions, require passing checks after a first successful run; restrict bypass; optionally require signed commits. Check plan-availability of all controls.
3. Review and rename `.github/workflows/trusted-evidence.yml.example` to `trusted-evidence.yml` only after branch protection and security review. Vet and pin any unpinned GitHub Actions to reviewed, full immutable commit hashes.
4. Run one trusted push on protected `main`; check both `collect` and `sign` completed. Collect the `raee-ci-evidence-claim` artifact from this same run. Record run URL and exact full 40-character commit SHA from GitHub UI.
5. On an *independent* trusted workstation, install an approved GitHub CLI. Authenticate read-only, download the exact `ci-evidence.json` bytes, then run:

```bash
raee-lite ci-verify \
  --manifest downloaded/ci-evidence.json \
  --expected-repo OWNER/RAEE-Lite \
  --expected-ref refs/heads/main \
  --expected-sha FULL_40_CHARACTER_GIT_SHA \
  --expected-workflow .github/workflows/trusted-evidence.yml
```

The expected repository, SHA and workflow must come from independently reviewed policy, NOT from the unsigned manifest. **Only the successful independent verification is real provenance evidence.** A signed report is still not a proof of test adequacy.

> Current GitHub entitlement note: Artifact Attestations for GitHub Free/Pro/Team require a **public** repository; private-repository support requires an eligible Enterprise Cloud plan. Verify the current plan docs before enabling.

## II. PR threat scenarios and explicit acceptance criteria

- Fork PR adds a malicious `setup.py` or test script: low-privilege static workflow never installs or runs **PR HEAD**. Trusted base tool may read the PR as untrusted data, with file bounds and HTML escaping.
- PR changes the verification workflow to grant write token/OIDC: PR review runs trusted base workflow; changes are not effective on protected `main` without review and required checks.
- PR introduces symlink/path traversal or huge logs: parser rejects symlink and nonlocal paths; output is bounded, raw logs are not uploaded.
- Forged `GITHUB_ACTIONS=true`, wrong ref/SHA, tampered report: export alone is never verification; `gh attestation verify` must reject insufficient provenance.
- Uploaded workflow artifact contains attacker-controlled content: signing must be restricted to artifacts made in the **same protected push workflow**, not PR artifacts or arbitrary `workflow_run` inputs.
- Source executable in CI can be malicious even on protected branch if reviewers miss it. Pin dependencies/actions, keep CI credential scope minimal, use disposable hosted runners and restrict egress as applicable.

Test these scenarios with fork PRs in a disposable public test repo (without secrets); retain run links, logs and failure screenshots. The included policy tests check templates, not cloud execution.

## III. Real Codex / Claude compatibility corpus

Only volunteers with explicit consent may share redacted diagnostics. **Do not ask people for full raw sessions**, which may include prompts, source files, private URLs, personal data and API keys. Prefer users run a local approved benchmark with **no external network upload**, and share only summary JSON. If manual labeling is required, keep private data on the volunteer's machine.

Each corpus index uses `raee-corpus-v1` and points to simple `.jsonl` filenames within the same local folder, with an opaque case ID, provider, evidence provenance, and expected `{kind, exit_code}` pairs. Real cases must set `provenance: consented-real` and `consent_confirmed: true` (self-declaration, not independently provable consent). The importer never copies raw prompts or command text to the summary.

Run locally:

```bash
raee-lite validate-corpus --index validation_corpus/index.json --out validation_corpus/summary.json
```

Evaluate separately for each provider and format family. Report **exact session match rate**, event precision, event recall, *false discovery rate* (FP / (TP + FP)), unknown exit rate, unsupported format count, number of annotation disagreements, and size/distribution. False positive rate requires labelled negative opportunities and cannot be inferred from event matches alone.

For requirement-to-test association, build a **separate double-labelled dataset** with explicit positive and negative candidate pairs; report precision, recall, true FPR = FP / (FP + TN), confidence intervals and inter-annotator agreement. **No field accuracy is available yet.**

## IV. Scale and reproducibility

Run `python benchmarks/validation_scaling.py --events 20000 --out perf-20k.json` and repeat with 50k/100k synthetic events within the parser's limits, from a clean environment. Record exact Python/runtime/OS, input size, peak Python allocation (not full RSS), elapsed time and failed/unknown parsing count. Follow with at least 3 consenting, redacted real sessions of different sizes before drawing any production conclusions. Measure source scan separately on >5k-file repositories, explicitly recording partial coverage.

## Release gates

| Gate | Required evidence | Status |
|---|---|---|
| Unit and security regression | 156 locally executed tests green in separate modules | **PASS locally** |
| Trusted CI proof | Signed GitHub artifact + **independent** gh verification | **NOT VERIFIED** |
| PR security | Disposable fork PRs; proof no privileged PR execution | **NOT VERIFIED IN GITHUB** |
| Cross-platform | GitHub Actions matrix links for Linux, Windows, macOS | **NOT VERIFIED IN GITHUB** |
| Agent compatibility | Real consenting/redacted corpus with format breakdown | **NO REAL CORPUS YET** |
| Association quality | Independent positive/negative pair annotations | **NO REAL DATA YET** |
| Performance | Reproducible synthetic benchmark + real repo/session samples | Synthetic measured; real workloads pending |
| Security assurance | Independent assessment of trusted CI, sandbox, supply chain | **PENDING** |

These gates must remain visible in the README. Do **not** call the project production-certified until the evidence exists.
