#!/usr/bin/env python3
"""Trusted-main regression runner that refuses accidentally empty/shrunken test discovery.

This is a smoke gate, not proof that tests are adequate or tamper-resistant.
Only run reviewed code on protected branches or disposable credential-free CI.
"""
from __future__ import annotations
import argparse
import sys
import unittest


REQUIRED_TEST_MODULES = {
    'test_counterevidence',
    'test_dependency_completeness_audit',
    'test_dependency_declarations',
    'test_dependency_scope_ablation',
    'test_real_cross_os_protocol',
    'test_security_v05',
    'test_workflow_policy_v09',
}


def _test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _test_ids(item)
        else:
            yield item.id()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-tests', type=int, default=240)
    parser.add_argument('--start-dir', default='tests')
    parser.add_argument('--require-critical-modules', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.min_tests <= 10_000:
        parser.error('--min-tests must be between 1 and 10000')
    suite = unittest.TestLoader().discover(args.start_dir)
    count = suite.countTestCases()
    print(f'RAEE reviewed suite discovery: {count} tests (minimum: {args.min_tests})', flush=True)
    if count < args.min_tests:
        print('FAIL CLOSED: discovered too few tests; review test collection.', file=sys.stderr)
        return 2
    if args.require_critical_modules:
        modules = {test_id.split('.', 1)[0] for test_id in _test_ids(suite)}
        missing = sorted(REQUIRED_TEST_MODULES - modules)
        if missing:
            print('FAIL CLOSED: critical regression modules missing: ' + ', '.join(missing),
                  file=sys.stderr)
            return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
