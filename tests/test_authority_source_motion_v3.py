"""Version 3 source samples over loopback UDP and admitted TCP (synthetic peers)."""
import socket
import threading
import unittest

from tests import test_authority_experimental_tcp_motion as tcp_fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC


class SourceMotionV3(unittest.TestCase):
    def bridge(self, replies):
        case = tcp_fixture.MotionTCP('test_invalid_values_and_no_fake_velocity')
        case.setUp()
        self.addCleanup(case.doCleanups)
        peer = case.case.connect()
        case.case.offer_and_claim(peer)
        case.client(peer, 1)
        case.case.host.tick(.1)
        delivery = ExperimentalTCPJobDelivery(case.case.host, enabled=True, timeout=1)
        motion = ExperimentalTCPMotion(delivery, enabled=True, min_interval=1/240)
        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        local.bind(('127.0.0.1', 0)); remote.bind(('127.0.0.1', 0))
        local.connect(remote.getsockname()); remote.connect(local.getsockname())
        self.addCleanup(local.close); self.addCleanup(remote.close)
        def source():
            remote.settimeout(2)
            for kind, fields in replies:
                try:
                    request = remote.recv(769).decode().split('|')[-1]
                    packet = ['S', '1'*32, '2'*32, kind, 'b'*32, 'c'*32, request, *fields]
                    remote.send('|'.join(packet).encode())
                except (OSError, TimeoutError):
                    return
        thread = threading.Thread(target=source)
        thread.start(); self.addCleanup(thread.join, 3)
        bridge = ExperimentalSourceMotionIPC(local, motion, enabled=True, lease='1'*32,
            attempt='2'*32, epoch='b'*32, generation='c'*32, guard=lambda: True,
            validate_peer=lambda peer: peer == remote.getsockname(), timeout=2)
        bridge.bind_confirmed(10055)
        return case, bridge

    @staticmethod
    def v3(seq, game='1', capture='10', frame='sector_a', rate=('-', '-', '-')):
        return ('SAMPLE3', ['10055', str(seq), frame, game, capture, '1', '2', '3', *rate])

    def test_equal_game_time_unknown_and_real_rate_reach_tcp(self):
        case, bridge = self.bridge([self.v3(1), self.v3(2, capture='11', rate=('0', '2', '-3'))])
        first = bridge.pull(); second = bridge.pull()
        self.assertIsNone(first['real_velocity'])
        self.assertEqual(second['real_velocity'], {'x': 0, 'y': 2, 'z': -3})
        self.assertEqual(second['source_time'], first['source_time'])
        self.assertEqual([value for _, value, _ in case.received], [first, second])
        bridge.close()

    def test_reject_invalid_or_inconsistent_streams(self):
        initial = self.v3(1)
        invalid = [
            self.v3(2, capture='nan'), self.v3(2, capture='-1'),
            self.v3(2, capture='10'), self.v3(2, capture='9'),
            self.v3(2, game='0', capture='11'),
            self.v3(2, capture='11', frame='sector_b', rate=('1', '0', '0')),
            ('SAMPLE', ['10055', '2', 'sector_a', '2', '1', '2', '3', '-', '-', '-']),
            ('SAMPLE3', ['10055', '2', 'sector_a', '1', '11', '1', '2', '3', '-', '-', '0']),
        ]
        for bad in invalid:
            with self.subTest(packet=bad):
                case, bridge = self.bridge([initial, bad])
                bridge.pull()
                with self.assertRaises(ValueError): bridge.pull()
                self.assertEqual(len(case.received), 1)
                self.assertTrue(case.case.host._failed)


if __name__ == '__main__':
    unittest.main()
