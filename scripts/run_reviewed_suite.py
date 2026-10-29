#!/usr/bin/env python3
"""Trusted-main regression runner that refuses accidentally empty/shrunken test discovery.

This is a smoke gate, not proof that tests are adequate or tamper-resistant.
Only run reviewed code on protected branches or disposable credential-free CI.
"""
from __future__ import annotations
import argparse
import sys
import unittest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-tests', type=int, default=150)
    parser.add_argument('--start-dir', default='tests')
    args = parser.parse_args(argv)
    if not 1 <= args.min_tests <= 10_000:
        parser.error('--min-tests must be between 1 and 10000')
    suite = unittest.TestLoader().discover(args.start_dir)
    count = suite.countTestCases()
    print(f'RAEE reviewed suite discovery: {count} tests (minimum: {args.min_tests})', flush=True)
    if count < args.min_tests:
        print('FAIL CLOSED: discovered too few tests; review test collection.', file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
