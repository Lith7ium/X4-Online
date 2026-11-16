"""Explicit long budgets remain bounded and preserve ordinary limits."""
from pathlib import Path
import socket
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
import authority.experimental_source_motion_ipc as source_ipc
import authority.experimental_tcp_job_delivery as job_delivery
import authority_recovered_loopback_server as supervisor
import test_authority_experimental_tcp_participants as fixture


class LongDiagnosticTests(unittest.TestCase):
    def setUp(self):
        fixture.ParticipantTCPTest.setUp(self)
        self.local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(self.local.close)
        self.addCleanup(self.remote.close)
        self.local.bind(('127.0.0.1', 0))
        self.remote.bind(('127.0.0.1', 0))
        self.local.connect(self.remote.getsockname())
        self.remote.connect(self.local.getsockname())
        self.remote.settimeout(2)

    def source(self, motion, timeout, **options):
        return ExperimentalSourceMotionIPC(
            self.local, motion, enabled=True, lease='1'*32, attempt='2'*32,
            epoch='b'*32, generation='c'*32, guard=lambda: True,
            validate_peer=lambda peer: peer == self.remote.getsockname(),
            timeout=timeout, **options)

    def test_cli_option_requires_private_single_client_motion(self):
        for witness, source, client in ((False, True, True), (True, False, True), (True, True, False)):
            with self.subTest(witness=witness, source=source, client=client):
                with self.assertRaises(ValueError):
                    supervisor.diagnostic_long_motion(SimpleNamespace(diagnostic_long_motion=True), witness, source, client)
        self.assertTrue(supervisor.diagnostic_long_motion(
            SimpleNamespace(diagnostic_long_motion=True), True, True, True))
        self.assertFalse(supervisor.diagnostic_long_motion(SimpleNamespace(), True, True, True))
        with self.assertRaises(ValueError):
            supervisor.diagnostic_long_motion(SimpleNamespace(diagnostic_long_motion=1), True, True, True)

    def test_source_deadline_is_enforced_after_more_than_300_seconds(self):
        delivery = ExperimentalTCPJobDelivery(self.host, enabled=True, timeout=480,
                                              private_long_diagnostic=True)
        motion = ExperimentalTCPMotion(delivery, enabled=True)
        bridge = self.source(motion, 600, saved_baseline=1, saved_guard=lambda *_: True,
                             stop_enabled=True, private_long_diagnostic=True)
        clock = [0.0]
        waited = []

        def select_timeout(read, write, exceptional, timeout):
            if timeout:
                clock[0] = 301.0 if not waited else 600.0
                waited.append(clock[0])
            return [], [], []

        with patch.object(source_ipc.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(source_ipc.select, 'select', side_effect=select_timeout):
            with self.assertRaisesRegex(RuntimeError, 'deadline'):
                bridge.register_saved(1)
        self.assertEqual(waited, [301.0, 600.0])
        self.assertEqual(self.remote.recv(769).decode().split('|')[3], 'REGISTER_SAVED')
        self.remote.settimeout(.05)
        with self.assertRaises(TimeoutError):
            self.remote.recv(769)
        self.assertEqual(bridge.state, 'failed')
        self.assertTrue(self.host._failed)

    def test_delivery_fails_at_its_480_second_deadline_without_ack(self):
        delivery = ExperimentalTCPJobDelivery(self.host, enabled=True, timeout=480,
                                              private_long_diagnostic=True)
        delivery._incarnations[1] = 'd'*32
        connection = object()
        peers = {1: (connection, {})}
        event = {'epoch': 'b'*32, 'generation': 'c'*32, 'sequence': 1, 'index': 1,
                 'descriptor': {'macro': 'ship_test_macro', 'faction': 'pioneers',
                                'sector_macro': 'sector_a', 'x': 1, 'y': 2, 'z': 3}}
        clock = [0.0]
        passed = []
        acknowledgements = []

        def exchange(_delivery, _conn, _peer, _others, _frame, _expected, deadline):
            self.assertEqual(deadline, 480.0)
            clock[0] = 301.0
            passed.append(clock[0] < deadline)
            clock[0] = 480.0

        with patch.object(job_delivery.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(delivery, '_peers', return_value=((1,), peers)), \
             patch.object(ExperimentalTCPParticipants, '_quiet'), \
             patch.object(ExperimentalTCPParticipants, '_exchange', side_effect=exchange):
            with self.assertRaises(TimeoutError):
                delivery.deliver(event, [{'id': 'peer_1', 'incarnation': 'd'*32}],
                                 lambda peer, item: acknowledgements.append((peer, item)) or True)
        self.assertEqual(passed, [True])
        self.assertEqual(acknowledgements, [])
        self.assertTrue(delivery._failed)
        self.assertTrue(self.host._failed)

    def test_default_and_long_upper_bounds_and_correlated_stop(self):
        host = self.host
        for options in ({}, {'private_long_diagnostic': False}, {'private_long_diagnostic': 1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ExperimentalTCPJobDelivery(host, enabled=True, timeout=301, **options)
        with self.assertRaises(ValueError):
            ExperimentalTCPJobDelivery(host, enabled=True, timeout=481, private_long_diagnostic=True)
        delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=480, private_long_diagnostic=True)
        motion = ExperimentalTCPMotion(delivery, enabled=True)
        common = {'saved_baseline': 1, 'saved_guard': lambda epoch, count: True, 'stop_enabled': True}
        for timeout, options in ((600, common), (601, dict(common, private_long_diagnostic=True)),
                                 (600, {'private_long_diagnostic': True, 'stop_enabled': True}),
                                 (600, dict(common, private_long_diagnostic=1))):
            with self.subTest(timeout=timeout, options=options), self.assertRaises(ValueError):
                self.source(motion, timeout, **options)
        bridge = self.source(motion, 600, **dict(common, private_long_diagnostic=True))
        received = []

        def peer():
            fields = self.remote.recv(769).decode().split('|')
            received.append(fields)
            self.remote.send('|'.join(['S', '1'*32, '2'*32, 'STOPPED', 'b'*32, 'c'*32, fields[6]]).encode())

        thread = threading.Thread(target=peer)
        thread.start()
        try:
            self.assertTrue(bridge.stop_remote())
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received[0][3], 'STOP')
        bridge.close()


if __name__ == '__main__':
    unittest.main()
