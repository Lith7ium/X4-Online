"""Loopback-only synthetic transport checks; not X4 or Internet validation.

FixtureUDP is intentionally limited to one fixture and one guest. Multi-ship
checks use the separate TCP ShipExchange; neither transport is a game server.
"""
import json
import select
from pathlib import Path
import socket
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.fixture_udp import FixtureUDP  # noqa: E402
from authority.transport import ShipExchange  # noqa: E402


class Peer:
    def __init__(self, address, name):
        self.socket = socket.create_connection(address, timeout=10)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.stream = self.socket.makefile('rwb')
        if not self.send({'op': 'hello', 'peer': name})['ok']:
            raise AssertionError('peer registration failed')

    def send(self, message):
        self.stream.write(json.dumps(message, separators=(',', ':')).encode() + b'\n')
        self.stream.flush()
        line = self.stream.readline()
        if not line:
            raise AssertionError('peer connection closed unexpectedly')
        return json.loads(line)

    def close(self):
        self.stream.close()
        self.socket.close()


def position(ship, seq):
    # Move in all three dimensions and occasionally cross synthetic frames.
    return {'sector': 'sector-%d' % ((ship + seq // 3) % 8),
            'x': ship * 1.25 + seq, 'y': -ship * 0.5 - seq * 2,
            'z': ship * 3.0 + seq * 0.25}


def update(ship, sequence):
    return {'op': 'update', 'world_epoch': 'world-scale', 'ship_id': 'ship-%05d' % ship,
            'generation': 1, 'authority_epoch': 2, 'sequence': sequence,
            'position': position(ship, sequence)}


class ScaleTests(unittest.TestCase):
    def test_many_moving_ships_with_three_simultaneous_clients(self):
        """10,000 identities, eight frames and concurrent independent writers."""
        exchange = ShipExchange(('127.0.0.1', 0), 'world-scale')
        thread = threading.Thread(target=exchange.serve_forever, daemon=True)
        thread.start()
        peers = []
        try:
            for name in ('server', 'client0', 'client1', 'client2', 'reader'):
                peers.append(Peer(exchange.server_address, name))
            server, *other = peers
            clients, reader = other[:3], other[3]
            for ship in range(10000):
                ident = 'ship-%05d' % ship
                created = server.send({'op': 'create', 'world_epoch': 'world-scale',
                                       'ship_id': ident, 'generation': 1,
                                       'position': position(ship, 0)})
                self.assertTrue(created['ok'], created)
                assigned = server.send({'op': 'assign', 'world_epoch': 'world-scale',
                                        'ship_id': ident, 'generation': 1,
                                        'authority_epoch': 1, 'owner': 'client%d' % (ship % 3)})
                self.assertTrue(assigned['ok'], assigned)

            # A missing sequence models a source update omitted before transport;
            # an older message and a duplicate must never replace newer state.
            def writer(client_index):
                peer = clients[client_index]
                for seq, expected in ((1, True), (3, True), (2, False), (3, False), (5, True)):
                    for ship in range(client_index, 10000, 3):
                        result = peer.send(update(ship, seq))
                        if result['ok'] != expected:
                            raise AssertionError((ship, seq, result))
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(writer, i) for i in range(3)]
                for future in futures:
                    future.result(timeout=120)

            rows = []
            revision = None
            offset = 0
            while offset is not None:
                response = reader.send({'op': 'snapshot', 'offset': offset, 'revision': revision})
                self.assertTrue(response['ok'], response)
                page = response['value']
                if revision is None:
                    revision = page['revision']
                self.assertEqual(page['revision'], revision)
                rows.extend(page['ships'])
                offset = page['next_offset']
            self.assertEqual(len(rows), 10000)
            for ship, row in enumerate(rows):
                self.assertEqual(row['ship_id'], 'ship-%05d' % ship)
                self.assertEqual(row['owner'], 'client%d' % (ship % 3))
                self.assertEqual(row['sequence'], 5)
                self.assertEqual(row['position'], position(ship, 5))
        finally:
            for peer in peers:
                peer.close()
            exchange.shutdown()
            exchange.server_close()
            thread.join(timeout=5)

    def test_one_fixture_udp_movement_with_omission_duplication_and_reordering(self):
        """Exercise 2,000 moving updates, with simulated omissions and duplicates."""
        adapter = FixtureUDP(fixture='one-fixture', source_lease='a' * 32,
                             guest_lease='b' * 32, max_age_seconds=60)
        source = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        guest = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        source.settimeout(3)
        guest.settimeout(3)
        try:
            for sock, role, lease in ((source, 'SOURCE', 'a' * 32),
                                      (guest, 'GUEST', 'b' * 32)):
                sock.sendto(f'FIX1|HELLO|{role}|{lease}|one-fixture'.encode(), adapter.address)
                self.assertTrue(select.select([adapter.sock], [], [], 3)[0])
                self.assertEqual(adapter.poll(), 1)
                self.assertEqual(sock.recv(512), f'FIX1|READY|{role}|one-fixture'.encode())
            for seq in range(1, 2001):
                # Send the actual update followed by an older update: the latter
                # must not roll back position or refresh its sequence.
                if seq % 13 == 0:
                    continue
                xyz = (seq * 1.5, -seq * 2.0, seq * 0.25)
                source.sendto(f'FIX1|PUT|{"a" * 32}|one-fixture|{seq}|{xyz[0]}|{xyz[1]}|{xyz[2]}'.encode(), adapter.address)
                if seq > 1 and seq % 7 == 0:
                    source.sendto(f'FIX1|PUT|{"a" * 32}|one-fixture|{seq - 1}|999|999|999'.encode(), adapter.address)
                if seq % 11 == 0:
                    source.sendto(f'FIX1|PUT|{"a" * 32}|one-fixture|{seq}|999|999|999'.encode(), adapter.address)
                self.assertTrue(select.select([adapter.sock], [], [], 3)[0])
                adapter.poll()
                if seq % 4 == 0:
                    guest.sendto(f'FIX1|GET|{"b" * 32}|one-fixture|{seq}'.encode(), adapter.address)
                    self.assertTrue(select.select([adapter.sock], [], [], 3)[0])
                    self.assertEqual(adapter.poll(), 1)
                    parts = guest.recv(512).decode().split('|')
                    self.assertEqual(parts[:5], ['FIX1', 'POS', 'one-fixture', str(seq), str(seq)])
                    self.assertEqual(tuple(map(float, parts[5:])), xyz)
        finally:
            source.close()
            guest.close()
            adapter.close()


if __name__ == '__main__':
    unittest.main()
