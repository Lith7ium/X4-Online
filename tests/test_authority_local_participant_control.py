"""Focused transport checks; these peers do not represent X4 or real clients."""
import socket
import threading
import time
import unittest

from authority.local_participant_control import LocalParticipantControl, LocalParticipantGroup


class LocalParticipantControlTest(unittest.TestCase):
    def test_requires_opt_in(self):
        with self.assertRaises(ValueError):
            LocalParticipantControl(enabled=False)

    def test_enroll_and_pause_through_loopback(self):
        controller = LocalParticipantControl(enabled=True, timeout=1)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(('127.0.0.1', 0))
        peer.settimeout(2)
        try:
            epoch = 'a' * 32
            peer.sendto(f'HELLO|{controller.lease}|{epoch}'.encode(), controller.sock.getsockname())
            controller.enroll(epoch, time.monotonic() + 1)
            controller.handle = 7
            def respond():
                command, address = peer.recvfrom(769)
                peer.sendto(b'RECEIPT|' + command.split(b'|', 1)[1] + b'|confirmed', address)
            thread = threading.Thread(target=respond)
            thread.start()
            self.assertTrue(controller.pause((7,)))
            thread.join(2)
            self.assertFalse(thread.is_alive())
            with self.assertRaises(ValueError):
                controller.resume((8,))
        finally:
            controller.close()
            peer.close()

    def test_timeout_fences_later_commands(self):
        controller = LocalParticipantControl(enabled=True, timeout=.01)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(('127.0.0.1', 0))
        try:
            controller.epoch = 'b' * 32
            controller.peer = peer.getsockname()
            controller.handle = 1
            with self.assertRaises(TimeoutError):
                controller.pause((1,))
            with self.assertRaises(RuntimeError):
                controller.resume((1,))
        finally:
            controller.close()
            peer.close()


class LocalParticipantGroupTest(unittest.TestCase):
    def setUp(self):
        self.group = LocalParticipantGroup(enabled=True, world_epoch='c' * 32)
        self.controllers = []
        self.peers = []
        for handle in (1, 2):
            controller = LocalParticipantControl(enabled=True, timeout=1)
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer.bind(('127.0.0.1', 0))
            peer.settimeout(.2)
            controller.epoch = 'c' * 32
            controller.peer = peer.getsockname()
            controller.handle = handle
            self.controllers.append(controller)
            self.peers.append(peer)
            self.group.attach(handle, controller)

    def tearDown(self):
        for controller in self.controllers:
            controller.close()
        for peer in self.peers:
            peer.close()

    @staticmethod
    def respond(peer, success=True):
        data, address = peer.recvfrom(769)
        reply = b'RECEIPT|' + data.split(b'|', 1)[1] + b'|confirmed' if success else b'bad receipt'
        peer.sendto(reply, address)

    def test_two_participants_confirm(self):
        threads = [threading.Thread(target=self.respond, args=(peer,)) for peer in self.peers]
        for thread in threads:
            thread.start()
        self.assertTrue(self.group.pause((1, 2)))
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_missing_participant_sends_nothing(self):
        with self.assertRaises(ValueError):
            self.group.resume((1, 3))
        for peer in self.peers:
            with self.assertRaises(socket.timeout):
                peer.recvfrom(769)

    def test_unavailable_participant_sends_nothing(self):
        self.controllers[1].fault = True
        with self.assertRaises(ValueError):
            self.group.pause((1, 2))
        for peer in self.peers:
            with self.assertRaises(socket.timeout):
                peer.recvfrom(769)

    def test_rejects_foreign_epoch_on_attach(self):
        self.group.detach(2)
        self.controllers[1].epoch = 'd' * 32
        with self.assertRaises(ValueError):
            self.group.attach(2, self.controllers[1])

    def test_changed_epoch_sends_nothing(self):
        self.controllers[1].epoch = 'd' * 32
        with self.assertRaises(ValueError):
            self.group.pause((1, 2))
        for peer in self.peers:
            with self.assertRaises(socket.timeout):
                peer.recvfrom(769)

    def test_invalid_epoch_rejected(self):
        with self.assertRaises(ValueError):
            LocalParticipantGroup(enabled=True, world_epoch='invalid')

    def test_partial_failure_faults_group(self):
        threads = [threading.Thread(target=self.respond, args=(self.peers[0],)),
                   threading.Thread(target=self.respond, args=(self.peers[1], False))]
        for thread in threads:
            thread.start()
        with self.assertRaises(RuntimeError):
            self.group.resume((1, 2))
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        with self.assertRaises(RuntimeError):
            self.group.pause((1, 2))
