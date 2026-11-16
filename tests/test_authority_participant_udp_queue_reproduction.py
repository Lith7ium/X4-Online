"""Exercise participant HELLO queue pressure using only local UDP sockets.

The artificial barrier makes the response arrive before request() can read;
this demonstrates a possible interleaving, not its frequency in native X4.
"""
from pathlib import Path
import os
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.local_participant_control import LocalParticipantControl


def socket_drop_count(sock):
    inode = str(os.fstat(sock.fileno()).st_ino)
    for line in Path('/proc/net/udp').read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 13 and fields[9] == inode:
            return int(fields[12])
    raise AssertionError('owned UDP socket absent from /proc/net/udp')


class HoldAfterCommand:
    """Delay the controller's first read until the peer has sent its receipt."""
    def __init__(self, sock, receipt_sent):
        self.sock = sock
        self.receipt_sent = receipt_sent

    def sendto(self, payload, address):
        sent = self.sock.sendto(payload, address)
        if not self.receipt_sent.wait(2):
            raise TimeoutError('test peer did not send its receipt')
        return sent

    def recvfrom(self, size):
        return self.sock.recvfrom(size)

    def gettimeout(self):
        return self.sock.gettimeout()

    def settimeout(self, value):
        self.sock.settimeout(value)

    def setblocking(self, value):
        self.sock.setblocking(value)

    def close(self):
        self.sock.close()


@unittest.skipUnless(sys.platform == 'linux' and Path('/proc/net/udp').is_file(),
                     'requires Linux per-socket UDP drop counters')
class ParticipantQueueReproduction(unittest.TestCase):
    def run_case(self, fill_queue):
        controller = LocalParticipantControl(enabled=True, timeout=0.2)
        self.addCleanup(controller.close)
        receiver = controller.sock
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        receiver.settimeout(0.02)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(peer.close)
        peer.bind(('127.0.0.1', 0))
        peer.settimeout(2)
        epoch = 'b' * 32
        hello = f'HELLO|{controller.lease}|{epoch}'.encode('ascii')
        peer.sendto(hello, receiver.getsockname())
        controller.enroll(epoch, time.monotonic() + 1)

        if fill_queue:
            for _ in range(400):
                peer.sendto(hello, receiver.getsockname())
        receipt_sent = threading.Event()
        observed = {}

        def answer_command():
            try:
                payload, address = peer.recvfrom(769)
                expected = f'CMD|{controller.lease}|{epoch}|1|pause'.encode('ascii')
                if payload != expected:
                    raise AssertionError('unexpected participant command')
                observed['drops_before'] = socket_drop_count(receiver)
                receipt = f'RECEIPT|{controller.lease}|{epoch}|1|pause|confirmed'.encode('ascii')
                peer.sendto(receipt, address)
                observed['drops_after'] = socket_drop_count(receiver)
            except BaseException as error:
                observed['error'] = error
            finally:
                receipt_sent.set()

        worker = threading.Thread(target=answer_command)
        worker.start()
        self.addCleanup(worker.join, 3)
        controller.sock = HoldAfterCommand(receiver, receipt_sent)
        # The wrapper only delays the receive; the owned real socket is closed separately.
        self.addCleanup(receiver.close)
        controller.request('pause')
        self.assertFalse(controller.fault)
        self.assertEqual(receiver.gettimeout(), 0.02)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        if 'error' in observed:
            raise observed['error']
        if fill_queue:
            self.assertGreater(observed['drops_before'], 0, 'fixture did not fill the receive queue')
        self.assertEqual(observed['drops_after'], observed['drops_before'])
        # Cleanup through the actual owned socket rather than the test wrapper.
        controller.sock = receiver

    def test_empty_queue_accepts_receipt(self):
        self.run_case(fill_queue=False)

    def test_full_hello_queue_drains_before_correlated_receipt(self):
        self.run_case(fill_queue=True)

    def test_stale_or_malformed_packet_fences_before_command(self):
        for payload in (b'RECEIPT|stale', b'', b'x' * 900):
            with self.subTest(payload=payload[:20]):
                controller = LocalParticipantControl(enabled=True, timeout=0.2)
                peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    peer.bind(('127.0.0.1', 0))
                    peer.settimeout(0.05)
                    controller.epoch = 'a' * 32
                    controller.peer = peer.getsockname()
                    controller.sock.settimeout(0.13)
                    peer.sendto(payload, controller.sock.getsockname())
                    with self.assertRaisesRegex(RuntimeError, 'before command'):
                        controller.request('pause')
                    self.assertTrue(controller.fault)
                    self.assertEqual(controller.sock.gettimeout(), 0.13)
                    with self.assertRaises(socket.timeout):
                        peer.recvfrom(769)
                    with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                        controller.request('pause')
                finally:
                    controller.close()
                    peer.close()

    def test_receive_queue_drain_is_bounded_and_restores_timeout(self):
        controller = LocalParticipantControl(enabled=True, timeout=0.2)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            peer.bind(('127.0.0.1', 0))
            peer.settimeout(0.05)
            controller.epoch = 'a' * 32
            controller.peer = peer.getsockname()
            controller.sock.settimeout(0.13)
            hello = f'HELLO|{controller.lease}|{controller.epoch}'.encode('ascii')
            for _ in range(8):
                peer.sendto(hello, controller.sock.getsockname())
            with patch('authority.local_participant_control._MAX_QUEUED_PACKETS', 4):
                with self.assertRaisesRegex(RuntimeError, 'did not drain'):
                    controller.request('pause')
            self.assertTrue(controller.fault)
            self.assertEqual(controller.sock.gettimeout(), 0.13)
            with self.assertRaises(socket.timeout):
                peer.recvfrom(769)
        finally:
            controller.close()
            peer.close()

    def test_expired_deadline_never_dispatches_after_or_during_drain(self):
        for queue_hello in (False, True):
            with self.subTest(queue_hello=queue_hello):
                controller = LocalParticipantControl(enabled=True, timeout=0.2)
                peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    peer.bind(('127.0.0.1', 0))
                    peer.settimeout(0.05)
                    controller.epoch = 'a' * 32
                    controller.peer = peer.getsockname()
                    controller.sock.settimeout(0.13)
                    if queue_hello:
                        hello = f'HELLO|{controller.lease}|{controller.epoch}'.encode('ascii')
                        peer.sendto(hello, controller.sock.getsockname())
                    # Deadline is 10.2: expire at the next drain iteration
                    # when queued, or at the pre-send check when empty.
                    with patch('authority.local_participant_control.time.monotonic',
                               side_effect=(10.0, 10.0, 10.3)):
                        with self.assertRaisesRegex(TimeoutError, 'before command'):
                            controller.request('pause')
                    self.assertTrue(controller.fault)
                    self.assertEqual(controller.sock.gettimeout(), 0.13)
                    with self.assertRaises(socket.timeout):
                        peer.recvfrom(769)
                finally:
                    controller.close()
                    peer.close()

    def test_receipt_read_after_deadline_stays_indeterminate(self):
        controller = LocalParticipantControl(enabled=True, timeout=0.2)
        receiver = controller.sock
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sent = threading.Event()
        errors = []
        peer.bind(('127.0.0.1', 0))
        peer.settimeout(2)
        controller.epoch = 'a' * 32
        controller.peer = peer.getsockname()

        def answer_command():
            try:
                command, address = peer.recvfrom(769)
                peer.sendto(b'RECEIPT|' + command.split(b'|', 1)[1] + b'|confirmed', address)
            except BaseException as error:
                errors.append(error)
            finally:
                sent.set()

        worker = threading.Thread(target=answer_command)
        worker.start()
        controller.sock = HoldAfterCommand(receiver, sent)
        try:
            with patch('authority.local_participant_control.time.monotonic',
                       side_effect=(10.0, 10.0, 10.0, 10.0, 10.3)):
                with self.assertRaisesRegex(TimeoutError, 'state indeterminate'):
                    controller.request('pause')
            self.assertTrue(controller.fault)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
        finally:
            controller.close()
            peer.close()
            worker.join(3)


if __name__ == '__main__':
    unittest.main()
