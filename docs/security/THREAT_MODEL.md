# RAEE-Lite v0.5.0 · Threat model and red-team checklist

## Trust boundaries

| Boundary | Attacker controls | What can happen | Defense applied | Residual risk |
|---|---|---|---|---|
| Imported agent JSONL | Entire transcript, tool output, tool call metadata | Prompt injection, oversized records, falsified test claims, secret-bearing output | No LLM execution, metadata-only extraction, byte/count ceilings, no-follow source open; NEVER counts as independent verification | Version mismatch, fabricated observations, malformed nested types |
| Source repository | `package.json`, tests, filenames, Git tree | Unexpected command execution, memory/disk exhaustion, symlink exfil | Preview-only by default, execution requires explicit flag; bounded discovery/fingerprint; destination symlink refusal | Opted-in commands have full caller permissions unless externally isolated |
| Manual command | Executable/argv, process descendants | Data loss, network exfil, hanging processes | Explicit approval, timeout, output discarded, POSIX process-group kill | Not sandboxed; Windows process grandchildren; OS-level exploits |
| PR JSON reports | Claims and nested fields | False PASS claims, HTML injection, confusing Base and Head | Type/size validation, output encoding, optional expected Git SHA equality | SHA text is not a signature; attacker may forge entire report |
| GitHub Actions workflow | PR source files and metadata | Token/secret exposure, poisoned artifacts, code execution | `pull_request`, contents:read, pinned Actions, no `--run`, install from trusted base, checked SHA flags | Malicious base repository owner/workflow, compromised dependencies/runners |
| Generated report | Requirement text, source paths, changed filenames | XSS in HTML, markdown image exfiltration, privacy leak | HTML escaping/CSP, markdown escaping, no external page dependencies | Intentional sharing exposes some metadata; links from elsewhere remain untrusted |

## Targeted red-team cases implemented

1. Untrusted transcript with embedded instructions and synthetic shell command: never executed.
2. Credential strings inside Agent command argv/output: not retained in imported evidence.
3. Overlong JSONL physical lines and malformed JSON: bounded, counted, skipped.
4. Explicit log claiming a passing Playwright command: cannot satisfy an independent evidence contract.
5. Forged Base Git SHA passed to `compare`: rejected.
6. Malformed report element types: rejected before comparison.
7. Symlinked evidence ledger and destination paths: refused without overwriting target.
8. HTML/Markdown injection in user requirement: escaped in generated reports.
9. `CI=true` and an execution request without explicit acknowledgement: rejected.
10. Chatty terminal process: stdout/stderr discarded; timeout tested.
11. Source file count overflow: marks fingerprint as incomplete.
12. Local Base/Head Git revisions: verified with corresponding commit IDs; deliberate mismatch fails.

## Validation scope

72 automated checks passed locally on Linux/Python 3.13, including 24 security/performance additions. Tests are reproducible with `python -m unittest discover -s tests -v`. No claim is made that they constitute a full penetration test or real production readiness. Actual Windows/macOS GitHub Actions status and provider log format compatibility on diverse real users remain pending.
