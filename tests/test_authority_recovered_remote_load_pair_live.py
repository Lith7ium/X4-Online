"""Offline composition checks; no processes or native X4 are started."""
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovered_remote_load_pair_live as subject


class RecoveredRemotePairTest(unittest.TestCase):
    def test_recovery_freshness_guard_wraps_actual_remote_transfer(self):
        participant = subject.RecoveredRemoteParticipant(time.monotonic()+20, Path('/test'))
        participant.checkpoint = SimpleNamespace(checkpoint_id='old', marker='old-marker')
        try:
            def transfer(instance, world, service, handle, out, profile):
                self.assertIs(instance, participant)
                instance.marker = 'new-marker'
                return {'checkpoint_id':'new'}, Path('/private/save')
            with patch.object(subject.remote.RemoteParticipant, 'offer_and_download', transfer):
                ticket, target = participant.offer_and_download(None, None, 1, None, None)
                self.assertEqual(ticket['checkpoint_id'], 'new')
                self.assertEqual(target, Path('/private/save'))
            with patch.object(subject.remote.RemoteParticipant, 'offer_and_download',
                              return_value=({'checkpoint_id':'old'}, Path('/private/save'))):
                with self.assertRaises(ValueError):
                    participant.offer_and_download(None, None, 1, None, None)
            self.assertIs(type(participant).join, subject.remote.RemoteParticipant.join)
            self.assertIs(type(participant).finish_remote_load, subject.remote.RemoteParticipant.finish_remote_load)
            self.assertIs(type(participant).verify_logs, subject.recovery.RecoveredParticipant.verify_logs)
        finally:
            participant.close()

    def test_run_restores_factory_and_reports_scope(self):
        original = subject.recovery.RecoveredParticipant
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(out=Path(tmp))
            def fake_run(_args):
                self.assertIs(subject.recovery.RecoveredParticipant, subject.RecoveredRemoteParticipant)
                return {'success':True}
            with patch.object(subject.recovery, 'run', side_effect=fake_run):
                result = subject.run(args)
            self.assertIs(subject.recovery.RecoveredParticipant, original)
            self.assertFalse(result['persistent_loopback_server_used'])
            self.assertFalse(result['repeated_joins_tested'])
            self.assertFalse(result['windows_tested'])
            self.assertEqual(json.loads((args.out/'result.json').read_text()), result)
            with patch.object(subject.recovery, 'run', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    subject.run(args)
            self.assertIs(subject.recovery.RecoveredParticipant, original)


if __name__ == '__main__':
    unittest.main()
