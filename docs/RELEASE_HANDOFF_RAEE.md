# RAEE-Lite release handoff for jinxinche/RAEE

The repository `jinxinche/RAEE` already exists. These reviewed source files target that repository. Their presence in this local source bundle **does not mean that a GitHub release, CI run, branch protection rule or attestation has occurred**.

## Deployment

1. Inspect the source, dependency declarations and security workflows.
2. From an authenticated local GitHub CLI session, run `bash scripts/publish_existing_repo.sh`. This pushes a review branch (not main) and opens/updates a PR.
3. Review the PR and ensure a distinct reviewer can approve it. Merge only after review. Preserve the four-language README and research preprint citation.
4. Enable branch protection: PR required, one independent approval, stale reviews dismissed, `pr-static-safety` required, no force-push/deletion. The protected branch must actually show the configured rule.
5. Check *real* Actions results on Linux, macOS and Windows on the protected main branch; do not infer them from YAML.
6. Manually trigger `Trusted Evidence Attestation` on protected main and download `ci-evidence.json`, `report.json`, and the GitHub-issued bundle.
7. On an independent authenticated environment with patched `gh >= 2.97.0`, run `bash scripts/verify_independent.sh ci-evidence.json report.json <FULL_COMMIT_SHA>`, recording actual verifier output and workflow identity.
8. After independent verification succeeds, publish the **pre-release** and wheel via `gh release create v0.10.0rc2 dist/*.whl --prerelease --repo jinxinche/RAEE`.

No third-party review or real user Agent-log compatibility metrics are claimed.
