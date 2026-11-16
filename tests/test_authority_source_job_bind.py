"""Concrete /proc UDP peer binding against this test process; no X4 starts."""
import os
from pathlib import Path
import socket
import sys
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority_source_job_bind import bind_source
from authority_tcp_job_client_live import socket_owner
import authority_sector_read_live as base
L,A,E,G=('a'*32,'b'*32,'c'*32,'d'*32)
HELLO=f'S|{L}|{A}|HELLO|{E}|{G}'.encode();BOUND=f'P|{L}|{A}|BOUND|{E}|{G}'.encode()
ATTACHED=f'S|{L}|{A}|ATTACHED|{E}|{G}'.encode()

class Bind(unittest.TestCase):
    def test_pid_and_actual_udp_inode_must_match(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
        source=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source.bind(('127.0.0.1',0));source.connect(sock.getsockname());source.settimeout(1)
        self.addCleanup(sock.close);self.addCleanup(source.close)
        st=os.stat('/proc/self/exe');process={'pid':os.getpid(),'start_ticks':base.live.start_ticks(os.getpid()),'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        self.assertTrue(socket_owner(source.getsockname(),sock.getsockname(),process))
        errors=[]
        def sender():
            try:source.send(HELLO);self.assertEqual(source.recv(769),BOUND);source.send(ATTACHED)
            except BaseException as exc:errors.append(exc)
        t=threading.Thread(target=sender);t.start();self.addCleanup(t.join,2)
        result=bind_source(sock,process=process,lease=L,attempt=A,epoch=E,generation=G,guard=lambda:True,timeout=1)
        self.assertIs(result,sock);self.assertEqual(sock.getpeername(),source.getsockname());t.join(2);self.assertEqual(errors,[])
    def test_changed_process_start_is_refused(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));self.addCleanup(sock.close)
        st=os.stat('/proc/self/exe');process={'pid':os.getpid(),'start_ticks':base.live.start_ticks(os.getpid())+1,'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        with self.assertRaises(RuntimeError):bind_source(sock,process=process,lease=L,attempt=A,epoch=E,generation=G,guard=lambda:True,timeout=.1)
