"""Opt-in transfer pump is exercised over real loopback, with no game process."""
import hashlib
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lockstep.launcher import joinfiles


class TransferPumpTest(unittest.TestCase):
    def test_pump_runs_while_header_and_body_stall_and_during_hash(self):
        content = b'a' * (joinfiles.CHUNK + 40)
        digest = hashlib.sha256(content).hexdigest()
        listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1)
        self.addCleanup(listener.close)
        def serve():
            conn, _ = listener.accept()
            with conn:
                conn.recv(512)
                time.sleep(.13)
                conn.sendall(f'OK|{len(content)}|{digest}\n'.encode())
                conn.sendall(content[:10])
                time.sleep(.13)
                conn.sendall(content[10:])
        worker = threading.Thread(target=serve); worker.start()
        self.addCleanup(lambda: worker.join(2))
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save'
            joinfiles.fetch('127.0.0.1', listener.getsockname()[1], 'a'*32, 1,
                'j1.xml.gz', path, expect_sha=digest, expect_size=len(content),
                retries=0, deadline=time.monotonic()+3, timeout=1,
                pump=lambda: calls.append(time.monotonic()), pump_interval=.02)
            self.assertEqual(path.read_bytes(), content)
        worker.join(1)
        self.assertGreaterEqual(len(calls), 10)
        self.assertGreater(calls[-1] - calls[0], .2)

    def test_sleep_handles_pump_running_past_sleep_or_deadline(self):
        clock = [0.0]
        def slow_pump(): clock[0] += 2
        with patch.object(joinfiles.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(joinfiles.time, 'sleep') as sleep:
            joinfiles._pump_sleep(1, 5, slow_pump, .1)
            sleep.assert_not_called()
            clock[0] = 0
            with self.assertRaises(joinfiles.FetchDeadline):
                joinfiles._pump_sleep(1, 1, slow_pump, .1)

    def test_pump_failure_is_not_converted_to_a_retryable_transfer_error(self):
        listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1)
        self.addCleanup(listener.close)
        with tempfile.TemporaryDirectory() as directory:
            def fail(): raise OSError('control channel lost')
            with self.assertRaisesRegex(RuntimeError, 'transfer control pump failed'):
                joinfiles.fetch('127.0.0.1', listener.getsockname()[1], 'a'*32, 1,
                    'j1.xml.gz', Path(directory) / 'save', retries=2,
                    deadline=time.monotonic()+1, pump=fail)


if __name__ == '__main__': unittest.main()
