"""Private pidfd-owned witness-guard helper; no X4 and no admission changes.

A successful CHECK is a sampled assertion, not a lock. The caller must fence
all checkpoint writers, protect the X4 session, and clean the helper before
releasing its global process lock. The existing full guard validates on startup.
The owner must exclusively own the IPC/pidfd descriptor numbers: checking an
FD identity and closing it cannot be made atomic against concurrent dup2/close.
Callers that must fence constructor failures must supply `cleanup_registry`;
without it a failed constructor does not return its owner for later cleanup.
Construction and helper cleanup require the main thread.
"""
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import signal
import socket
import sys
import threading
import time

from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json, send_frame

READER=Path(__file__).resolve().with_name('authority_recovered_registry_reader.py')


class GuardClientTiming:
    """Optional local wall times; response waits do not identify helper work.

    Send time includes any nested pump time. Response wait is time in select,
    not the helper's hash time; scheduler and I/O waits are included.
    """
    def __init__(self, clock=None):
        self.clock = time.perf_counter if clock is None else clock
        self.values = {name: {'calls': 0, 'seconds': 0.0} for name in ('pump', 'send', 'response_wait')}

    def start(self):
        try:
            value = self.clock()
            return value if type(value) in (int, float) and math.isfinite(value) else None
        except Exception:
            return None

    def finish(self, name, started):
        try:
            finished = self.clock()
            if (started is not None and type(finished) in (int, float) and
                    math.isfinite(finished) and finished >= started):
                row = self.values[name]
                row['calls'] += 1
                row['seconds'] += finished - started
        except Exception:
            pass  # Diagnostic accounting must not replace an operation error.

    def snapshot(self):
        return {name: dict(value) for name, value in self.values.items()}


class WitnessGuardClient:
    """Main-thread owner of the helper and its exclusively held IPC endpoints."""
    def __init__(self, store, checkpoint, *, deadline, registry, pump, timeout=120, cleanup_registry=None):
        if (threading.current_thread() is not threading.main_thread() or
            type(deadline) not in (int,float) or not math.isfinite(deadline) or
            not time.monotonic()<deadline<=time.monotonic()+86400 or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120 or
            type(registry) is not list or not callable(pump) or
            (cleanup_registry is not None and type(cleanup_registry) is not list)):
            raise ValueError('bounded guard context required')
        self.deadline=float(deadline);self.timeout=float(timeout);self.pump=pump
        self.owner=threading.get_ident();self.seq=0;self.state='initializing';self.token=secrets.token_hex(16)
        self.timing=None
        self.sock=None;self._owned_sock=None;self.helper=None;self._owned_helper=None
        self.fd=self.identity=self._child_fd=self._child_identity=None
        self._owned_child=None;self._socket_cleanup_error=None
        if cleanup_registry is not None:
            # Register before acquiring descriptors, even if initialization fails.
            cleanup_registry.append(self)
        try:
            self._open_owned_socketpair()
            parent,child=self._owned_sock,self._owned_child
            parent.setblocking(False)
            self.helper=OwnedHelper([sys.executable,str(READER),str(child.fileno())],registry=registry,pass_fds=(child.fileno(),))
            self._owned_helper=self.helper;self._proc=self.helper.proc;self._pidfd=self.helper.pidfd
            self._close_ipc_socket('_owned_child',self._child_fd,self._child_identity)
            if self._socket_cleanup_error is not None:
                raise RuntimeError('guard IPC cleanup unconfirmed') from self._socket_cleanup_error
            self.helper.release()
            config={'mode':'witness_guard','store':str(store.directory),'token':self.token,'deadline':self.deadline}
            config.update({key:str(getattr(checkpoint,key)) if key=='path' else getattr(checkpoint,key)
                           for key in ('checkpoint_id','path','sha256','size','marker')})
            self._send(config,self.deadline)
            answer=self._read(self.deadline)
            if (type(answer) is not dict or set(answer)!={'token','seq','event','status'} or
                answer['token']!=self.token or type(answer['seq']) is not int or answer['seq']!=0 or
                answer['event']!='READY' or type(answer['status']) is not list or len(answer['status'])!=4 or
                answer['status'][0]!='ready' or type(answer['status'][1]) is not str or
                not re.fullmatch(r'[0-9a-f]{32}',answer['status'][1]) or
                type(answer['status'][2]) is not int or not 1<=answer['status'][2]<=200000 or
                type(answer['status'][3]) is not str or not re.fullmatch(r'[0-9a-f]{64}',answer['status'][3])):
                raise ValueError('invalid guard READY')
            self.status=tuple(answer['status']);self._quiet();self.state='ready'
        except BaseException as error:
            self.state='failed'
            try: self._cleanup()
            except BaseException as cleanup_error:
                error.add_note('guard initialization cleanup failed: '+type(cleanup_error).__name__)
            raise

    def _open_owned_socketpair(self):
        """Register both IPC endpoints before delivering cancellation signals."""
        deferred=[None];previous={}
        def remember(number, _frame):
            deferred[0]=deferred[0] or number
        try:
            for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
                previous[number]=signal.signal(number,remember)
            parent,child=socket.socketpair()
            self.sock=self._owned_sock=parent;self._owned_child=child
            self.fd=parent.fileno();st=os.fstat(self.fd);self.identity=(st.st_dev,st.st_ino)
            self._child_fd=child.fileno();st=os.fstat(self._child_fd);self._child_identity=(st.st_dev,st.st_ino)
        finally:
            for number,handler in previous.items():signal.signal(number,handler)
        if deferred[0] is not None:
            raise InterruptedError('signal '+str(deferred[0]))

    def _check(self):
        if (threading.get_ident()!=self.owner or self.state not in ('initializing','ready','checking','stopping') or
            self.helper is None or self.helper is not self._owned_helper or self.helper.proc is not self._proc or
            self.helper.pidfd!=self._pidfd or self._pidfd is None or self._proc.poll() is not None or
            self.sock is None or self.sock is not self._owned_sock or self.sock.fileno()!=self.fd or time.monotonic()>=self.deadline):
            raise RuntimeError('guard helper unavailable')
        st=os.fstat(self.fd)
        if (st.st_dev,st.st_ino)!=self.identity:raise RuntimeError('guard IPC identity changed')
        pidfd_st=os.fstat(self._pidfd)
        if (pidfd_st.st_dev,pidfd_st.st_ino)!=self._owned_helper._pidfd_identity:
            raise RuntimeError('guard pidfd identity changed')
        state=self.state
        self._pump()
        if (self.state!=state or self.helper is not self._owned_helper or self.helper.proc is not self._proc or
                self.helper.pidfd!=self._pidfd or self._proc.poll() is not None or self.sock is None or self.sock is not self._owned_sock or
                self.sock.fileno()!=self.fd or time.monotonic()>=self.deadline):
            raise RuntimeError('guard helper changed')
        st=os.fstat(self.fd)
        if (st.st_dev,st.st_ino)!=self.identity:raise RuntimeError('guard IPC identity changed')
        pidfd_st=os.fstat(self._pidfd)
        if (pidfd_st.st_dev,pidfd_st.st_ino)!=self._owned_helper._pidfd_identity:
            raise RuntimeError('guard pidfd identity changed')

    def _send(self,value,deadline):
        payload=json.dumps(value,separators=(',',':'),allow_nan=False).encode('ascii')
        if len(payload)>4096:raise ValueError('guard request too large')
        timing=self.timing
        started=timing.start() if timing is not None else None
        try:
            send_frame(self.sock,payload,deadline,self._check)
        finally:
            if timing is not None:timing.finish('send',started)

    def enable_timing(self, timing=None):
        """Start local accounting between operations; does not time the helper."""
        if (threading.get_ident()!=self.owner or self.state!='ready' or self.timing is not None or
                (timing is not None and type(timing) is not GuardClientTiming)):
            raise ValueError('timing requires an idle owned guard')
        self.timing = GuardClientTiming() if timing is None else timing
        return self.timing

    def _pump(self):
        timing=self.timing
        started=timing.start() if timing is not None else None
        try:
            return self.pump()
        finally:
            if timing is not None:timing.finish('pump',started)

    def _read(self,deadline):
        # Only one reply is legal per request. Read in bounded chunks so a
        # guarded pump is not invoked once per byte of a JSON frame.
        data=bytearray()
        while True:
            self._check()
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('guard response timed out')
            timing=self.timing
            started=timing.start() if timing is not None else None
            try:
                ready,_,bad=select.select([self.sock],[],[self.sock],min(left,.25))
            finally:
                if timing is not None:timing.finish('response_wait',started)
            if bad:raise RuntimeError('guard socket exception')
            if not ready:continue
            self._check()
            try:chunk=self.sock.recv(1026-len(data))
            except BlockingIOError:continue
            if not chunk:raise RuntimeError('guard socket closed')
            data.extend(chunk)
            if b'\n' in data:
                line,tail=data.split(b'\n',1)
                if tail or len(line)>1024:raise ValueError('unexpected or oversized guard frame')
                self._check()
                if time.monotonic()>=deadline:raise TimeoutError('guard response timed out')
                return parse_json(bytes(line))
            if len(data)>1024:raise ValueError('guard frame too large')

    def _quiet(self):
        self._check();readable,_,bad=select.select([self.sock],[],[self.sock],0)
        if readable or bad:raise RuntimeError('unexpected guard frame or EOF')
        self._check()

    def _request(self,op):
        if self.state!='ready' or threading.get_ident()!=self.owner:
            self.state='failed';raise RuntimeError('guard reentry or unavailable')
        self.state='checking' if op=='CHECK' else 'stopping'
        try:
            self._quiet();self.seq+=1
            deadline=min(self.deadline,time.monotonic()+self.timeout)
            self._send({'token':self.token,'seq':self.seq,'op':op},deadline)
            answer=self._read(deadline)
            if (type(answer) is not dict or set(answer)!={'token','seq','event'} or
                answer['token']!=self.token or type(answer['seq']) is not int or answer['seq']!=self.seq or
                answer['event']!=('CHECKED' if op=='CHECK' else 'STOPPED')):
                raise ValueError('invalid guard response')
            if op=='CHECK':self._quiet();self.state='ready';return True
            # STOPPED is consumed while the helper is still alive. Explicitly
            # acknowledge it with EOF, then require clean exit and peer EOF.
            self._quiet();self.sock.shutdown(socket.SHUT_WR)
            while self.helper.proc.poll() is None:
                if time.monotonic()>=deadline:raise TimeoutError('guard STOP exit deadline')
                self._pump()
                if (self.state!='stopping' or self.helper is not self._owned_helper or self.helper.proc is not self._proc or
                    self.helper.pidfd!=self._pidfd or self.sock is None or self.sock is not self._owned_sock or self.sock.fileno()!=self.fd):
                    raise RuntimeError('guard STOP context changed')
                st=os.fstat(self.fd)
                if (st.st_dev,st.st_ino)!=self.identity:raise RuntimeError('guard IPC identity changed')
                select.select([],[],[],min(.02,max(0,deadline-time.monotonic())))
            if self.helper.proc.returncode!=0:raise RuntimeError('guard helper exit failed')
            ready,_,bad=select.select([self.sock],[],[self.sock],0)
            if bad or not ready or self.sock.recv(1)!=b'':raise RuntimeError('guard trailing response')
            self.state='stopped';self._cleanup();return True
        except BaseException as error:
            self.state='failed'
            try: self._cleanup()
            except BaseException as cleanup_error:
                error.add_note('guard request cleanup failed: '+type(cleanup_error).__name__)
            raise

    def check(self):return self._request('CHECK')
    def stop(self):return self._request('STOP')

    def _close_ipc_socket(self, attribute, descriptor, identity):
        """Close a pinned IPC endpoint or permanently record uncertainty."""
        owned=getattr(self,attribute)
        if owned is None:return
        try:
            if descriptor is None or identity is None or owned.fileno()!=descriptor:
                raise RuntimeError('guard IPC descriptor unavailable or replaced')
            st=os.fstat(descriptor)
            if (st.st_dev,st.st_ino)!=identity:
                raise RuntimeError('guard IPC replaced; cleanup unconfirmed')
            owned.close()
        except BaseException as error:
            if self._socket_cleanup_error is None:
                self._socket_cleanup_error=error
            else:
                self._socket_cleanup_error.add_note('another guard IPC cleanup failed: '+type(error).__name__)
            try:
                # Do not let finalization close a potentially foreign FD.
                if owned.fileno()>=0:owned.detach()
            except BaseException as detach_error:
                self._socket_cleanup_error.add_note('guard IPC detach failed: '+type(detach_error).__name__)
                if not hasattr(self,'_untrusted_sockets'):self._untrusted_sockets=[]
                self._untrusted_sockets.append(owned)
        setattr(self,attribute,None)
        if attribute=='_owned_sock':self.sock=None

    def _cleanup(self):
        # A failed IPC close remains uncertain across subsequent calls. Helper
        # stop is still attempted every time, including after either IPC fault.
        self._close_ipc_socket('_owned_child',self._child_fd,self._child_identity)
        self._close_ipc_socket('_owned_sock',self.fd,self.identity)
        helper_error=None
        try:
            if self._owned_helper is not None:self._owned_helper.stop()
        except BaseException as error:
            helper_error=error
        if self._socket_cleanup_error is not None:
            failure=RuntimeError('guard IPC cleanup unconfirmed')
            if helper_error is not None:
                failure.add_note('guard helper cleanup also failed: '+type(helper_error).__name__)
            raise failure from self._socket_cleanup_error
        if helper_error is not None:
            raise helper_error
