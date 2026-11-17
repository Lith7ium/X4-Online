"""Local participant/receipt correlation; no X4 or network is started."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority_recovered_server_client import CorrelatedClientSector


class ClientSectorCorrelation(unittest.TestCase):
    def setUp(self):
        self.peer = object()
        self.peer_state = {'stage': 'admitted', 'handle': 7}
        self.control = SimpleNamespace(_peers={self.peer: self.peer_state})
        self.host = SimpleNamespace(_control=self.control)
        self.world = SimpleNamespace(session=object())
        self.participant = SimpleNamespace(server_tcp=self.peer, motion_stop_confirmed=False,
            _sector_incarnation='a'*32,
            motion_installation=SimpleNamespace(secrets={'player_sector_incarnation':'a'*32}),
            check_active=Mock(return_value=True), check_motion_stopped=Mock(return_value=True))
        self.watch = SimpleNamespace(observe=Mock(return_value='sector_a'), confirm_stop=Mock(),
                                     finish=Mock(return_value='sector_a'))
        self.owner = CorrelatedClientSector(self.watch, self.participant, self.world, self.host, 7)
        self.member = {'id':'peer_7', 'incarnation':'a'*32}
        self.receipt = (2, 'b'*64)

    def test_bound_receipt_stopped_worker_and_final_observation(self):
        self.assertEqual(self.owner.poll(self.member, self.receipt), 'sector_a')
        with self.assertRaises(RuntimeError):
            self.owner.stop()
        self.participant.motion_stop_confirmed=True
        self.assertTrue(self.owner.stop())
        self.watch.confirm_stop.assert_called_once_with(confirmed=True)
        result = self.owner.finish()
        self.assertEqual(result['sector_macro'], 'sector_a')
        self.assertEqual(result['participant_id'], 'peer_7')
        self.assertEqual(result['motion_sample_sha256'], 'b'*64)
        self.assertNotIn('a'*32, str(result))

    def test_changed_participant_incarnation_or_receipt_is_rejected(self):
        self.assertEqual(self.owner.poll(self.member, self.receipt), 'sector_a')
        for member, receipt in ((dict(self.member, incarnation='c'*32), self.receipt),
                                (self.member, (2, 'd'*64)),
                                (dict(self.member, id='peer_8'), self.receipt),
                                (self.member, (1, 'b'*64))):
            with self.subTest(member=member, receipt=receipt):
                with self.assertRaises(RuntimeError):
                    self.owner.poll(member, receipt)

    def test_guard_and_peer_are_rechecked_after_read(self):
        def mutate():
            self.participant.server_tcp = object()
            return 'sector_a'
        self.watch.observe.side_effect = mutate
        with self.assertRaises(RuntimeError):
            self.owner.poll(self.member, self.receipt)
        self.assertIsNone(self.owner.value)

    def test_peer_mutation_during_guard_is_rejected(self):
        def mutate(**_):
            self.control._peers[self.peer] = {'stage':'admitted', 'handle':7}
            return True
        self.participant.check_active.side_effect = mutate
        with self.assertRaises(RuntimeError):
            self.owner.poll(self.member, self.receipt)
        self.watch.observe.assert_not_called()

    def test_installation_token_mutation_is_rejected(self):
        self.participant.motion_installation.secrets['player_sector_incarnation']='c'*32
        with self.assertRaises(RuntimeError):
            self.owner.poll(self.member, self.receipt)
        self.watch.observe.assert_not_called()

    def test_missing_or_changed_final_value_is_rejected(self):
        self.owner.poll(self.member, self.receipt)
        self.participant.motion_stop_confirmed=True
        self.owner.stop()
        self.watch.finish.return_value='sector_b'
        with self.assertRaises(ValueError):
            self.owner.finish()

    def test_incarnation_mutation_during_stopped_worker_or_log_check_faults(self):
        for where in ('worker', 'stop_log', 'final_log'):
            with self.subTest(where=where):
                self.setUp()
                self.owner.poll(self.member, self.receipt)
                self.participant.motion_stop_confirmed=True
                def mutate():
                    self.participant.motion_installation.secrets['player_sector_incarnation']='c'*32
                    return True
                if where=='worker':
                    self.participant.check_motion_stopped.side_effect=mutate
                elif where=='stop_log':
                    self.watch.confirm_stop.side_effect=lambda **_: mutate()
                else:
                    self.owner.stop()
                    self.watch.finish.side_effect=lambda **_: mutate() and 'sector_a'
                with self.assertRaises((RuntimeError, ValueError)):
                    self.owner.finish() if where=='final_log' else self.owner.stop()


if __name__ == '__main__':
    unittest.main()
