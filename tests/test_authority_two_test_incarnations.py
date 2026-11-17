"""Explicit two-peer diagnostic incarnation binding over local TCP."""
import select
import unittest
from unittest.mock import patch

from tests import test_authority_experimental_tcp_participants as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_participants import ExperimentalTCPParticipants


class TwoTestIncarnations(unittest.TestCase):
    def pair(self):
        case = fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp()
        self.addCleanup(case.doCleanups)
        first, second = case.connect(), case.connect()
        case.offer_and_claim(first)
        case.offer_and_claim(second)
        case.responder(first)
        case.responder(second)
        case.host.tick(.1)
        return case, first, second, ExperimentalTCPJobDelivery(case.host, enabled=True, timeout=1)

    def test_binds_exact_sockets_with_supplied_distinct_tokens(self):
        case, _, _, delivery = self.pair()
        self.assertTrue(delivery.bind_test_incarnations({2:'c'*32, 1:'b'*32}, enabled=True))
        self.assertEqual(delivery.membership(), ({'id':'peer_1', 'incarnation':'b'*32},
                                                 {'id':'peer_2', 'incarnation':'c'*32}))
        with self.assertRaises(ValueError):
            delivery.bind_test_incarnations({1:'b'*32, 2:'c'*32}, enabled=True)
        self.assertTrue(case.host._failed)

    def test_wrong_or_reused_input_fences_without_minting(self):
        cases = ({1:'b'*32}, {1:'b'*32, 3:'c'*32}, {1:'b'*32, 2:'b'*32},
                 {1:'b'*32, 2:'invalid'}, {True:'b'*32, 2:'c'*32})
        for bindings in cases:
            with self.subTest(bindings=bindings):
                case, _, _, delivery = self.pair()
                with self.assertRaises(ValueError): delivery.bind_test_incarnations(bindings, enabled=True)
                self.assertTrue(case.host._failed)
                self.assertEqual(delivery._incarnations, {})

    def test_membership_and_socket_changes_fence_without_regeneration(self):
        case, _, _, delivery = self.pair()
        delivery.bind_test_incarnations({1:'b'*32, 2:'c'*32}, enabled=True)
        conn, state = next((conn, state) for conn, state in case.control._peers.items() if state['handle'] == 2)
        case.control._peers[conn] = dict(state)
        with self.assertRaises(RuntimeError): delivery.membership()
        self.assertTrue(case.host._failed)
        self.assertEqual(delivery._incarnations, {1:'b'*32, 2:'c'*32})

    def test_unsolicited_other_peer_and_reentry_fence_without_binding(self):
        case, _, second, delivery = self.pair()
        second.sendall(b'unexpected\n')
        server = next(conn for conn, state in case.control._peers.items() if state['handle'] == 2)
        self.assertIn(server, select.select([server], [], [], 1)[0])
        with self.assertRaises(RuntimeError):
            delivery.bind_test_incarnations({1:'b'*32, 2:'c'*32}, enabled=True)
        self.assertEqual(delivery._incarnations, {})
        case, _, _, delivery = self.pair()
        original = ExperimentalTCPParticipants._quiet
        def reenter(*args):
            try: delivery.bind_test_incarnation(1, 'b'*32, enabled=True)
            except RuntimeError: pass
            return original(*args)
        with patch.object(ExperimentalTCPParticipants, '_quiet', side_effect=reenter):
            with self.assertRaises(RuntimeError):
                delivery.bind_test_incarnations({1:'b'*32, 2:'c'*32}, enabled=True)
        self.assertTrue(case.host._failed)
        self.assertEqual(delivery._incarnations, {})


if __name__ == '__main__':
    unittest.main()
