"""Legacy authority domains reject V3; synthetic TCP, no native engine."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from authority.experimental_tcp_motion import motion_digest
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
import test_authority_tcp_client_authority_motion as fixture
from test_authority_experimental_tcp_motion import MotionTCP


def real_time_sample(sequence):
    value = MotionTCP.sample(sequence, t=sequence)
    del value['velocity']
    return dict(value, version=3, capture_time=100 + sequence, real_velocity=None)


class LegacyAuthorityVersionRefusal(unittest.TestCase):
    def setup_pair(self, values):
        return fixture.AuthorityTCP.setup_pair(self, values)

    def test_participant_rejects_v3_on_first_or_later_pull_without_success_receipt(self):
        for later in (False, True):
            with self.subTest(later=later):
                values = [MotionTCP.sample()] if later else []
                values.append(real_time_sample(2 if later else 1))
                case, owner, _, calls, _ = self.setup_pair(values)
                if later:
                    self.assertEqual(owner.pull()['version'], 1)
                with self.assertRaises((ValueError, RuntimeError, ConnectionError, OSError)):
                    owner.pull()
                self.assertEqual(owner._last_sequence, 1 if later else 0)
                self.assertEqual(len(calls), 2 if later else 1)
                self.assertTrue(case.case.host._failed)

    def test_server_rejects_forged_v3_first_or_later_result_before_state_advance(self):
        for later in (False, True):
            with self.subTest(later=later):
                case, owner, _, calls, _ = self.setup_pair([MotionTCP.sample()])
                if later:
                    owner.pull()
                def exchange(delivery, connection, peer, others, payload, expected, deadline, **options):
                    request = json.loads(payload)
                    value = real_time_sample(2 if later else 1)
                    answer = {key: request[key] for key in
                              ('version', 'connection_handle', 'session_epoch', 'incarnation', 'request_id', 'grant')}
                    answer.update(kind='authority_motion_result', sample=value,
                                  sample_sha256=motion_digest(value))
                    self.assertFalse(options['validate_answer'](answer))
                    raise ValueError('unsupported forged response')
                with patch.object(ExperimentalTCPParticipants, '_exchange', side_effect=exchange):
                    with self.assertRaisesRegex(ValueError, 'unsupported forged response'):
                        owner.pull()
                self.assertEqual(owner._last_sequence, 1 if later else 0)
                self.assertEqual(len(calls), 1 if later else 0)
                self.assertTrue(case.case.host._failed)


if __name__ == '__main__':
    unittest.main()
