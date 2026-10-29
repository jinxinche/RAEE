# RAEE-Lite v0.10.0rc2 — release handoff (draft)

This branch is an **incomplete staging branch**, not a public source release. Do not merge until the complete Python package, tests and reviewed workflows are pushed and the independent review is complete.

## Local validation completed
- Existing candidate corrected to the actual GitHub repository identity: `jinxinche/RAEE`.
- 14 separate Python test modules passed; combined discovery identified 184 tests.
- Python Wheel built and installed in a new virtual environment.
- Publication script syntax and the three workflow YAML files were parsed successfully.

## Still required
1. Upload the full, reviewed source candidate from the project archive using `bash scripts/publish_existing_repo.sh` on an authenticated developer machine. The script pushes to this branch and preserves the four-language README, `CITATION.cff`, `REFERENCES.bib` and `LICENSE`.
2. Confirm the complete diff and obtain independent review, then merge.
3. Enable effective `main` branch protection with a real independent reviewer and required `pr-static-safety` check.
4. Observe the Linux/Windows/macOS GitHub Actions jobs running successfully on protected `main`.
5. Generate a **real** GitHub Artifact Attestation from `.github/workflows/trusted-evidence.yml`.
6. Independently verify the attested bytes, repository, workflow, full commit SHA, and signing identity with a patched GitHub CLI.
7. Publish a prerelease Wheel only after successful cloud verification and review.

**No real cloud attestation, full cross-platform result, production-security certification or external user-log compatibility result is claimed yet.**

The scientific RAEE preprint is separate from the RAEE-Lite software and does not empirically validate this developer tool. See the main README and `REFERENCES.bib`.
