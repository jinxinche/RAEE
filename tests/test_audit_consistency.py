"""A report must not accept a mixture of observed evidence-store versions."""
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from raee_lite import core, enhanced


class AuditConsistencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='raee-audit-consistency-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        core.init(self.root)
        self.rid = core.add_requirement(self.root, 'Feature works')
        core.run_check(self.root, self.rid, [sys.executable, '-B', '-c', 'pass'], 10)

    def test_unchanged_inputs_keep_passing_report(self):
        self.assertTrue(enhanced.is_passing(enhanced.audit(self.root), strict=True))

    def test_failure_appended_during_core_audit_cannot_be_ignored(self):
        original = core.fingerprint

        def fingerprint_and_fail(root):
            source = original(root)
            receipt = dict(core.read_json(root / core.LEDGER)['runs'][0])
            receipt.update(observed_exit_code=1, observed_status='fail')
            core.append_receipt(root, receipt)
            return source

        with patch.object(core, 'fingerprint', side_effect=fingerprint_and_fail):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                core.audit(self.root)
        self.assertEqual(core.audit(self.root)['overall'], 'FAILED_CHECK')

    def test_requirement_added_after_core_audit_requires_retry(self):
        original = enhanced.assess_contracts

        def assess_then_add(root, source):
            result = original(root, source)
            core.add_requirement(root, 'New untested requirement')
            return result

        with patch.object(enhanced, 'assess_contracts', side_effect=assess_then_add):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                enhanced.audit(self.root)
        self.assertFalse(enhanced.is_passing(enhanced.audit(self.root), strict=True))

    def test_auxiliary_input_creation_requires_retry(self):
        for filename, field in [('imports.json', 'observations'), ('links.json', 'links')]:
            with self.subTest(filename=filename):
                path = self.root / '.raee' / filename
                path.unlink(missing_ok=True)
                original = enhanced.build_associations

                def associate_then_create(root, source):
                    result = original(root, source)
                    core.write_json(path, {'schema': 1, field: []})
                    return result

                with patch.object(enhanced, 'build_associations', side_effect=associate_then_create):
                    with self.assertRaisesRegex(ValueError, 'inputs changed'):
                        enhanced.audit(self.root)
                path.unlink()

    def test_auxiliary_input_removal_requires_retry(self):
        path = self.root / '.raee' / 'links.json'
        core.write_json(path, {'schema': 1, 'links': []})
        original = enhanced.build_associations

        def associate_then_remove(root, source):
            result = original(root, source)
            path.unlink()
            return result

        with patch.object(enhanced, 'build_associations', side_effect=associate_then_remove):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                enhanced.audit(self.root)

    def test_render_error_leaves_all_existing_report_files_unchanged(self):
        report = enhanced.audit(self.root)
        enhanced.save_report(self.root, report)
        paths = [self.root / '.raee' / ('report.' + ext) for ext in ('json', 'md', 'html', 'sarif')]
        original = [path.read_bytes() for path in paths]
        report['goal'] = 'A newer report'
        with patch.object(enhanced, 'html_report', side_effect=ValueError('Rendering refused')):
            with self.assertRaisesRegex(ValueError, 'Rendering refused'):
                enhanced.save_report(self.root, report)
        self.assertEqual([path.read_bytes() for path in paths], original)
