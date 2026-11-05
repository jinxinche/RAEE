#!/usr/bin/env python3
"""Trusted-main regression runner that refuses accidentally empty/shrunken test discovery.

This is a smoke gate, not proof that tests are adequate or tamper-resistant.
Only run reviewed code on protected branches or disposable credential-free CI.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
import platform
from pathlib import Path
import sys
import tempfile
import unittest


REQUIRED_TEST_MODULES = {
    'test_association_concurrency': 10,
    'test_audit_consistency': 6,
    'test_binding_edges': 10,
    'test_cli_edges': 7,
    'test_contract_edges': 10,
    'test_dashboard_integrity': 22,
    'test_dependency_graph_edges': 10,
    'test_dependency_performance': 8,
    'test_diff_edges': 7,
    'test_discovery_integrity': 13,
    'test_envelope_edges': 22,
    'test_import_concurrency': 8,
    'test_inventory_warnings': 4,
    'test_io_edges': 8,
    'test_manifest_concurrency': 5,
    'test_metric_integrity': 10,
    'test_origin_edges': 30,
    'test_packaging_edges': 7,
    'test_pr_boundary_edges': 15,
    'test_process_edges': 22,
    'test_snapshot_edges': 6,
    'test_trace_integrity': 18,
    'test_agent_log_integrity': 22,
    'test_association_metrics_v09': 5,
    'test_attestation_v07': 22,
    'test_branch_protection_policy': 12,
    'test_ci_attestation_v08': 17,
    'test_ci_verification_integrity': 10,
    'test_cli': 6,
    'test_contracts': 9,
    'test_concurrent_evidence': 30,
    'test_counterevidence': 10,
    'test_dependency_completeness_audit': 27,
    'test_dependency_declarations': 6,
    'test_dependency_scope_ablation': 22,
    'test_enhanced': 12,
    'test_evidence_integrity': 21,
    'test_git_process_integrity': 17,
    'test_isolated_v06': 19,
    'test_obligation_trace': 8,
    'test_pr_bootstrap': 4,
    'test_pr_boundary_policy_v091': 8,
    'test_pr_diff_integrity': 20,
    'test_preflight_v010': 16,
    'test_readonly_io': 15,
    'test_report_integrity': 28,
    'test_real_cross_os_protocol': 11,
    'test_security_v05': 24,
    'test_signing_integrity': 10,
    'test_workflow_policy_v09': 8,
    'test_reviewed_suite': 14,
    'test_trust_chain_rc2': 6,
    'test_v04': 21,
    'test_validation_v09': 23,
}
MIN_TESTS = sum(REQUIRED_TEST_MODULES.values())

WINDOWS_CRITICAL_SKIPS = {
    'test_pr_boundary_edges.PRBoundaryEdgeTests.test_real_unreadable_directory_fails_closed',
    'test_inventory_warnings.InventoryWarningTests.test_real_unreadable_directory_cannot_be_reported_as_complete',
    'test_process_edges.ProcessEdgeTests.test_stderr_only_inherited_pipe_respects_deadline',
    'test_dependency_scope_ablation.DependencyScopeAblationTests.test_project_symlink_path_not_followed',
    'test_real_cross_os_protocol.RealMatrixContract.test_macos_style_temp_symlink_is_canonicalized_only_for_owned_fixture',
    'test_dependency_completeness_audit.CompletenessAuditTests.test_declared_path_through_link_never_reads_external_file',
    'test_security_v05.SecurityV05.test_symlink_to_ledger_cannot_be_overwritten',
    'test_attestation_v07.AttestationTests.test_private_key_world_readable_rejected',
    'test_readonly_io.ReadonlyIOTests.test_fifo_inputs_return_without_blocking',
    'test_git_process_integrity.CaptureIntegrityTests.test_parent_exit_with_inherited_stdout_cleans_process_group',
}


def _test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _test_ids(item)
        else:
            yield item.id()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-tests', type=int, default=MIN_TESTS)
    parser.add_argument('--start-dir', default='tests')
    parser.add_argument('--require-critical-modules', action='store_true')
    parser.add_argument('--summary', type=Path, help='Write bounded machine-readable test outcome counts')
    args = parser.parse_args(argv)
    if not 1 <= args.min_tests <= 10_000:
        parser.error('--min-tests must be between 1 and 10000')
    # Canonicalize the parent used for owned temporary test fixtures on macOS.
    # This does not relax the product's rejection of project-controlled links.
    tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve(strict=True))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    summary = {'schema': 'raee.reviewed_suite.v1', 'discovered': 0,
               'tests_run': 0, 'failures': 0, 'errors': 0,
               'skipped': 0, 'expected_failures': 0, 'unexpected_successes': 0, 'gate_passed': False,
               'environment': {'python': platform.python_version(), 'os': sys.platform,
                               'architecture': platform.machine()},
               'minimum_tests': args.min_tests,
               'critical_modules_required': args.require_critical_modules}

    def finish(code):
        summary['gate_passed'] = code == 0
        if args.summary:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        return code

    # Invalidate any previous success before collection can fail or abort.
    finish(2)
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(args.start_dir)
        count = suite.countTestCases()
        ids = list(_test_ids(suite))
    except Exception as exc:
        summary['errors'] = 1
        print(f'FAIL CLOSED: test discovery raised {type(exc).__name__}.', file=sys.stderr)
        return finish(2)
    summary.update(discovered=count, errors=len(loader.errors))
    print(f'RAEE reviewed suite discovery: {count} tests (minimum: {args.min_tests})', flush=True)
    if loader.errors:
        print('FAIL CLOSED: test collection contains import errors.', file=sys.stderr)
        return finish(2)
    if len(ids) != count or len(set(ids)) != count:
        print('FAIL CLOSED: duplicate or inconsistent discovered test IDs.', file=sys.stderr)
        return finish(2)
    if count < args.min_tests:
        print('FAIL CLOSED: discovered too few tests; review test collection.', file=sys.stderr)
        return finish(2)
    if args.require_critical_modules:
        modules = Counter(test_id.split('.', 1)[0] for test_id in ids)
        missing = sorted(name for name, minimum in REQUIRED_TEST_MODULES.items() if modules[name] < minimum)
        if missing:
            print('FAIL CLOSED: critical regression modules missing or reduced: ' + ', '.join(missing),
                  file=sys.stderr)
            return finish(2)
        unregistered = sorted(set(modules) - set(REQUIRED_TEST_MODULES))
        if unregistered:
            print('FAIL CLOSED: register minimum counts for new test modules: ' + ', '.join(unregistered),
                  file=sys.stderr)
            return finish(2)
    class TrackedResult(unittest.TextTestResult):
        def __init__(self, *values, **options):
            super().__init__(*values, **options)
            self.executed_ids = []

        def startTest(self, test):
            self.executed_ids.append(test.id())
            super().startTest(test)

    result = unittest.TextTestRunner(verbosity=2, resultclass=TrackedResult).run(suite)
    summary.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                   unexpected_successes=len(result.unexpectedSuccesses))
    if result.testsRun != count:
        print('FAIL CLOSED: fewer tests ran than were discovered.', file=sys.stderr)
        return finish(1)
    if Counter(result.executed_ids) != Counter(ids):
        print('FAIL CLOSED: executed test identities differ from discovery.', file=sys.stderr)
        return finish(1)
    if args.require_critical_modules:
        allowed = WINDOWS_CRITICAL_SKIPS if os.name == 'nt' else set()
        unverified = [test.id() for test, _ in result.skipped
                      if test.id() not in allowed]
        unverified.extend(test.id() for test, _ in result.expectedFailures)
        if unverified:
            print('FAIL CLOSED: critical tests did not pass: ' + ', '.join(unverified), file=sys.stderr)
            return finish(1)
    return finish(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    sys.exit(main())
