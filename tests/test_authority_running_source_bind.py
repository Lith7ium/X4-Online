"""Private running bind: real loopback/PID and sampled session fences."""
import os
from pathlib import Path
import socket
import sys
import threading
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_source_job_bind as bind
import authority_motion_ipc_supervisor as motion_bind
import authority_sector_read_live as base

L,A,E,G=('a'*32,'b'*32,'c'*32,'d'*32)

def context():
    st=os.stat('/proc/self/exe')
    identity={'pid':os.getpid(),'start_ticks':base.live.start_ticks(os.getpid()),'exe_dev':st.st_dev,'exe_ino':st.st_ino}
    session=types.SimpleNamespace(state='running',pending=None,players=((1,'p'),),ready_players=((1,'p'),))
    return identity,types.SimpleNamespace(session=session)

class RunningBind(unittest.TestCase):
    def test_actual_socket_and_process(self):
        if not sys.platform.startswith('linux'):self.skipTest('Linux /proc required')
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
        source=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source.bind(('127.0.0.1',0))
        source.connect(server.getsockname());source.settimeout(2)
        self.addCleanup(server.close);self.addCleanup(source.close)
        identity,world=context();errors=[]
        def worker():
            try:
                source.send(f'S|{L}|{A}|HELLO|{E}|{G}'.encode())
                if source.recv(769)!=f'P|{L}|{A}|BOUND|{E}|{G}'.encode():raise AssertionError('bad bound')
                source.send(f'S|{L}|{A}|ATTACHED|{E}|{G}'.encode())
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=worker);thread.start()
        try:
            self.assertIs(bind.bind_running_source(server,process=identity,lease=L,attempt=A,epoch=E,generation=G,
                world=world,client_guard=lambda:True,timeout=2),server)
        finally:thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(server.getpeername(),source.getsockname())

    def test_running_context_rejected_at_every_handoff_stage(self):
        for stage in ('before','during','after','client','pending','unready','pid'):
            with self.subTest(stage=stage):
                server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
                self.addCleanup(server.close)
                identity,world=context()
                if stage=='before':world.session.state='paused'
                if stage=='pending':world.session.pending='pause'
                if stage=='unready':world.session.ready_players=()
                if stage=='pid':identity['start_ticks']+=1
                class FakeBinding:
                    def __init__(self,sock,**kw):self.sock=sock;self.guard=kw['guard']
                    def bind(self):
                        if stage=='during':world.session.state='paused'
                        if not self.guard():raise RuntimeError('binding fence')
                    def handoff(self):
                        if stage=='after':world.session.state='paused'
                        return self.sock
                with patch.object(bind,'ExperimentalSourceJobBinding',FakeBinding):
                    with self.assertRaises((RuntimeError,ValueError)):
                        bind.bind_running_source(server,process=identity,lease=L,attempt=A,epoch=E,generation=G,
                            world=world,client_guard=lambda:stage!='client',timeout=2)
                self.assertEqual(server.fileno(),-1)

    def test_running_mode_limits_timeout_and_default_is_unchanged(self):
        from authority.experimental_source_job_binding import ExperimentalSourceJobBinding
        for mode,timeout in ((True,121),(False,301)):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
            self.addCleanup(sock.close)
            with self.assertRaises(ValueError):
                ExperimentalSourceJobBinding(sock,enabled=True,lease=L,attempt=A,epoch=E,generation=G,
                    guard=lambda:True,validate_peer=lambda _:True,timeout=timeout,running_diagnostic=mode)

    def test_motion_bind_and_later_operations_can_use_separate_timeouts(self):
        if not sys.platform.startswith('linux'): self.skipTest('Linux /proc required')
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        source = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0)); source.bind(('127.0.0.1', 0))
        source.connect(server.getsockname()); source.settimeout(2)
        self.addCleanup(server.close); self.addCleanup(source.close)
        identity, world = context()
        motion = types.SimpleNamespace(_delivery=types.SimpleNamespace(_host=types.SimpleNamespace(_world=world)))
        errors = []
        def worker():
            try:
                source.send(f'S|{L}|{A}|HELLO|{E}|{G}'.encode())
                if source.recv(769) != f'P|{L}|{A}|BOUND|{E}|{G}'.encode(): raise AssertionError('bad bound')
                source.send(f'S|{L}|{A}|ATTACHED|{E}|{G}'.encode())
            except BaseException as error: errors.append(error)
        thread = threading.Thread(target=worker); thread.start()
        try:
            with patch.object(motion_bind, 'ExperimentalSourceMotionIPC') as ipc:
                motion_bind.bind_running_source_motion(server, motion, process=identity, lease=L,
                    attempt=A, epoch=E, generation=G, world=world, client_guard=lambda: True,
                    select_recipients=lambda value, members: [], timeout=300, bind_timeout=120)
                self.assertEqual(ipc.call_args.kwargs['timeout'], 300)
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])

    def test_member_change_inside_guard_or_before_handoff_fails(self):
        for stage in ('guard','handoff'):
            with self.subTest(stage=stage):
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
                self.addCleanup(sock.close);identity,world=context()
                def switch():world.session.players=((2,'q'),);world.session.ready_players=((2,'q'),)
                def guard():
                    if stage=='guard':switch()
                    return True
                class FakeBinding:
                    def __init__(self,sock,**kw):self.sock=sock
                    def bind(self):
                        if stage=='handoff':switch()
                    def handoff(self):return self.sock
                with patch.object(bind,'ExperimentalSourceJobBinding',FakeBinding):
                    with self.assertRaises(RuntimeError):bind.bind_running_source(sock,process=identity,lease=L,attempt=A,
                        epoch=E,generation=G,world=world,client_guard=guard,timeout=1)
                self.assertEqual(sock.fileno(),-1)

    def test_motion_owner_must_use_exact_guarded_world(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
        self.addCleanup(sock.close);identity,world=context();_,other=context()
        motion=types.SimpleNamespace(_delivery=types.SimpleNamespace(_host=types.SimpleNamespace(_world=other)))
        with self.assertRaises(ValueError):motion_bind.bind_running_source_motion(sock,motion,process=identity,
            lease=L,attempt=A,epoch=E,generation=G,world=world,client_guard=lambda:True,
            select_recipients=lambda value,members:[],timeout=1)
        self.assertEqual(sock.fileno(),-1)
