"""Loopback TCP and fake local controllers; no X4, Windows, or WAN."""
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
import test_authority_experimental_tcp_participants as host_fixture


class Controller:
    def __init__(self): self.calls = []; self.response = True
    def pause(self, handles): self.calls.append(('pause', handles)); return self.response
    def resume(self, handles): self.calls.append(('resume', handles)); return self.response


def command(number=1, operation='pause', epoch='a'*32, handle=1):
    return {'version':1, 'kind':'participant_command', 'epoch':epoch,
            'connection_handle':handle, 'request_id':number, 'operation':operation}


def frame(value): return json.dumps(value, separators=(',', ':')).encode()+b'\n'


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1',0)); self.listener.listen(1); self.addCleanup(self.listener.close)
        conn = socket.create_connection(self.listener.getsockname(), timeout=1)
        self.server, _ = self.listener.accept(); self.server.settimeout(1); self.addCleanup(self.server.close)
        self.controller = Controller()
        self.client = ExperimentalTCPParticipantClient(conn, self.controller, enabled=True, epoch='a'*32, handle=1, timeout=.2)
        self.addCleanup(lambda: self.client.close() if not (self.client._closed or self.client._failed) else None)

    def exchange(self, value):
        data = frame(value); self.server.sendall(data[:7]); self.client.poll(.1)
        self.server.sendall(data[7:]); self.client.poll(.1); self.client.poll(.1)
        return json.loads(self.server.recv(8192))

    def test_fragmented_commands_have_exact_receipts_and_increasing_ids(self):
        for number, op in ((4,'pause'),(9,'resume')):
            expected = dict(command(number,op), kind='participant_receipt', status='confirmed')
            self.assertEqual(self.exchange(command(number,op)), expected)
        self.assertEqual(self.controller.calls, [('pause',(1,)),('resume',(1,))])

    def test_stale_request_faults_without_second_dispatch(self):
        self.exchange(command())
        self.server.sendall(frame(command()))
        with self.assertRaises(ValueError): self.client.poll(.1)
        self.assertEqual(self.controller.calls, [('pause',(1,))])
        self.assertEqual(self.server.recv(1), b'')

    def test_controller_must_confirm(self):
        self.controller.response = False
        self.server.sendall(frame(command()))
        with self.assertRaises(RuntimeError): self.client.poll(.1)
        self.assertEqual(self.server.recv(1), b'')

    def test_reentrant_controller_fails_even_if_it_catches_error(self):
        def nested(_):
            try: self.client.poll()
            except RuntimeError: pass
            return True
        self.controller.pause = nested
        self.server.sendall(frame(command()))
        with self.assertRaises(RuntimeError): self.client.poll(.1)
        self.assertEqual(self.server.recv(1), b'')

    def test_late_controller_receipt_is_never_emitted(self):
        def slow(_): time.sleep(.22); return True
        self.controller.pause = slow
        self.server.sendall(frame(command()))
        with self.assertRaises(TimeoutError): self.client.poll(.1)
        self.assertEqual(self.server.recv(1), b'')

    def test_foreign_epoch_handle_and_duplicate_json_refused(self):
        for bad in (command(epoch='b'*32), command(handle=2), command(number=True),
                    b'{"version":1,"version":1}\n'):
            with self.subTest(bad=bad):
                fixture = ClientTest('test_stale_request_faults_without_second_dispatch'); fixture.setUp()
                try:
                    fixture.server.sendall(bad if isinstance(bad,bytes) else frame(bad))
                    with fixture.assertRaises(ValueError): fixture.client.poll(.1)
                    fixture.assertEqual(fixture.controller.calls, [])
                    fixture.assertEqual(fixture.server.recv(1), b'')
                finally: fixture.doCleanups()

    def test_peer_eof_before_controller_dispatch_refused(self):
        self.server.sendall(frame(command())); self.server.shutdown(socket.SHUT_WR)
        with self.assertRaises(RuntimeError): self.client.poll(.1)
        self.assertEqual(self.controller.calls, [])


class PairedAdapterTest(unittest.TestCase):
    def test_host_participant_and_pumpable_client_exchange(self):
        fixture = host_fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation'); fixture.setUp()
        try:
            conn = fixture.connect(); fixture.offer_and_claim(conn)
            controller = Controller(); ready = threading.Event(); stop = threading.Event(); errors = []
            def client_loop():
                try:
                    conn.settimeout(1); ack = b''
                    while not ack.endswith(b'\n'): ack += conn.recv(1)
                    assert json.loads(ack)['kind'] == 'accepted'
                    adapter = ExperimentalTCPParticipantClient(conn, controller, enabled=True,
                                                               epoch='a'*32, handle=1, timeout=.5)
                    ready.set()
                    while not stop.is_set(): adapter.poll(.05)
                    if not adapter._failed: adapter.close()
                except BaseException as error: errors.append(error); ready.set()
            worker = threading.Thread(target=client_loop); worker.start()
            try:
                fixture.host.tick(.1)  # flush ACK, synchronously request resume
                self.assertTrue(ready.wait(1))
                second = fixture.connect()
                fixture.host.tick(.1)  # joining schedules pause of first client
                self.assertEqual(controller.calls, [('resume',(1,)),('pause',(1,))])
                self.assertEqual(fixture.world.session.state, 'saving')
                second.close()
            finally:
                stop.set(); worker.join(2)
            self.assertFalse(worker.is_alive()); self.assertEqual(errors, [])
        finally: fixture.doCleanups()


if __name__ == '__main__': unittest.main()
