"""The participant guard reports failures without logging handshake contents."""
import os
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_tcp_job_client_live as worker


def own_process_identity():
    proc = Path('/proc/self')
    image = (proc / 'exe').stat()
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': os.getpid(), 'start_ticks': int(fields[19]),
            'exe_dev': image.st_dev, 'exe_ino': image.st_ino}


class ParticipantHandshakeDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        if sys.platform != 'linux':
            self.skipTest('Linux process identity required')
        self.participant = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.jobs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control, self.parent = socket.socketpair()
        for sock in (self.participant, self.jobs, self.sender, self.control, self.parent):
            self.addCleanup(sock.close)
        self.participant.bind(('127.0.0.1', 0))
        self.jobs.bind(('127.0.0.1', 0))
        self.context = {'client_process': own_process_identity(), 'deadline': time.monotonic() + 10,
                        'epoch': 'a' * 32, 'job_epoch': 'b' * 32,
                        'participant_lease': 'c' * 32}

    def test_unexpected_packet_is_distinguished_without_logging_its_content(self):
        self.sender.sendto(b'private-unexpected-payload', self.participant.getsockname())
        with patch.object(worker, 'socket_owner') as owner:
            with self.assertRaisesRegex(RuntimeError, '^unexpected participant hello$'):
                worker.run(self.participant, self.jobs, self.control, self.context, None)
            owner.assert_not_called()

    def test_owner_failure_remains_fenced_with_static_reason(self):
        message = ('HELLO|' + self.context['participant_lease'] + '|' + self.context['epoch']).encode()
        self.sender.sendto(message, self.participant.getsockname())
        def reject(_peer, _destination, _process, *, diagnostic):
            diagnostic('competing IPv4 source port')
            return False
        with patch.object(worker, 'socket_owner', side_effect=reject):
            with self.assertRaisesRegex(RuntimeError, '^participant peer not owned by X4: competing IPv4 source port$'):
                worker.run(self.participant, self.jobs, self.control, self.context, None)


if __name__ == '__main__':
    unittest.main()
