"""Real loopback TCP, synthetic clients and game; no native X4 or WAN."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl, offer_request
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
from authority.save_transfer import SaveOffers
from authority.trusted_load_messages import decode_bound_offer, encode_load_claim
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_experimental_local_host import Engine
from test_authority_trusted_marker_load_session import claim_for


class ParticipantTCPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); (root/'store').mkdir()
        self.store = CheckpointStore(root/'store')
        self.service = FileService('a'*32, bind='127.0.0.1', port=0, slots=(1,2)).start()
        self.addCleanup(self.service.thread.join, 2); self.addCleanup(self.service.close)
        self.engine = Engine(root)
        self.world = WorldCoordinator('a'*32, self.engine, self.store, SaveOffers(self.service, self.store))
        self.control = ExperimentalTCPControl(TrustedMarkerLoadSession(self.world, enabled=True), enabled=True)
        self.addCleanup(lambda: self.control.close() if not (self.control._closed or self.control._failed) else None)
        self.host = ExperimentalLocalHost(self.world, self.control, self.service, enabled=True)
        self.participants = ExperimentalTCPParticipants(self.host, enabled=True, timeout=.3)
        self.world._participants = self.participants
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0)); self.listener.listen(3); self.addCleanup(self.listener.close)
        self.host.tick()

    def connect(self):
        client = socket.create_connection(self.listener.getsockname(), timeout=1)
        self.addCleanup(client.close)
        conn, _ = self.listener.accept(); self.host.adopt(conn)
        return client

    def offer_and_claim(self, client):
        self.host.tick()  # confirmed save
        client.sendall(offer_request()); self.host.tick(.1); self.host.tick(.1)
        bound = decode_bound_offer(client.recv(8192).rstrip(b'\n'))
        client.sendall(encode_load_claim(claim_for(bound.offer))+b'\n'); self.host.tick(.1)

    def responder(self, client, mode='ok'):
        records = []; stop = threading.Event()
        self.receipt_sent = threading.Event()
        client.settimeout(.1)
        def run():
            data = b''
            while not stop.is_set():
                try: block = client.recv(8192)
                except socket.timeout: continue
                except OSError: break
                if not block: break
                data += block
                while b'\n' in data:
                    raw, data = data.split(b'\n', 1); item = json.loads(raw)
                    if item['kind'] == 'accepted': continue
                    records.append(item)
                    if mode == 'timeout': continue
                    if mode == 'disconnect': client.shutdown(socket.SHUT_RDWR); return
                    answer = dict(item, kind='participant_receipt', status='confirmed')
                    if mode == 'wrong_id': answer['request_id'] += 1
                    if mode == 'bool_id': answer['request_id'] = True
                    if mode == 'wrong_epoch': answer['epoch'] = 'b'*32
                    payload = json.dumps(answer, separators=(',', ':')).encode()+b'\n'
                    if mode == 'duplicate': payload += payload
                    try:
                        client.sendall(payload[:8]); client.sendall(payload[8:])
                        if mode == 'fin_after': client.shutdown(socket.SHUT_WR)
                        self.receipt_sent.set()
                    except OSError: return
        thread = threading.Thread(target=run); thread.start()
        def finish():
            stop.set(); thread.join(2)
            self.assertFalse(thread.is_alive())
        self.addCleanup(finish)
        return records

    def test_pause_resume_and_socket_handle_binding(self):
        client = self.connect(); self.offer_and_claim(client)
        records = self.responder(client)
        self.host.tick(.1)
        self.assertEqual(self.world.session.state, 'running')
        second = self.connect()  # a join requires pausing the existing client
        self.host.tick(.1)
        self.assertEqual(self.world.session.state, 'saving')
        self.assertEqual([r['operation'] for r in records], ['resume','pause'])
        self.assertEqual([r['request_id'] for r in records], [1,2])
        self.assertEqual(self.engine.calls, ['pause','save','resume','pause'])
        second.close()

    def test_wrong_receipt_timeout_and_disconnect_fault_without_retry(self):
        # Each failure uses a fresh, separate host; unittest subtests cannot
        # share one after an intentionally indeterminate operation.
        for mode in ('wrong_id', 'bool_id', 'wrong_epoch', 'duplicate', 'timeout', 'disconnect', 'fin_after'):
            with self.subTest(mode=mode):
                with ParticipantCase(mode) as case:
                    case.exercise()

    def test_partial_two_client_resume_faults_and_repauses_server(self):
        alice = self.connect(); bob = self.connect()
        self.offer_and_claim(alice); a_records = self.responder(alice)
        self.offer_and_claim(bob); b_records = self.responder(bob, 'wrong_id')
        with self.assertRaises(ValueError): self.host.tick(.1)
        self.assertEqual([r['operation'] for r in a_records], ['resume'])
        self.assertEqual([r['operation'] for r in b_records], ['resume'])
        self.assertEqual(self.engine.calls, ['pause','save','resume','pause'])
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertTrue(self.host._failed); self.assertTrue(self.participants._failed)

    def test_adapter_refuses_use_outside_active_host_operation(self):
        with self.assertRaises(ValueError): self.participants.resume((1,))
        self.assertFalse(self.participants._failed)

    def test_expired_select_never_sends_command(self):
        client = self.connect(); conn = next(iter(self.control._peers)); peer = self.control._peers[conn]
        with patch('authority.experimental_tcp_participants.time.monotonic', side_effect=(0, 2)), \
             patch('authority.experimental_tcp_participants.select.select', return_value=([], [conn], [])):
            with self.assertRaises(TimeoutError):
                self.participants._exchange(conn, peer, [], b'command\n', {}, 1)
        client.settimeout(.02)
        with self.assertRaises(socket.timeout): client.recv(1)


class ParticipantCase:
    """Reuse fixture lifecycle for one deliberate failure without re-running tests."""
    def __init__(self, mode): self.mode = mode; self.case = ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
    def __enter__(self): self.case.setUp(); return self
    def __exit__(self, *args): self.case.doCleanups()
    def exercise(self):
        c = self.case; client = c.connect(); c.offer_and_claim(client)
        records = c.responder(client, self.mode)
        original = c.participants._quiet
        def after_fin(peers, deadline):
            c.assertTrue(c.receipt_sent.wait(.2))
            return original(peers, deadline)
        if self.mode == 'fin_after':
            with patch.object(c.participants, '_quiet', side_effect=after_fin):
                with c.assertRaises((ValueError, TimeoutError, RuntimeError)): c.host.tick(.1)
        else:
            with c.assertRaises((ValueError, TimeoutError, RuntimeError)): c.host.tick(.1)
        c.assertTrue(c.participants._failed); c.assertTrue(c.host._failed)
        c.assertEqual(c.world.session.state, 'faulted')
        c.assertEqual(c.engine.calls, ['pause','save','resume','pause'])
        c.assertEqual(len(records), 1)
        with c.assertRaises(RuntimeError): c.host.tick()


if __name__ == '__main__': unittest.main()
