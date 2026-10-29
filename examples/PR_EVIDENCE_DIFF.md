# PR evidence delta — safe, reproducible workflow

Generate two *independent* `.raee/report.json` snapshots from the actual base and head worktrees. Do not copy a test receipt from base to head and call it fresh. Since `.raee/ledger.json` is deliberately untracked, checks executed at head must be executed again at head.

```bash
# In separate base and head checkouts (run only code you trust):
raee-lite --project path/to/base check --run
raee-lite --project path/to/head check --run

# Compare generated snapshots, no execution occurs during comparison:
raee-lite compare \
  --base path/to/base/.raee/report.json \
  --head path/to/head/.raee/report.json \
  --out comparison --fail-on-regression
```

Results: `comparison/pr-diff.html`, `.md`, `.json`. The comparison matches human-authored requirement *descriptions* and check scopes, plus discovered check IDs; if a requirement is renamed, it may appear as a deletion/addition. An observed process exit is NOT coverage proof. A removal of previously passing evidence counts as a regression signal. This is a two-snapshot evidence difference, not semantic equivalence or changed-line test coverage.

You can commit `.raee/manifest.json` (the project's expectations) to the repository, while retaining private logs, `ledger.json`, and report artifacts outside git. Scrutinize the manifest for sensitive data before committing.

For the **opt-in** GitHub Actions example see `.github/workflows/pr-evidence-example.yml.example`. Rename to `.yml` only if you are willing to execute PR code in dedicated, ephemeral CI runners. Do not use privileged `pull_request_target`, expose secrets, or execute untrusted repository scripts on trusted runners.
