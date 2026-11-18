"""CLI/config checks only; no Windows, X4 or network connection."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'fixture_cli', ROOT / 'tools/dev/authority_windows_fixture_client.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class FixtureCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.connection = self.root / 'connection.json'
        self.settings = dict(server_host='example.invalid', server_port=47050,
                             server_fingerprint='a' * 64, shared_key='b' * 64,
                             file_token='c' * 32, file_slot=1)
        self.connection.write_text(json.dumps(self.settings))

    def test_connection_decodes_only_expected_fields(self):
        settings = cli.read_connection_settings(self.connection)
        self.assertEqual(settings, self.settings | {'shared_key': bytes.fromhex('b' * 64)})
        for changes in ({'file_slot': True}, {'extra': 'secret'}, {'shared_key': 'short'}):
            with self.subTest(changes=changes):
                self.connection.write_text(json.dumps(self.settings | changes))
                with self.assertRaises(ValueError):
                    cli.read_connection_settings(self.connection)
        self.connection.write_text('{"shared_key":"one","shared_key":"two"}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            cli.read_connection_settings(self.connection)

    def test_connection_bound_and_reparse_rejection(self):
        self.connection.write_bytes(b' ' * 4097)
        with self.assertRaisesRegex(ValueError, 'bounded'):
            cli.read_connection_settings(self.connection)
        from types import SimpleNamespace
        import stat
        with patch.object(Path, 'lstat', return_value=SimpleNamespace(
                st_mode=stat.S_IFREG, st_size=100, st_file_attributes=0x400)):
            with self.assertRaises(ValueError):
                cli.read_connection_settings(self.connection)

    def test_observation_window_starts_at_first_admitted_poll(self):
        window = cli.ObservationWindow(30)
        with patch.object(cli.time, 'monotonic', side_effect=(100, 129, 130)):
            self.assertFalse(window())
            self.assertFalse(window())
            self.assertTrue(window())

    def test_motion_config_is_explicit_bounded_and_fixture_checked(self):
        path = self.root / 'motion.json'
        request = {'generation': '1' * 32, 'indices': [1318], 'timeout': 5,
                   'saved_playback_fixture': 'recovery_enh_870'}
        path.write_text(json.dumps(request))
        self.assertEqual(cli.read_motion_request(path), request)
        for invalid in (None, {**request, 'indices': [1]}, {**request, 'timeout': 30},
                        {**request, 'generation': 'bad'}, {**request, 'extra': True}):
            with self.subTest(invalid=invalid):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    cli.read_motion_request(path)

    def test_motion_request_counts_both_ipc_deadlines_in_overall_limit(self):
        from authority.windows_fixture_session import validate_motion_request
        request = {'generation': '1' * 32, 'indices': [1318], 'timeout': 30}
        validate_motion_request(request, participant_timeout=239)
        with self.assertRaisesRegex(ValueError, 'bounded'):
            validate_motion_request(request, participant_timeout=240)

    def test_failure_does_not_print_exception_text_or_credentials(self):
        arguments = ['--connection-file', str(self.connection), '--game', str(self.root / 'game'),
                     '--view-container', str(self.root / 'view'), '--out', str(self.root / 'out'),
                     '--network-dll', str(self.root / 'net.dll'), '--network-dll-sha256', 'a' * 64]
        output = io.StringIO()
        with patch.object(cli, 'run', side_effect=RuntimeError('PRIVATE_CREDENTIAL')):
            with contextlib.redirect_stderr(output):
                self.assertEqual(cli.main(arguments), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['error_type'], 'RuntimeError')
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('PRIVATE_CREDENTIAL', output.getvalue())

    def test_missing_opt_in_refuses_before_reading_credentials(self):
        args = type('Arguments', (), {'isolated_fixture_test': False})()
        with patch.object(cli, 'read_connection_settings') as reader:
            with self.assertRaises(ValueError):
                cli.run(args)
        reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
