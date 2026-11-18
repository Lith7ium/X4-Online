"""Calling-thread pump propagation through bounded saved-registry inspection."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from authority import registry_evidence, saved_registry
from authority.checkpoints import Checkpoint
from test_authority_registry_save_evidence import EPOCH, xml


class RegistryInspectionPumpTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / 'synthetic-save.xml.gz'
        compressed = gzip.compress(xml().encode())
        self.path.write_bytes(compressed)
        self.checkpoint = Checkpoint(
            'checkpoint-' + 'a' * 32,
            self.path,
            hashlib.sha256(compressed).hexdigest(),
            len(compressed),
        )

    def _instrument_parser_passes(self, calls_by_pass, on_pump):
        current_pass = [0]

        def instrument(original):
            def parse(checkpoint, callback, *, characters=None, pump=None):
                current_pass[0] += 1
                pass_number = current_pass[0]

                def tracked_pump():
                    calls_by_pass[pass_number] = calls_by_pass.get(pass_number, 0) + 1
                    on_pump(pass_number)
                    pump()

                return original(checkpoint, callback, characters=characters, pump=tracked_pump)
            return parse

        return instrument

    def test_initialized_status_pumps_every_registry_pass(self):
        calls_by_pass = {}
        instrument = self._instrument_parser_passes(calls_by_pass, lambda _pass_number: None)
        with patch.object(saved_registry, '_parse', instrument(saved_registry._parse)), \
                patch.object(registry_evidence, '_parse', instrument(registry_evidence._parse)):
            result = saved_registry.saved_status(self.checkpoint, pump=lambda: None)

        self.assertEqual(result[:3], ('ready', EPOCH, 2))
        self.assertEqual(set(calls_by_pass), {1, 2, 3, 4, 5})
        self.assertTrue(all(count > 0 for count in calls_by_pass.values()))

    def test_callback_exceptions_abort_final_component_pass_unchanged(self):
        for expected_error in (OSError('cancel inspection'), KeyboardInterrupt('stop inspection')):
            with self.subTest(error=type(expected_error).__name__):
                calls_by_pass = {}

                def stop_final_pass(pass_number):
                    if pass_number == 5:
                        raise expected_error

                instrument = self._instrument_parser_passes(calls_by_pass, stop_final_pass)
                with patch.object(saved_registry, '_parse', instrument(saved_registry._parse)), \
                        patch.object(registry_evidence, '_parse', instrument(registry_evidence._parse)), \
                        self.assertRaises(type(expected_error)) as raised:
                    saved_registry.saved_status(self.checkpoint, pump=lambda: None)

                self.assertIs(raised.exception, expected_error)
                self.assertGreater(calls_by_pass.get(5, 0), 0)

    def test_registry_verify_propagates_callback_exception(self):
        class StopInspection(Exception):
            pass

        def stop():
            raise StopInspection('stop registry verification')

        with self.assertRaisesRegex(StopInspection, 'stop registry verification'):
            registry_evidence.verify(self.checkpoint, EPOCH, 2, pump=stop)


if __name__ == '__main__':
    unittest.main()
