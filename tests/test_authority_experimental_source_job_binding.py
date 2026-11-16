"""Local HELLO/BOUND/ATTACHED and peer fencing; no X4 process is started."""
from pathlib import Path
import socket
import sys
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_source_job_binding import ExperimentalSourceJobBinding
L,A,E,G=('a'*32,'b'*32,'c'*32,'d'*32)
HELLO=f'S|{L}|{A}|HELLO|{E}|{G}'.encode()
BOUND=f'P|{L}|{A}|BOUND|{E}|{G}'.encode()
ATTACHED=f'S|{L}|{A}|ATTACHED|{E}|{G}'.encode()

class Binding(unittest.TestCase):
    def make(self,*,validator=None,guard=lambda:True,timeout=.5):
        p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.bind(('127.0.0.1',0))
        x=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);x.bind(('127.0.0.1',0));x.connect(p.getsockname());x.settimeout(1)
        self.addCleanup(p.close);self.addCleanup(x.close)
        b=ExperimentalSourceJobBinding(p,enabled=True,lease=L,attempt=A,epoch=E,generation=G,
            guard=guard,validate_peer=validator or (lambda peer:peer==x.getsockname()),timeout=timeout)
        return b,p,x
    def test_handshake_handoff_is_owned_and_irreversible(self):
        b,p,x=self.make();errors=[]
        def source():
            try:
                x.send(HELLO);self.assertEqual(x.recv(769),BOUND);x.send(ATTACHED)
            except BaseException as e:errors.append(e)
        t=threading.Thread(target=source);t.start();self.addCleanup(t.join,2)
        self.assertTrue(b.bind());self.assertIs(b.handoff(),p);self.assertEqual(b.state,'handed_off')
        with self.assertRaises(RuntimeError):b.handoff()
        with self.assertRaises(RuntimeError):b.bind()
        self.assertNotEqual(p.fileno(),-1);self.assertEqual(p.getpeername(),x.getsockname())
        t.join(2);self.assertEqual(errors,[])
    def test_foreign_hello_and_unconfirmed_peer_fail_before_bound(self):
        for wrong,validator in ((True,lambda _:True),(False,lambda _:False)):
            b,p,x=self.make(validator=validator)
            x.send(HELLO.replace(E.encode(),b'f'*32) if wrong else HELLO)
            with self.assertRaises((ValueError,RuntimeError)):b.bind()
            self.assertEqual(b.state,'failed');self.assertEqual(p.fileno(),-1)
    def test_invalid_attached_and_duplicate_hello_fault(self):
        for reply in (ATTACHED.replace(G.encode(),b'f'*32),HELLO):
            b,p,x=self.make()
            def source():x.send(HELLO);x.recv(769);x.send(reply)
            t=threading.Thread(target=source);t.start();self.addCleanup(t.join,2)
            with self.assertRaises(ValueError):b.bind()
            self.assertEqual(b.state,'failed');t.join(2)
    def test_timeout_and_duplicate_socket_owner_fail(self):
        b,p,x=self.make(timeout=.03)
        with self.assertRaises(ValueError):
            ExperimentalSourceJobBinding(p,enabled=True,lease=L,attempt=A,epoch=E,generation=G,
                guard=lambda:True,validate_peer=lambda _:True,timeout=.1)
        with self.assertRaises(RuntimeError):b.bind()
        self.assertEqual(b.state,'failed')
    def test_lost_guard_and_reentrant_peer_callback_fault(self):
        b,p,x=self.make(guard=lambda:False);x.send(HELLO)
        with self.assertRaises(RuntimeError):b.bind()
        self.assertEqual(b.state,'failed')
        ref={}
        def validator(_):
            try:ref['b'].handoff()
            except RuntimeError:pass
            return True
        b,p,x=self.make(validator=validator);ref['b']=b;x.send(HELLO)
        with self.assertRaises(RuntimeError):b.bind()
        self.assertEqual(b.state,'failed')
