"""Owned file-service shutdown with real loopback sockets; no X4."""
from pathlib import Path
import os
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from lockstep.launcher.joinfiles import FileService, request_line
from authority_two_x4_live import close_owned_file_service
from authority_recovered_loopback_server import finish_recovery_lock


class FileServiceCleanup(unittest.TestCase):
    def setUp(self):
        self.service = FileService('a' * 32, slots=(1,)).start()
        self.addCleanup(self.cleanup_if_needed)

    def cleanup_if_needed(self):
        if not self.service._closing:
            close_owned_file_service(self.service)

    def connect(self):
        client = socket.create_connection(('127.0.0.1', self.service.port), timeout=2)
        client.settimeout(2)
        self.addCleanup(client.close)
        return client

    def wait_for(self, predicate):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.service.lock:
                if predicate():
                    return
            time.sleep(.005)
        self.fail('service did not enter the expected state')

    def test_idle_unauthenticated_connection_is_closed_and_handler_reaped(self):
        client = self.connect()
        self.wait_for(lambda: len(self.service._handlers) == 1 and self.service.active == 1)
        close_owned_file_service(self.service)
        self.assertEqual(client.recv(1), b'')
        self.assertFalse(self.service.thread.is_alive())
        with self.service.lock:
            self.assertFalse(self.service._handlers)
            self.assertEqual(self.service.active, 0)
        with self.assertRaisesRegex(RuntimeError, 'closing'):
            self.service.offer('j1.xml.gz', '/does/not/exist')

    def test_active_authenticated_transfer_is_interrupted_before_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save'
            with path.open('wb') as stream:
                stream.truncate(16 * 1024 * 1024)
            self.service.offer('j1.xml.gz', path)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            client.settimeout(2)
            client.connect(('127.0.0.1', self.service.port))
            self.addCleanup(client.close)
            client.sendall(request_line('a' * 32, 1, 'j1.xml.gz'))
            self.wait_for(lambda: len(self.service._transfers) == 1)
            close_owned_file_service(self.service)
            with self.service.lock:
                self.assertFalse(self.service._handlers)
                self.assertFalse(self.service._transfers)
                self.assertFalse(self.service.offered)
                self.assertEqual(self.service.active, 0)
            self.assertFalse(self.service.thread.is_alive())

    def test_accept_registered_before_worker_spawn_is_fenced(self):
        entered, release = threading.Event(), threading.Event()
        original = socketserver.ThreadingMixIn.process_request
        def delayed_start(server, request, address):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release handler spawn')
            return original(server, request, address)
        errors = []
        def close():
            try: close_owned_file_service(self.service)
            except BaseException as error: errors.append(error)
        with patch.object(socketserver.ThreadingMixIn, 'process_request', delayed_start):
            client = self.connect()
            self.assertTrue(entered.wait(2))
            closer = threading.Thread(target=close)
            closer.start()
            try:
                self.wait_for(lambda: self.service._closing)
            finally:
                release.set()
            closer.join(3)
        self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(client.recv(1), b'')
        with self.service.lock:
            self.assertFalse(self.service._handlers)
            self.assertEqual(self.service.active, 0)

    def test_stalled_handler_makes_cleanup_unconfirmed_with_deadline(self):
        entered, release = threading.Event(), threading.Event()
        original = socketserver.ThreadingMixIn.process_request_thread
        def stalled_handler(server, request, address):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release handler')
            return original(server, request, address)
        with patch.object(socketserver.ThreadingMixIn, 'process_request_thread', stalled_handler):
            self.connect()
            self.assertTrue(entered.wait(2))
            try:
                started = time.monotonic()
                with self.assertRaisesRegex(TimeoutError, 'handlers or offers remain'):
                    self.service.close_and_drain(timeout=.5)
                self.assertLess(time.monotonic() - started, 1.5)
                self.assertEqual(self.service.server.fileno(), -1)
            finally:
                release.set()
            self.wait_for(lambda: not self.service._handlers)
            self.service.thread.join(2)
            self.assertFalse(self.service.thread.is_alive())

    def test_inflight_offer_prevents_cleanup_success_and_cannot_publish_after_close(self):
        entered, release = threading.Event(), threading.Event()
        offer_errors = []
        def slow_digest(_path):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release digest')
            return 'b' * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save'
            path.write_bytes(b'checkpoint')
            def offer():
                try: self.service.offer('j1.xml.gz', path)
                except BaseException as error: offer_errors.append(error)
            with patch('lockstep.launcher.joinfiles.sha256_file', slow_digest):
                worker = threading.Thread(target=offer)
                worker.start()
                self.assertTrue(entered.wait(2))
                try:
                    with self.assertRaisesRegex(TimeoutError, 'handlers or offers remain'):
                        self.service.close_and_drain(timeout=.5)
                    with self.service.lock:
                        self.assertEqual(self.service._offers_inflight, 1)
                        self.assertFalse(self.service.offered)
                finally:
                    release.set()
                    worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(offer_errors), 1)
            self.assertIsInstance(offer_errors[0], RuntimeError)
            with self.service.lock:
                self.assertEqual(self.service._offers_inflight, 0)
                self.assertFalse(self.service.offered)

    def test_stalled_shutdown_is_bounded_and_listener_is_closed(self):
        entered, release = threading.Event(), threading.Event()
        original = self.service.server.shutdown
        def stalled_shutdown():
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release shutdown')
            original()
        with patch.object(self.service.server, 'shutdown', stalled_shutdown):
            try:
                with tempfile.TemporaryDirectory() as directory:
                    lock = Path(directory) / 'owned-lock'
                    lock.touch()
                    lock_fd = os.open(lock, os.O_RDONLY)
                    errors = []
                    started = time.monotonic()
                    with self.assertRaisesRegex(TimeoutError, 'shutdown unconfirmed'):
                        self.service.close_and_drain(timeout=.05)
                    finish_recovery_lock([(lock_fd, object())], [], False, errors)
                    self.assertTrue(lock.exists())
                    self.assertTrue(any('lock retained' in error for error in errors))
                    with self.assertRaises(OSError): os.fstat(lock_fd)
                    self.assertLess(time.monotonic() - started, 1)
                    self.assertTrue(entered.is_set())
                    self.assertEqual(self.service.server.fileno(), -1)
            finally:
                release.set()
            self.service.thread.join(2)
            self.assertFalse(self.service.thread.is_alive())

    def test_synchronous_close_overrunning_deadline_is_not_reported_as_success(self):
        unstarted = FileService('b' * 32, slots=(1,))
        with patch('lockstep.launcher.joinfiles.time.monotonic', side_effect=(10.0, 12.1)):
            with self.assertRaisesRegex(TimeoutError, 'cleanup deadline'):
                unstarted.close_and_drain(timeout=2)
        self.assertEqual(unstarted.server.fileno(), -1)


if __name__ == '__main__':
    unittest.main()
