"""Synthetic loopback checks for the diagnostic participant adapter, not X4."""
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/dev'))
import authority_two_x4_resume_live as experiment


class ParticipantTest(unittest.TestCase):
    def setUp(self):
        self.participant = experiment.Participant()
        self.peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.peer.bind(('127.0.0.1', 0)); self.peer.settimeout(2)
        self.participant.epoch = 'a'*32
        self.participant.peer = self.peer.getsockname()
        self.participant.handle = 4

    def tearDown(self):
        self.peer.close(); self.participant.sock.close()

    def test_native_receipt_envelope_and_participant_set(self):
        def synthetic_peer():
            data, address = self.peer.recvfrom(769)
            command = data.decode('ascii').split('|')
            self.assertEqual(command[-1], 'resume')
            self.peer.sendto(('RECEIPT|'+'|'.join(command[1:])+'|confirmed').encode(), address)
        thread = threading.Thread(target=synthetic_peer)
        thread.start()
        self.assertTrue(self.participant.resume((4,)))
        thread.join(3); self.assertFalse(thread.is_alive())
        with self.assertRaises(ValueError): self.participant.pause((4, 5))

    def test_unexpected_receipt_fences_later_commands(self):
        def synthetic_peer():
            _, address = self.peer.recvfrom(769)
            self.peer.sendto(b'bad', address)
        thread = threading.Thread(target=synthetic_peer)
        thread.start()
        with self.assertRaises(RuntimeError): self.participant.pause((4,))
        thread.join(3)
        with self.assertRaises(RuntimeError): self.participant.resume((4,))

    def test_existing_output_is_never_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'client/case/extensions/x4_lan_lab/ui/config.lua'
            path.parent.mkdir(parents=True)
            path.write_text('original')
            with self.assertRaises(ValueError): experiment.run(SimpleNamespace(out=Path(directory)))
            self.assertEqual(path.read_text(), 'original')

    def test_redaction_rejects_replaced_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.lua'
            path.write_text('original')
            self.participant.config = path
            self.participant.config_identity = (0, 0)
            with self.assertRaises(ValueError): self.participant.redact()
            self.assertEqual(path.read_text(), 'original')

if __name__ == '__main__': unittest.main()
