"""Offline ownership and evidence checks; no X4 process is started."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovered_server_client as subject


class ServerClientTests(unittest.TestCase):
    def test_public_evidence_contains_only_expected_correlation_fields(self):
        ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=2,
                      load_generation=3, checkpoint_id='checkpoint-'+'b'*32,
                      sha256='c'*64, attempt_id='d'*32, slot='save_009')
        result = {}
        subject.record_client_evidence(result, ticket, 'e'*32)
        self.assertEqual(result['client_ticket'], ticket)
        self.assertEqual(result['client_checkpoint_sha256'], ticket['sha256'])
        self.assertEqual(result['client_loaded_marker'], 'e'*32)
        self.assertTrue(result['client_owned_process_stopped'])
        self.assertFalse(any('lease' in field or 'token' in field for field in result))
        with self.assertRaises(ValueError):
            subject.record_client_evidence({}, dict(ticket, file_token='secret'), 'e'*32)

    def test_recovered_watch_not_pair_runner_server_log_path_is_used(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        watch = SimpleNamespace(stage=3, poll=Mock(return_value=True))
        participant.recovery_watch = watch
        try:
            with patch.object(subject.recovery, 'check_client_log') as client_log:
                participant.verify_logs(Path('/nonexistent/pair/server.log'), Path('/client.log'),
                                        {'ticket':'value'}, 'marker')
            self.assertEqual(watch.poll.call_count, 2)
            client_log.assert_called_once_with(Path('/client.log'), {'ticket':'value'}, 'marker')
        finally:
            participant.close()

    def test_diagnostic_cleanup_reaps_helpers_without_closing_server_control(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        helper, control = Mock(), Mock()
        participant.helpers.append(helper); participant.control = control
        self.assertTrue(participant.cleanup_diagnostic())
        helper.stop.assert_called_once_with()
        control.close.assert_not_called()

    def test_uncertain_helper_cleanup_is_failure_and_keeps_server_control(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        helper, control = Mock(), Mock()
        helper.stop.side_effect = RuntimeError('uncertain')
        participant.helpers.append(helper); participant.control = control
        with self.assertRaises(RuntimeError): participant.cleanup_diagnostic()
        control.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
