"""Actual loopback UDP receive-queue tests; no X4 process."""
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.local_control_bridge import LocalControlBridge


class QueuedHelloTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.profile=Path(self.temp.name)/'45841';(self.profile/'save').mkdir(parents=True)
        self.recv=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.recv.bind(('127.0.0.1',0))
        self.recv.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096);self.addCleanup(self.recv.close)
        self.peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.peer.bind(('127.0.0.1',0))
        self.peer.settimeout(1);self.addCleanup(self.peer.close)
        self.lease='a'*32;self.epoch='b'*32
        self.hello=f'HELLO|{self.lease}|{self.epoch}'.encode()
        self.verify=f'VERIFY|{self.lease}|{self.epoch}|1'
        self.verified=f'VERIFIED|{self.lease}|{self.epoch}|1'

    def adapter(self):
        return LocalControlBridge(enabled=True,sock=self.recv,peer=self.peer.getsockname(),
            lease=self.lease,world_epoch=self.epoch,profile=self.profile,store=object(),
            verify_checkpoint=lambda *_:None,timeout=1)

    def test_full_receive_queue_drains_before_correlated_response(self):
        for old_timeout in (None,0.0,0.2):
            with self.subTest(old_timeout=old_timeout):
                self.recv.settimeout(old_timeout)
                for _ in range(400): self.peer.sendto(self.hello,self.recv.getsockname())
                errors=[]
                def answer():
                    try:
                        data,addr=self.peer.recvfrom(769)
                        if data != self.verify.encode(): raise AssertionError('unexpected command')
                        self.peer.sendto(self.verified.encode(),addr)
                    except BaseException as error: errors.append(error)
                worker=threading.Thread(target=answer);worker.start()
                self.adapter()._exchange(self.verify,self.verified)
                worker.join(2);self.assertFalse(worker.is_alive());self.assertFalse(errors)
                self.assertEqual(self.recv.gettimeout(),old_timeout)

    def test_unexpected_peer_message_poisoned_without_sending(self):
        self.recv.settimeout(0.17)
        self.peer.sendto(b'VERIFIED|stale',self.recv.getsockname())
        adapter=self.adapter()
        with self.assertRaisesRegex(RuntimeError,'before command'): adapter._exchange(self.verify,self.verified)
        self.assertEqual(self.recv.gettimeout(),0.17)
        self.peer.setblocking(False)
        with self.assertRaises(BlockingIOError):self.peer.recvfrom(769)
        with self.assertRaisesRegex(RuntimeError,'fenced'):adapter._exchange(self.verify,self.verified)

    def test_receive_timeout_restores_original_socket_state_and_fences(self):
        self.recv.settimeout(0.17)
        adapter=self.adapter();adapter._timeout=0.05
        with self.assertRaises(TimeoutError):adapter._exchange(self.verify,self.verified)
        self.assertEqual(self.recv.gettimeout(),0.17)
        data,_=self.peer.recvfrom(769);self.assertEqual(data,self.verify.encode())
        with self.assertRaisesRegex(RuntimeError,'fenced'):adapter._exchange(self.verify,self.verified)

    def test_bounded_drain_fails_closed_and_restores_timeout(self):
        self.recv.settimeout(0.23)
        for _ in range(8): self.peer.sendto(self.hello,self.recv.getsockname())
        adapter=self.adapter()
        with patch('authority.local_control_bridge._MAX_QUEUED_PACKETS',4):
            with self.assertRaisesRegex(RuntimeError,'did not drain'):adapter._exchange(self.verify,self.verified)
        self.assertEqual(self.recv.gettimeout(),0.23)
        self.peer.setblocking(False)
        with self.assertRaises(BlockingIOError):self.peer.recvfrom(769)
        with self.assertRaisesRegex(RuntimeError,'fenced'):adapter._exchange(self.verify,self.verified)

if __name__=='__main__':unittest.main()
