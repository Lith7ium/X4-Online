import select
import socket
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.fixture_udp import FixtureUDP, MAX_DATAGRAM  # noqa: E402


class FixtureUDPTests(unittest.TestCase):
    def setUp(self):
        self.source = self.endpoint()
        self.guest = self.endpoint()
        self.foreign = self.endpoint()
        self.adapter = FixtureUDP(fixture='fixture-1', source_lease='a' * 32,
                                  guest_lease='b' * 32, max_age_seconds=2)
        self.addCleanup(self.adapter.close)

    def endpoint(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        sock.settimeout(1)
        self.addCleanup(sock.close)
        return sock

    def send(self, sock, packet):
        if isinstance(packet, str):
            packet = packet.encode('ascii')
        sock.sendto(packet, self.adapter.address)
        readable, _, _ = select.select([self.adapter.sock], [], [], 1)
        self.assertTrue(readable, 'local packet did not arrive')
        self.assertEqual(self.adapter.poll(), 1)

    def no_reply(self, sock):
        self.assertFalse(select.select([sock], [], [], .01)[0])

    def put(self, seq, coords='1|2|3', lease='a' * 32, fixture='fixture-1', sock=None):
        self.send(sock or self.source, f'FIX1|PUT|{lease}|{fixture}|{seq}|{coords}')

    def get(self, seq, lease='b' * 32, fixture='fixture-1', sock=None):
        self.send(sock or self.guest, f'FIX1|GET|{lease}|{fixture}|{seq}')

    def receive(self):
        self.assertTrue(select.select([self.guest], [], [], 1)[0])
        data, sender = self.guest.recvfrom(MAX_DATAGRAM)
        self.assertEqual(sender, self.adapter.address)
        return data.decode('ascii').split('|')

    def hello(self, sock, role, lease):
        self.send(sock, f'FIX1|HELLO|{role}|{lease}|fixture-1')

    def register(self):
        self.hello(self.source, 'SOURCE', 'a' * 32)
        self.assertEqual(self.source.recvfrom(512)[0], b'FIX1|READY|SOURCE|fixture-1')
        self.hello(self.guest, 'GUEST', 'b' * 32)
        self.assertEqual(self.receive(), ['FIX1', 'READY', 'GUEST', 'fixture-1'])

    def test_registration_binds_endpoint_and_hello_retry_is_idempotent(self):
        self.put(1)
        self.get(1)
        self.no_reply(self.source)
        self.no_reply(self.guest)
        self.hello(self.foreign, 'SOURCE', 'b' * 32)
        self.no_reply(self.foreign)
        self.hello(self.source, 'SOURCE', 'a' * 32)
        self.assertEqual(self.source.recvfrom(512)[0], b'FIX1|READY|SOURCE|fixture-1')
        self.hello(self.source, 'GUEST', 'b' * 32)
        self.no_reply(self.source)
        self.hello(self.guest, 'GUEST', 'b' * 32)
        self.assertEqual(self.receive(), ['FIX1', 'READY', 'GUEST', 'fixture-1'])
        self.hello(self.source, 'SOURCE', 'a' * 32)
        self.assertEqual(self.source.recvfrom(512)[0], b'FIX1|READY|SOURCE|fixture-1')
        self.hello(self.foreign, 'SOURCE', 'a' * 32)
        self.hello(self.foreign, 'GUEST', 'b' * 32)
        self.hello(self.source, 'GUEST', 'b' * 32)
        self.hello(self.guest, 'SOURCE', 'a' * 32)
        self.no_reply(self.foreign)
        self.no_reply(self.source)
        self.no_reply(self.guest)
        self.put(1)
        self.get(1)
        self.assertEqual(self.receive()[3:5], ['1', '1'])

    def test_loopback_transfer_duplicates_reordering_and_role_restrictions(self):
        self.register()
        self.get(1)
        self.no_reply(self.guest)
        self.put(3, '1.5|-2|3e2')
        self.no_reply(self.source)
        self.put(3, '999|999|999')
        self.put(2, '999|999|999')
        self.get(2)
        self.assertEqual(self.receive(), ['FIX1', 'POS', 'fixture-1', '2', '3', '1.5', '-2.0', '300.0'])
        self.get(2)
        self.get(1)
        self.no_reply(self.guest)
        self.put(4, '-1|0|5')
        self.get(3)
        self.assertEqual(self.receive(), ['FIX1', 'POS', 'fixture-1', '3', '4', '-1.0', '0.0', '5.0'])

    def test_foreign_endpoint_wrong_role_wrong_lease_and_invalid_data(self):
        self.register()
        self.put(1, sock=self.foreign)
        self.put(1, lease='b' * 32)
        self.put(1, fixture='fixture-2')
        self.put(1, coords='NaN|1|2')
        self.put(1, coords='1e999|1|2')
        self.put(1, coords='1|2|3|4')
        self.put('01')
        self.put(9007199254740992)
        self.send(self.source, b'x' * (MAX_DATAGRAM + 1))
        self.send(self.source, b'\xff')
        self.get(1)
        self.no_reply(self.guest)
        self.put(1)
        self.get(2, lease='a' * 32)
        self.get(2, fixture='fixture-2')
        self.get(2, sock=self.foreign)
        self.get(2, sock=self.source)
        self.no_reply(self.foreign)
        self.no_reply(self.source)
        self.no_reply(self.guest)
        self.get(2)
        self.assertEqual(self.receive()[3:5], ['2', '1'])

    def test_old_samples_expire_and_fresh_sequence_is_required(self):
        self.register()
        self.adapter.max_age = .08
        self.put(1)
        time.sleep(.11)
        self.get(1)
        self.no_reply(self.guest)
        self.put(1, '4|5|6')  # duplicate cannot refresh the age
        self.get(2)
        self.no_reply(self.guest)
        self.put(2, '4|5|6')
        self.get(2)  # rejected GET sequence was consumed
        self.no_reply(self.guest)
        self.get(3)
        self.assertEqual(self.receive()[3:], ['3', '2', '4.0', '5.0', '6.0'])

    def test_configuration_is_local_explicit_and_bounded(self):
        opts = dict(fixture='fixture-1', source_lease='a' * 32, guest_lease='b' * 32, max_age_seconds=1)
        for change in (dict(bind=('0.0.0.0', 0)), dict(guest_lease='a' * 32),
                       dict(source_lease='short'), dict(fixture='a|b'), dict(max_age_seconds=float('nan')),
                       dict(max_age_seconds=0), dict(max_age_seconds=61)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                FixtureUDP(**(opts | change))
        for invalid in (0, 65, True):
            with self.subTest(max_packets=invalid), self.assertRaises(ValueError):
                self.adapter.poll(invalid)


if __name__ == '__main__':
    unittest.main()
