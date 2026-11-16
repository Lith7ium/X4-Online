"""Real local UDP/TCP, simulated X4 owner; no X4 process is started."""
import json
from pathlib import Path
import select
import socket
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.experimental_participant_job_ipc import ExperimentalParticipantJobIPC
from authority.experimental_tcp_job_delivery import job_digest
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

LEASE, ATTEMPT, EPOCH, GENERATION = ('a'*32, 'b'*32, 'c'*32, 'd'*32)
EVENT = {'epoch': EPOCH, 'generation': GENERATION, 'sequence': 1, 'index': 10055,
         'descriptor': {'macro': 'ship_test', 'faction': 'argon', 'sector_macro': 'sector_a',
                        'x': 1.25, 'y': -2.5, 'z': 3}}
READY = f'X|{LEASE}|{ATTEMPT}|READY|{EPOCH}|{GENERATION}'.encode()


def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 0)); s.settimeout(2)
    return s


class Controller:
    def pause(self, handles): return True
    def resume(self, handles): return True


class IPC(unittest.TestCase):
    def test_real_participant_waits_for_exact_applied_before_tcp_receipt(self):
        ipc, x4 = udp(), udp()
        self.addCleanup(ipc.close); self.addCleanup(x4.close)
        listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1)
        self.addCleanup(listener.close)
        server = socket.create_connection(listener.getsockname()); client, _ = listener.accept()
        self.addCleanup(server.close); self.addCleanup(client.close); server.settimeout(2)
        errors = []; peer_seen = []; ready = threading.Event()
        def run():
            try:
                bridge = ExperimentalParticipantJobIPC(ipc, enabled=True, lease=LEASE, attempt=ATTEMPT,
                    epoch=EPOCH, generation=GENERATION, guard=lambda: True,
                    validate_peer=lambda peer: peer_seen.append(peer) or peer == x4.getsockname(), timeout=1)
                ready.set(); bridge.wait_ready()
                participant = ExperimentalTCPParticipantClient(client, Controller(), enabled=True,
                    epoch=EPOCH, handle=1, timeout=2, apply_job=bridge)
                delivered = 0
                while delivered < 2:
                    if participant.poll(.05): delivered += 1
                participant.close(); bridge.close()
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=run); thread.start(); self.addCleanup(thread.join, 3)
        self.assertTrue(ready.wait(1)); x4.sendto(READY, ipc.getsockname())
        for seq, index, sector in ((1, 10055, 'sector_a'), (2, 10056, 'sector_b')):
            event = dict(EVENT, sequence=seq, index=index,
                         descriptor=dict(EVENT['descriptor'], sector_macro=sector))
            command = {'version': 1, 'kind': 'job_delivery', 'connection_handle': 1, 'request_id': seq,
                       'session_epoch': EPOCH, 'incarnation': 'e'*32, 'event': event}
            server.sendall(json.dumps(command).encode()+b'\n')
            packet, address = x4.recvfrom(769); parts = packet.decode().split('|')
            self.assertEqual(parts[:4], ['P', LEASE, ATTEMPT, 'APPLY'])
            self.assertEqual(parts[5:10], [EPOCH, GENERATION, str(seq), str(index), job_digest(event)])
            self.assertEqual(parts[10:13], ['ship_test', 'argon', sector])
            self.assertFalse(select.select([server], [], [], .05)[0])
            x4.sendto('|'.join(['X', LEASE, ATTEMPT, 'APPLIED', *parts[4:10]]).encode(), address)
            receipt = json.loads(server.recv(4096))
            self.assertEqual(receipt['kind'], 'job_receipt')
            self.assertEqual(receipt['event_sha256'], job_digest(event))
        thread.join(3); self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        self.assertTrue(peer_seen)
        self.assertTrue(all(peer == x4.getsockname() for peer in peer_seen))

    def test_wrong_response_fences_and_cannot_retry(self):
        ipc, x4 = udp(), udp(); self.addCleanup(ipc.close); self.addCleanup(x4.close)
        bridge = ExperimentalParticipantJobIPC(ipc, enabled=True, lease=LEASE, attempt=ATTEMPT,
            epoch=EPOCH, generation=GENERATION, guard=lambda: True,
            validate_peer=lambda peer: peer == x4.getsockname(), timeout=.5)
        x4.sendto(READY, ipc.getsockname()); self.assertTrue(bridge.wait_ready())
        def fake_x4():
            packet, address = x4.recvfrom(769); parts = packet.decode().split('|')
            parts[9] = 'f'*64
            x4.sendto('|'.join(['X', LEASE, ATTEMPT, 'APPLIED', *parts[4:10]]).encode(), address)
        thread = threading.Thread(target=fake_x4); thread.start(); self.addCleanup(thread.join, 2)
        with self.assertRaises(ValueError): bridge(EVENT)
        self.assertEqual(bridge.state, 'failed')
        with self.assertRaises(RuntimeError): bridge(EVENT)

    def test_unverified_peer_and_timeout_fail_closed(self):
        ipc, x4 = udp(), udp(); self.addCleanup(ipc.close); self.addCleanup(x4.close)
        bridge = ExperimentalParticipantJobIPC(ipc, enabled=True, lease=LEASE, attempt=ATTEMPT,
            epoch=EPOCH, generation=GENERATION, guard=lambda: True,
            validate_peer=lambda peer: False, timeout=.1)
        x4.sendto(READY, ipc.getsockname())
        with self.assertRaises(RuntimeError): bridge.wait_ready()
        self.assertEqual(bridge.state, 'failed')
        ipc2 = udp(); self.addCleanup(ipc2.close)
        bridge2 = ExperimentalParticipantJobIPC(ipc2, enabled=True, lease=LEASE, attempt=ATTEMPT,
            epoch=EPOCH, generation=GENERATION, guard=lambda: True,
            validate_peer=lambda peer: True, timeout=.05)
        x4.sendto(READY, ipc2.getsockname()); self.assertTrue(bridge2.wait_ready())
        with self.assertRaises(RuntimeError): bridge2(EVENT)
        self.assertEqual(bridge2.state, 'failed')

    def test_peer_ownership_loss_prevents_dispatch(self):
        ipc, x4 = udp(), udp(); self.addCleanup(ipc.close); self.addCleanup(x4.close)
        owned = [True]
        bridge = ExperimentalParticipantJobIPC(ipc, enabled=True, lease=LEASE, attempt=ATTEMPT,
            epoch=EPOCH, generation=GENERATION, guard=lambda: True,
            validate_peer=lambda peer: owned[0] and peer == x4.getsockname(), timeout=.2)
        x4.sendto(READY, ipc.getsockname()); self.assertTrue(bridge.wait_ready()); owned[0] = False
        with self.assertRaises(RuntimeError): bridge(EVENT)
        self.assertEqual(bridge.state, 'failed')
        self.assertFalse(select.select([x4], [], [], .02)[0])


if __name__ == '__main__': unittest.main()
