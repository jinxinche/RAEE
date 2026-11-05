"""JSON writer budgets and rejected updates under the permanent writer lock."""
import json
from pathlib import Path
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from raee_lite import core, safe_io


class IOEdgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='raee-io-edges-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'shared.json'
        self.previous = b'{"previous": true}\n'
        self.path.write_bytes(self.previous)

    def test_tiny_read_does_not_allocate_the_full_json_cap(self):
        tracemalloc.start()
        try:
            value = safe_io.read_bytes(self.path, 16_000_000)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(value, self.previous)
        self.assertLess(peak, 1_000_000)

    def test_coerced_duplicate_keys_preserve_previous_document(self):
        for key, spelling in ((1, '1'), (True, 'true'), (None, 'null'), (1.5, '1.5')):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
                    safe_io.write_json(self.path, {'nested': [{key: 'first', spelling: 'second'}]})
                self.assertEqual(self.path.read_bytes(), self.previous)

    def test_rejected_receipt_keeps_ledger_readable_for_next_writer(self):
        first = core.append_receipt(self.root, {'status': 'first'})
        ledger = self.root / core.LEDGER
        previous = ledger.read_bytes()
        lock_identity = (self.root / core.LEDGER_LOCK).stat()
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
            core.append_receipt(self.root, {'metadata': {1: 'first', '1': 'second'}})
        self.assertEqual(ledger.read_bytes(), previous)
        second = core.append_receipt(self.root, {'status': 'second'}, lock_timeout=0)
        self.assertEqual((first['id'], second['id']), ('E1', 'E2'))
        self.assertEqual(core.read_json(ledger)['runs'], [first, second])
        current = (self.root / core.LEDGER_LOCK).stat()
        self.assertEqual((current.st_dev, current.st_ino),
                         (lock_identity.st_dev, lock_identity.st_ino))

    def test_byte_budget_stops_encoding_before_exhausting_collection(self):
        class CountedList(list):
            seen = 0

            def __iter__(self):
                for item in super().__iter__():
                    self.seen += 1
                    yield item

        payload = CountedList(['x' * 64] * 10000)
        with patch.object(safe_io, 'MAX_STORED_JSON', 128):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                safe_io.write_json(self.path, payload)
        self.assertLess(payload.seen, len(payload))
        self.assertEqual(self.path.read_bytes(), self.previous)
        self.assertEqual(list(self.root.glob('.raee-tmp-*')), [])

    def test_multibyte_budget_includes_final_newline(self):
        document = {'text': '\u6c49\U0001f600\n'}
        expected = (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        with patch.object(safe_io, 'MAX_STORED_JSON', len(expected) - 1):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                safe_io.write_json(self.path, document)
        self.assertEqual(self.path.read_bytes(), self.previous)
        with patch.object(safe_io, 'MAX_STORED_JSON', len(expected)):
            safe_io.write_json(self.path, document)
            self.assertEqual(self.path.read_bytes(), expected)
            self.assertEqual(safe_io.safe_read_json(self.path), document)

    def test_distinct_coerced_keys_keep_json_encoder_compatibility(self):
        document = {1: 'integer', False: 'boolean', None: 'null', 1.5: 'float'}
        expected = json.dumps(document, indent=2, ensure_ascii=False) + '\n'
        safe_io.write_json(self.path, document)
        self.assertEqual(self.path.read_text(), expected)
        self.assertEqual(safe_io.safe_read_json(self.path), json.loads(expected))

    def test_excessive_nesting_is_a_value_error_and_preserves_document(self):
        document = []
        for _ in range(3000):
            document = [document]
        with self.assertRaisesRegex(ValueError, 'nesting'):
            safe_io.write_json(self.path, document)
        self.assertEqual(self.path.read_bytes(), self.previous)

    def test_oversized_integer_timeout_is_rejected_before_creating_lock(self):
        lock = self.root / 'new-parent' / 'shared.lock'
        for timeout in (10 ** 1000, -(10 ** 1000)):
            with self.subTest(negative=timeout < 0):
                with self.assertRaisesRegex(ValueError, 'Lock timeout'):
                    with safe_io.exclusive_lock(lock, timeout=timeout):
                        self.fail('Accepted an out-of-range timeout')
        self.assertFalse(lock.parent.exists())
