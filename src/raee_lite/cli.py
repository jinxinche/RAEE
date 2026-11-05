"""Zero-config and manual role-aware evidence checkpoints for AI-assisted coding."""
from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path

from .core import add_boundary, add_requirement, init, run_check
from .contracts import KINDS, set_expectation, plan_text
from .obligation_trace import trace as obligation_trace, format_text as format_obligation_trace
from .discovery import discover
from .enhanced import audit, ensure_initialized, github_step_summary, is_passing, save_report
from .enhanced import run_discovered
from .skills import install_skill
from .agent_logs import import_log
from .associations import link_evidence
from .pr_diff import save_diff, diff_markdown
from . import __version__
from .isolated import replay
from . import attestation
from . import ci_attestation
from . import validation
from . import preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raee-lite", description="Evidence Firewall for AI-generated code")
    parser.add_argument("--project", default=".", help="Project root (default: current directory)")
    parser.add_argument("--version", action="version", version=f"raee-lite {__version__}")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init", help="Initialize manual acceptance requirements")
    add = sub.add_parser("add", help="Declare a user-authored acceptance requirement")
    add.add_argument("description")
    expect = sub.add_parser("expect", help="Declare the kind of evidence needed for a requirement")
    expect.add_argument("--for", dest="requirement", required=True)
    expect.add_argument("--kind", choices=KINDS, required=True)
    boundary = sub.add_parser("boundary", help="Record an explicit limitation or unknown")
    boundary.add_argument("description")
    run = sub.add_parser("run", help="Execute an explicit check for a declared requirement")
    run.add_argument("--for", dest="requirement", required=True)
    run.add_argument("--kind", choices=KINDS, help="Self-declared scope; not automatically verified")
    run.add_argument("--timeout", type=int, default=120)
    run.add_argument("--allow-ci-execution", action="store_true", help="Acknowledge unsafe CI execution; requires disposable runner without secrets")
    run.add_argument("command", nargs=argparse.REMAINDER)
    iso = sub.add_parser("isolate", help="Replay a labelled check using a restricted, offline Docker container; never runs on host")
    iso.add_argument("--for", dest="requirement", required=True)
    iso.add_argument("--kind", choices=KINDS, required=True)
    iso.add_argument("--image", required=True, help="Pre-installed trusted local Docker image; pinned to resolved ID")
    iso.add_argument("--timeout", type=int, default=120)
    iso.add_argument("--memory-mb", type=int, default=512)
    iso.add_argument("--dry-run", action="store_true", help="Preview sanitized snapshot; never execute or persist receipt")
    iso.add_argument("--allow-ci-execution", action="store_true", help="Explicitly approve Docker access in CI on a dedicated, secret-free worker")
    iso.add_argument("command", nargs=argparse.REMAINDER)
    check = sub.add_parser("check", help="Discover checks safely; --run to actually execute them")
    check.add_argument("--run", action="store_true", help="OPT IN: executes repository-owned checks")
    check.add_argument("--allow-ci-execution", action="store_true", help="Acknowledge unsafe CI execution; requires disposable runner without secrets")
    check.add_argument("--timeout", type=int, default=120)
    check.add_argument("--strict", action="store_true", help="Require passing user-declared acceptance evidence")
    check.add_argument("--ci", action="store_true", help="Return a nonzero exit for incomplete evidence")
    check.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    sub.add_parser("doctor", help="List discovered checks without executing them or creating files")
    pf = sub.add_parser("preflight", help="Read-only release/security inventory; does not run project code")
    pf.add_argument("--json", action="store_true", help="Machine-readable findings")
    skill = sub.add_parser("install-skill", help="Install a non-overwriting Agent Skill for a coding agent")
    skill.add_argument("--agent", choices=["codex", "claude", "cursor", "all"], required=True)
    sub.add_parser("plan", help="Show explicit gaps and suggested additional check scopes (read only)")
    trace_parser = sub.add_parser("trace", help="Explain the declared evidence graph and exact unproven obligations (read only)")
    trace_parser.add_argument("--for", dest="requirement", help="Trace one declared requirement ID; default: all")
    trace_parser.add_argument("--json", action="store_true", help="Machine-readable evidence graph; never a coverage proof")
    trace_parser.add_argument("--target-os", help="Target OS identity, requires --target-python")
    trace_parser.add_argument("--target-python", help="Target Python version, requires --target-os")
    sub.add_parser("report", help="Generate JSON, Markdown, HTML and SARIF reports")
    sub.add_parser("status", help="Inspect current evidence and freshness")
    imp = sub.add_parser("import-agent", help="Explicitly import a local Codex/Claude JSONL transcript; logs do not pass contracts")
    imp.add_argument("--provider", choices=["auto", "codex", "claude"], default="auto")
    imp.add_argument("--file", required=True, help="An explicitly selected local .jsonl file (not searched automatically)")
    link = sub.add_parser("link", help="Associate a receipt and a requirement with a human-supplied rationale")
    link.add_argument("--for", dest="requirement", required=True)
    link.add_argument("--evidence", required=True)
    link.add_argument("--reason", required=True)
    compare = sub.add_parser("compare", help="Compare base/head JSON evidence reports; never runs tests")
    compare.add_argument("--base", required=True, help="Base report.json")
    compare.add_argument("--head", required=True, help="Head report.json")
    compare.add_argument("--out", default=".raee", help="Where to write pr-diff.{html,md,json}")
    compare.add_argument("--fail-on-regression", action="store_true")
    compare.add_argument("--expected-base-sha", help="Assert base report records expected Git commit")
    compare.add_argument("--expected-head-sha", help="Assert head report records expected Git commit")
    keygen = sub.add_parser("attest-keygen", help="Create an Ed25519 signing key outside the repository; never overwrites")
    keygen.add_argument("--private", required=True, help="New private key location (OUTSIDE project)")
    keygen.add_argument("--public", required=True, help="New public key location for independent pinning")
    attest = sub.add_parser("attest", help="DSSE-sign a fresh evidence report and source/Git bindings")
    attest.add_argument("--private-key", required=True)
    attest.add_argument("--out", default=".raee/attestation.dsse.json")
    attest.add_argument("--allow-no-git", action="store_true", help="Source-only signing without Git identity")
    attest.add_argument("--allow-dirty", action="store_true", help="Explicitly admit the Git tree is dirty")
    attest.add_argument("--allow-partial", action="store_true", help="Explicitly admit files were skipped")
    attest.add_argument("--require-isolated", action="store_true", help="Require matching local isolated-replay record")
    verify = sub.add_parser("verify-attestation", help="Verify with independently trusted pinned public key")
    verify.add_argument("--attestation", default=".raee/attestation.dsse.json")
    verify.add_argument("--public-key", required=True)
    verify.add_argument("--report", default=".raee/report.json")
    verify.add_argument("--ledger", default=".raee/ledger.json", help="Signed local ledger to cross-check by default")
    verify.add_argument("--manifest", default=".raee/manifest.json", help="Signed local manifest to cross-check by default")
    verify.add_argument("--offline", action="store_true", help="Validate report and signature without local ledger/manifest (reduced verification)")
    verify.add_argument("--expected-commit", help="Require exact 40 or 64 hexadecimal Git SHA")
    verify.add_argument("--check-current", action="store_true", help="Recompute current workspace fingerprint and Git head")
    verify.add_argument("--require-isolated", action="store_true")
    verify.add_argument("--require-clean", action="store_true", help="Reject unsigned/unavailable or dirty Git state")
    cie = sub.add_parser('ci-export', help='Export a bounded CI evidence receipt on a trusted push/dispatch event; NOT signed until GitHub attests it')
    cie.add_argument('--expected-repo', required=True, help='Pinned expected owner/repo')
    cie.add_argument('--trusted-ref', default='refs/heads/main', help='Pinned protected branch')
    cie.add_argument('--workflow', default='.github/workflows/trusted-evidence.yml', help='Pinned signing workflow path')
    cie.add_argument('--allow-incomplete', action='store_true', help='Export nonpassing evidence with explicit nonpassing status')
    civ = sub.add_parser('ci-verify', help='Independently verify GitHub/Sigstore artifact attestation (requires gh CLI)')
    civ.add_argument('--manifest', required=True, help='GitHub-attested ci-evidence.json (signed subject)')
    civ.add_argument('--expected-repo', required=True)
    civ.add_argument('--expected-ref', required=True)
    civ.add_argument('--expected-sha', required=True)
    civ.add_argument('--expected-workflow', required=True, help='Workflow path under .github/workflows/')
    civ.add_argument('--report', help='Optional report.json to additionally validate hash binding')
    civ.add_argument('--allow-incomplete', action='store_true', help='Permit attested failing/incomplete checks (never call them passing)')
    civ.add_argument('--timeout', type=int, default=60)
    cv = sub.add_parser('validate-corpus', help='Evaluate annotated, explicitly approved local agent JSONL fixtures')
    cv.add_argument('--index', required=True, help='JSON index with synthetic/consented case labels')
    cv.add_argument('--out', required=True, help='Aggregate JSON results; raw logs are not copied')
    args = parser.parse_args(argv)
    root = Path(args.project).resolve()
    def project_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else root / path
    try:
        if not root.is_dir():
            raise ValueError(f"Project folder does not exist: {root}")
        if args.action == 'validate-corpus':
            return validation.main(['--index', str(project_path(args.index)), '--out', str(project_path(args.out))])
        if args.action == 'ci-export':
            result = ci_attestation.export(root, expected_repo=args.expected_repo,
                    trusted_ref=args.trusted_ref, workflow=args.workflow,
                    require_passed=not args.allow_incomplete)
            print(json.dumps(result, indent=2))
            print('UNTRUSTED receipt until separately signed with GitHub actions/attest and externally verified.')
            return 0
        if args.action == 'ci-verify':
            result = ci_attestation.verify(project_path(args.manifest),
                expected_repo=args.expected_repo, expected_ref=args.expected_ref,
                expected_sha=args.expected_sha, expected_workflow=args.expected_workflow,
                report_path=project_path(args.report) if args.report else None,
                timeout=args.timeout, require_passed=not args.allow_incomplete)
            print(json.dumps(result, indent=2))
            return 0
        if args.action == "attest-keygen":
            result = attestation.keygen(Path(args.private), Path(args.public), root)
            print(json.dumps(result, indent=2))
            print('Keep the private key outside any repository and independently distribute/pin the public key.')
            return 0
        if args.action == "attest":
            result = attestation.create(root, Path(args.private_key).expanduser(), project_path(args.out),
                                        allow_no_git=args.allow_no_git, allow_dirty=args.allow_dirty,
                                        allow_partial=args.allow_partial, require_isolated=args.require_isolated)
            print(json.dumps(result, indent=2))
            print('SIGNED CLAIM ONLY: neither execution authenticity nor code correctness is guaranteed.')
            return 0
        if args.action == "verify-attestation":
            result = attestation.verify(root, project_path(args.attestation), Path(args.public_key).expanduser(),
                                        project_path(args.report), expected_commit=args.expected_commit,
                                        check_current=args.check_current, require_isolated=args.require_isolated,
                                        require_clean=args.require_clean,
                                        ledger_path=None if args.offline else project_path(args.ledger),
                                        manifest_path=None if args.offline else project_path(args.manifest))
            print(json.dumps(result, indent=2))
            return 0
        if args.action == "isolate":
            if not args.dry_run:
                _check_ci_execution(args)
            cmd = args.command[1:] if args.command and args.command[0] == "--" else args.command
            result = replay(root, args.requirement, args.kind, cmd, image=args.image,
                            timeout=args.timeout, memory_mb=args.memory_mb, dry_run=args.dry_run)
            if args.dry_run:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            save_report(root)
            print(f"Isolated evidence {result['id']}: {result['observed_status'].upper()} "
                  f"(exit {result['observed_exit_code']}); inspect .raee/report.html")
            return 0 if result['observed_exit_code'] == 0 else 1
        if args.action == "import-agent":
            ensure_initialized(root)
            result = import_log(root, Path(args.file).expanduser(), args.provider)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            save_report(root)
            return 0
        if args.action == "link":
            row = link_evidence(root, args.requirement, args.evidence, args.reason)
            save_report(root)
            print(f"Associated {row['evidence_id']} with {row['requirement']}; association is NOT proof of coverage")
            return 0
        if args.action == "compare":
            output = Path(args.out)
            if not output.is_absolute():
                output = root / output
            result = save_diff(Path(args.base).expanduser(), Path(args.head).expanduser(), output,
                               args.expected_base_sha, args.expected_head_sha)
            print(diff_markdown(result))
            target = __import__('os').environ.get('GITHUB_STEP_SUMMARY')
            if target:
                with open(target, 'a', encoding='utf-8') as out:
                    out.write(diff_markdown(result))
            print(f"Saved to: {output / 'pr-diff.html'}")
            return 1 if args.fail_on_regression and result['regressions'] else 0
        if args.action == "init":
            print("Initialized:", init(root))
            return 0
        if args.action == "install-skill":
            for line in install_skill(root, args.agent):
                print(line)
            return 0
        if args.action == "plan":
            report = audit(root)
            print(plan_text(report))
            return 0
        if args.action == "trace":
            if bool(args.target_os) != bool(args.target_python):
                raise ValueError("Supply both --target-os and --target-python")
            report = audit(root)
            if args.target_os:
                from .contracts import assess_contracts
                report["evidence_contracts"] = assess_contracts(root, report["source"],
                    target_environment={"os": args.target_os, "python": args.target_python})
            result = obligation_trace(report, requirement_id=args.requirement)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_obligation_trace(result))
            return 0
        if args.action == "preflight":
            result = preflight.evaluate(root)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("RAEE-Lite preflight:", result["result"])
                for item in result["findings"]:
                    print(f"  [{item['severity'].upper()}] {item['id']}: {item['message']}")
                    print("    Next:", item["next_action"])
                print(result["limitations"])
            return 2 if result["counts"]["blocker"] else 0
        if args.action == "doctor":
            found, notes = discover(root)
            print(f"Detected {len(found)} check(s) in {root.name} (not executed):")
            for x in found:
                print(f"  {x.kind}: {shlex.join(x.command)}")
            for n in notes:
                print(f"  Note: {n}")
            print("To execute discovered repository scripts, run `raee-lite check --run`.")
            return 0
        if args.action == "check":
            if args.timeout <= 0:
                raise ValueError("Timeout must be positive")
            ensure_initialized(root)
            found, _ = discover(root)
            if args.run:
                _check_ci_execution(args)
                for ch in found:
                    result = run_discovered(root, ch, args.timeout)
                    if not args.json:
                        print(f"{ch.kind:10} {result['observed_status'].upper():5} "
                              f"exit={result['observed_exit_code']} ({result['duration_seconds']}s)")
                if not found and not args.json:
                    print("No supported checks discovered. Use `raee-lite add` and `raee-lite run`.")
            report = save_report(root)
            github_step_summary(report)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print("Outcome:", report["overall"])
                if not args.run:
                    print("Safe preview: no project commands executed. Add `--run` to opt in.")
                print("Open .raee/report.html (also Markdown, JSON and SARIF).")
            return 0 if (not args.ci or is_passing(report, args.strict)) else 1
        if args.action == "add":
            print("Added requirement:", add_requirement(root, args.description))
        elif args.action == "expect":
            req = set_expectation(root, args.requirement, args.kind)
            print(f"Declared: {req['id']} expects {', '.join(req['expected_checks'])} (user-labelled; not proof)")
        elif args.action == "boundary":
            add_boundary(root, args.description)
            print("Recorded boundary")
        elif args.action == "run":
            _check_ci_execution(args)
            cmd = args.command[1:] if args.command and args.command[0] == "--" else args.command
            result = run_check(root, args.requirement, cmd, args.timeout, kind=args.kind)
            print(f"Evidence {result['id']}: {result['observed_status'].upper()} "
                  f"(exit {result['observed_exit_code']}, {result['duration_seconds']}s)")
            print("Execution observed. Requirement coverage is not automatically validated.")
            return 0 if result["observed_exit_code"] == 0 else 1
        elif args.action == "report":
            result = save_report(root)
            print("Outcome:", result["overall"])
            print("Generated .raee/report.html, .raee/report.md, .raee/report.json and .raee/report.sarif")
            return 0 if is_passing(result) else 1
        elif args.action == "status":
            report = audit(root)
            print("Outcome:", report["overall"])
            for item in report["requirements"]:
                print(f"  {item['id']}: {item['state']} — {item['requirement']}")
            for item in report.get("evidence_contracts", []):
                if item["status"] == "GAPS":
                    print(f"  {item['id']}: EXPLICIT EVIDENCE GAP ({len(item['gaps'])} scope(s))")
            for item in report["automatic_checks"]:
                print(f"  {item['id']}: {item['state']}")
            return 0 if is_passing(report) else 1
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    return 0


def _check_ci_execution(args) -> None:
    """Prevent accidental execution of untrusted project code in hosted CI.

    This flag is an explicit hazard acknowledgement, NOT sandboxing.
    """
    if os.environ.get('CI', '').lower() in ('1', 'true', 'yes') and not args.allow_ci_execution:
        raise ValueError('Execution blocked in CI by default; use a secret-free isolated runner and explicitly pass --allow-ci-execution')
