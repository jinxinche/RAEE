# Solo-maintainer validation record (not an independent audit)

This file documents the repository owner's choice to continue development with a single GitHub account. It is **not** evidence of an independent code review, third-party attestation, production security certification, or successful external fork test.

## Bootstrap and base trust

- [x] PR #3 added `scripts/pr_boundary.py` to the trusted `main` baseline and was merged normally.
- [x] Bootstrap script matched the candidate release script by exact Git blob SHA (`b0733d5a04fe3d42c04a8497b760288568ca0337`).
- [x] Local smoke classified ordinary file change as pass, sensitive script change as REVIEW REQUIRED, and a directory symlink as REVIEW REQUIRED.
- [ ] Independently audited by a human other than the maintainer.

## Repository-side acceptance

- [ ] A new CI run of PR #2 against the updated `main` baseline completes.
- [ ] PR changes to `.github/workflows/`, `scripts/`, `pyproject.toml`, and the attestation module are reviewed and explicitly acknowledged by the owner; no independent review is claimed.
- [ ] PR protection policy is configured and confirmed active in repository settings.
- [ ] The `pr-static-safety` check is not misrepresented as a clean safety result if it prints REVIEW REQUIRED. Its failure must not be silently ignored or bypassed.
- [ ] On protected `main`, GitHub Actions Linux/Windows/macOS matrix jobs complete successfully.
- [ ] A real GitHub artifact attestation is signed on protected `main`, then independently verified for repo/workflow/ref/SHA/report digest.
- [ ] A real fork PR permission-boundary scenario is completed and documented.
- [ ] A third-party security review is performed (future work).

## Policy choice for single maintainer

A branch rule requiring one independent approval cannot be met with one actual maintainer. Use **require pull request** and suitable **required automatically passing safety/integrity checks** without pretending a review happened. If a check intentionally refuses sensitive changes, do not configure that check as a required success gate without a separate legitimate exception/review mechanism: otherwise the repository becomes deadlocked. Do not bypass an already enforced protection rule.

Reviewable security-sensitive changes should be recorded explicitly in the PR discussion and remain labeled as *maintainer-reviewed only* until an independent reviewer becomes available.
