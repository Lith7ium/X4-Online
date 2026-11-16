"""Small real helper and checkpoint tests; no native X4."""
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from test_authority_witness_source_guard import source_xml, MARKER
import authority_witness_guard_client as client
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import read_line, send_frame, parse_json

@unittest.skipUnless(sys.platform=='linux' and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'Linux pidfd required')
class GuardHelper(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'store').mkdir();self.store=CheckpointStore(self.root/'store')
        source=self.root/'save.gz';source.write_bytes(gzip.compress(source_xml().encode()))
        self.cp=self.store.publish(source,marker=MARKER);self.store.confirm(self.cp)
        self.registry=[];self.pumps=0
    def pump(self):self.pumps+=1
    def start(self,**kw):
        return client.WitnessGuardClient(self.store,self.cp,registry=self.registry,pump=self.pump,
            deadline=time.monotonic()+kw.get('deadline',5),timeout=kw.get('timeout',2))
    def test_full_guard_check_and_clean_correlated_stop(self):
        g=self.start();self.addCleanup(g._cleanup)
        self.assertEqual(g.status[:3],('ready','a'*32,2))
        self.assertTrue(g.check());self.assertTrue(g.check());self.assertTrue(g.stop())
        self.assertEqual(g.state,'stopped');self.assertEqual(g.helper.proc.returncode,0)
        self.assertIsNone(g.helper.pidfd);self.assertGreater(self.pumps,0)
    def test_opt_in_timing_preserves_real_helper_check_and_stop(self):
        g=self.start();self.addCleanup(g._cleanup)
        timing=g.enable_timing()
        self.assertTrue(g.check());self.assertTrue(g.stop())
        values=timing.snapshot()
        self.assertEqual(set(values),{'pump','send','response_wait'})
        self.assertGreater(values['pump']['calls'],0)
        self.assertEqual(values['send']['calls'],2)
        self.assertGreater(values['response_wait']['calls'],0)
        self.assertTrue(all(row['seconds']>=0 for row in values.values()))
        self.assertEqual(g.state,'stopped');self.assertIsNone(g.helper.pidfd)
    def test_pointer_mutation_faults_and_reaps(self):
        g=self.start();self.addCleanup(g._cleanup)
        p=self.store.directory/'CURRENT';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises((RuntimeError,ValueError,TimeoutError)):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
        self.assertIsNotNone(g.helper.proc.poll())
    def test_dead_helper_fails_closed(self):
        g=self.start();self.addCleanup(g._cleanup);g.helper.proc.kill();g.helper.proc.wait()
        with self.assertRaises(RuntimeError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_initialization_deadline_and_pumping(self):
        script=self.root/'slow.py';script.write_text('import time\ntime.sleep(10)\n')
        with patch.object(client,'READER',script):
            with self.assertRaises((TimeoutError,RuntimeError)):self.start(deadline=.3,timeout=.1)
        self.assertGreater(self.pumps,0)
        self.assertIsNotNone(self.registry[0].proc.poll());self.assertIsNone(self.registry[0].pidfd)
    def test_check_timeout_correlated_protocol_and_cleanup(self):
        script=self.root/'stall.py';script.write_text('''import json,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));f=s.makefile('rb');c=json.loads(f.readline())
s.sendall((json.dumps(dict(token=c['token'],seq=0,event='READY',status=['ready','a'*32,2,'b'*64]))+'\\n').encode())
f.readline();time.sleep(10)
''')
        with patch.object(client,'READER',script):
            g=self.start(timeout=.2);self.addCleanup(g._cleanup)
            with self.assertRaises(TimeoutError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
        self.assertIsNotNone(g.helper.proc.poll())
    def test_wrong_correlation_faults(self):
        script=self.root/'wrong.py';script.write_text('''import json,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));f=s.makefile('rb');c=json.loads(f.readline())
s.sendall((json.dumps(dict(token=c['token'],seq=0,event='READY',status=['ready','a'*32,2,'b'*64]))+'\\n').encode())
r=json.loads(f.readline());s.sendall((json.dumps(dict(token=r['token'],seq=r['seq']+1,event='CHECKED'))+'\\n').encode())
time.sleep(10)
''')
        with patch.object(client,'READER',script):
            g=self.start();self.addCleanup(g._cleanup)
            with self.assertRaises(ValueError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_timing_survives_guard_failure_and_reap(self):
        g=self.start();self.addCleanup(g._cleanup)
        timing=g.enable_timing()
        pointer=self.store.directory/'CURRENT'
        pointer.write_bytes(pointer.read_bytes()+b' ')
        with self.assertRaises((RuntimeError,ValueError,TimeoutError)):
            g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
        self.assertIsNotNone(g.helper.proc.poll())
        self.assertGreater(timing.snapshot()['pump']['calls'],0)
        self.assertEqual(timing.snapshot()['send']['calls'],1)
    def test_pump_reentry_cannot_restore_failed_state(self):
        g=self.start();self.addCleanup(g._cleanup);attempted=[]
        def reenter():
            if not attempted:
                attempted.append(True)
                try:g.check()
                except RuntimeError:pass
        g.pump=reenter
        with self.assertRaises(RuntimeError):g.check()
        self.assertEqual(attempted,[True]);self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_oversized_or_unsolicited_response_faults(self):
        for value in ('oversized','duplicate'):
            with self.subTest(value=value):
                script=self.root/(value+'.py')
                response="b'x'*1026" if value=='oversized' else "b'{}\\n{}\\n'"
                script.write_text("import socket,sys,time\ns=socket.socket(fileno=int(sys.argv[1]));s.recv(4096)\ns.sendall("+response+")\ntime.sleep(10)\n")
                with patch.object(client,'READER',script):
                    with self.assertRaises(ValueError):self.start()
                self.assertIsNotNone(self.registry[-1].proc.poll());self.assertIsNone(self.registry[-1].pidfd)
    def test_replaced_ipc_descriptor_is_detached_not_closed(self):
        g=self.start();self.addCleanup(g.helper.stop)
        fd=g.fd;read,write=os.pipe()
        try:
            os.dup2(read,fd)
            with self.assertRaisesRegex(RuntimeError,'IPC identity changed'):g.check()
            os.fstat(fd)
            self.assertIsNone(g.helper.pidfd)
            with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):g._cleanup()
            os.fstat(fd)
        finally:
            os.close(fd);os.close(read);os.close(write)

    def test_failed_socket_close_stays_failed_and_helper_stop_is_retried(self):
        g=self.start();self.addCleanup(g.helper.stop)
        fd=g.fd
        original_close=socket.socket.close
        original_stop=g.helper.stop
        calls=[]

        def close_with_failure(sock):
            if sock is g._owned_sock:
                raise OSError('simulated IPC close failure')
            return original_close(sock)

        def flaky_stop():
            calls.append('stop')
            if len(calls)==1:
                raise RuntimeError('simulated helper stop failure')
            return original_stop()

        try:
            with patch.object(socket.socket, 'close', close_with_failure), \
                 patch.object(g.helper, 'stop', side_effect=flaky_stop):
                with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed') as first:
                    g._cleanup()
                self.assertIsInstance(first.exception.__cause__, OSError)
                self.assertTrue(any('helper cleanup also failed' in note for note in first.exception.__notes__))
                with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):
                    g._cleanup()
            self.assertEqual(calls,['stop','stop'])
            self.assertIsNotNone(g.helper.proc.poll())
            self.assertIsNone(g.helper.pidfd)
            os.fstat(fd)  # Simulated close did not close or let finalization close it.
        finally:
            os.close(fd)

    def test_constructor_failure_registers_sticky_socket_cleanup_with_owner(self):
        import authority_recovered_loopback_server as supervisor
        import authority_recovered_server_client as recovered_client
        participant=SimpleNamespace(keep_worker=True,helpers=self.registry,pump_loading=self.pump)
        world=SimpleNamespace(_store=self.store)
        sockets=[]
        original_pair=socket.socketpair
        original_close=socket.socket.close

        def record_pair():
            pair=original_pair()
            sockets.extend(pair)
            return pair

        def fail_parent_close(sock):
            if sockets and sock is sockets[0]:
                raise OSError('simulated parent IPC close failure')
            return original_close(sock)

        try:
            with patch.object(client.socket, 'socketpair', side_effect=record_pair), \
                 patch.object(socket.socket, 'close', fail_parent_close), \
                 patch.object(client, 'OwnedHelper', side_effect=ValueError('original initialization failure')):
                with self.assertRaisesRegex(ValueError, 'original initialization failure') as error:
                    recovered_client.prepare_witness_guard(
                        participant,world,self.cp,time.monotonic()+5,lambda:None)
            self.assertTrue(any('initialization cleanup failed' in note for note in error.exception.__notes__))
            resources=participant.guard_resources
            self.assertEqual(len(resources),1)
            self.assertIsInstance(resources[0]._socket_cleanup_error,OSError)
            diagnostic=Mock()
            diagnostic.cleanup_diagnostic.side_effect=resources[0]._cleanup
            errors=[]
            self.assertFalse(supervisor.cleanup_diagnostics([diagnostic],errors))
            self.assertTrue(any('cleanup unconfirmed' in error for error in errors))
        finally:
            if getattr(participant, 'guard_resources', None):
                fd=participant.guard_resources[0].fd
                try:os.close(fd)
                except OSError:pass

    def test_request_error_survives_simultaneous_socket_cleanup_failure(self):
        g=self.start();self.addCleanup(g.helper.stop)
        fd=g.fd
        original_close=socket.socket.close

        def close_with_failure(sock):
            if sock is g._owned_sock:raise OSError('simulated IPC close failure')
            return original_close(sock)

        def fail_operation():
            raise ValueError('original request failure')

        g.pump=fail_operation
        try:
            with patch.object(socket.socket,'close',close_with_failure):
                with self.assertRaisesRegex(ValueError,'original request failure') as error:
                    g.check()
            self.assertTrue(any('request cleanup failed' in note for note in error.exception.__notes__))
            self.assertEqual(g.state,'failed')
            self.assertIsNotNone(g.helper.proc.poll())
            with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):
                g._cleanup()
            os.fstat(fd)
        finally:
            os.close(fd)

    def test_child_close_failure_is_sticky_and_helper_is_reaped(self):
        resources=[]
        sockets=[]
        original_pair=socket.socketpair
        original_close=socket.socket.close

        def record_pair():
            pair=original_pair();sockets.extend(pair);return pair

        def fail_child_close(sock):
            if sockets and sock is sockets[1]:
                raise OSError('simulated child IPC close failure')
            return original_close(sock)

        try:
            with patch.object(client.socket,'socketpair',side_effect=record_pair), \
                 patch.object(socket.socket,'close',fail_child_close):
                with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed') as first:
                    client.WitnessGuardClient(self.store,self.cp,registry=self.registry,pump=self.pump,
                        deadline=time.monotonic()+5,cleanup_registry=resources)
            self.assertIsInstance(first.exception.__cause__,OSError)
            self.assertEqual(len(resources),1)
            with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):
                resources[0]._cleanup()
            self.assertIsNotNone(self.registry[0].proc.poll())
            self.assertIsNone(self.registry[0].pidfd)
            os.fstat(resources[0]._child_fd)
        finally:
            if resources and resources[0]._child_fd is not None:
                try:os.close(resources[0]._child_fd)
                except OSError:pass

    def test_constructor_rejects_other_thread_before_registering_or_opening(self):
        resources=[]
        errors=[]
        def run():
            try:
                client.WitnessGuardClient(self.store,self.cp,registry=self.registry,pump=self.pump,
                    deadline=time.monotonic()+5,cleanup_registry=resources)
            except BaseException as error:
                errors.append(error)
        with patch.object(client.socket,'socketpair') as create_socketpair:
            thread=threading.Thread(target=run);thread.start();thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],ValueError)
        self.assertEqual(resources,[])
        self.assertEqual(self.registry,[])
        create_socketpair.assert_not_called()

    def test_signal_after_socketpair_acquisition_keeps_both_endpoints_owned(self):
        resources=[]
        original_pair=socket.socketpair
        captured=[]

        def interrupted_pair():
            pair=original_pair();captured.extend(pair)
            signal.raise_signal(signal.SIGTERM)
            return pair

        with patch.object(client.socket,'socketpair',side_effect=interrupted_pair):
            with self.assertRaises(InterruptedError):
                client.WitnessGuardClient(self.store,self.cp,registry=self.registry,pump=self.pump,
                    deadline=time.monotonic()+5,cleanup_registry=resources)
        self.assertEqual(len(resources),1)
        self.assertEqual([sock.fileno() for sock in captured],[-1,-1])
        self.assertEqual(self.registry,[])
        resources[0]._cleanup()

    def test_second_guard_cleanup_keeps_supervisor_lock_after_ipc_failure(self):
        import authority_recovered_loopback_server as supervisor
        g=self.start();self.addCleanup(g.helper.stop)
        fd=g.fd;read,write=os.pipe()
        lock=self.root/'global-lock';lock.write_text('lock')
        lock_fd=os.open(lock,os.O_RDONLY);lock_stat=os.fstat(lock_fd)
        try:
            os.dup2(read,fd)
            with self.assertRaisesRegex(RuntimeError,'IPC identity changed'):
                g.check()
            import authority_recovered_server_client as recovered_client
            participant=object.__new__(recovered_client.ServerClient)
            participant.guard_resources=[g]
            participant.helpers=[]
            errors=[]
            clean=supervisor.cleanup_diagnostics([participant],errors)
            self.assertFalse(clean)
            remaining=supervisor.stop_owned_processes([],clean,errors)
            self.assertIsNone(remaining)
            supervisor.finish_recovery_lock([(lock_fd,lock_stat)],remaining,True,errors)
            lock_fd=None
            self.assertTrue(lock.exists())
            self.assertTrue(any('lock retained' in error for error in errors))
            os.fstat(fd)  # Foreign replacement must not be closed.
        finally:
            if lock_fd is not None:os.close(lock_fd)
            os.close(fd);os.close(read);os.close(write)

    def test_reader_rejects_wrong_token_sequence_and_post_stop_frame(self):
        for case in ('token','sequence','after_stop'):
            with self.subTest(case=case):
                parent,child=socket.socketpair();self.addCleanup(parent.close)
                helper=OwnedHelper([sys.executable,str(client.READER),str(child.fileno())],
                    registry=self.registry,pass_fds=(child.fileno(),))
                try:
                    child.close();parent.setblocking(False);helper.release();deadline=time.monotonic()+4
                    token='e'*32
                    config={'mode':'witness_guard','store':str(self.store.directory),'token':token,'deadline':deadline}
                    config.update({key:str(getattr(self.cp,key)) if key=='path' else getattr(self.cp,key)
                                   for key in ('checkpoint_id','path','sha256','size','marker')})
                    def send(value):send_frame(parent,json.dumps(value).encode(),deadline,lambda:None)
                    def read():return parse_json(read_line(parent,1024,deadline))
                    send(config);self.assertEqual(read()['event'],'READY')
                    request={'token':token,'seq':1,'op':'CHECK'}
                    if case=='token':request['token']='f'*32
                    elif case=='sequence':request['seq']=2
                    else:request['op']='STOP'
                    send(request)
                    if case=='after_stop':
                        self.assertEqual(read()['event'],'STOPPED');send({'token':token,'seq':2,'op':'CHECK'})
                    self.assertNotEqual(helper.proc.wait(timeout=3),0)
                finally:
                    child.close();parent.close();helper.stop()
