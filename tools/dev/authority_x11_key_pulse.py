"""Default-off one-key private X11 worker supervisor; never launches X4."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import sys
import time

from authority_helper_lifecycle import OwnedHelper
import authority_x11_private_scope as scope

WORKER=Path(__file__).with_name('authority_x11_pulse_worker.py')
class KeyReleaseUnconfirmed(RuntimeError):
    """Retain owned X4/display and its lock until independent cleanup succeeds."""

class OneKeyPulse:
    def __init__(self,*,enabled=False):
        if enabled is not True:raise ValueError('private input is disabled')
        self.helpers=[];self.sockets=[];self.used=False;self.keycode=None
        self.possible_down=False;self.up_confirmed=False
    @staticmethod
    def _check(deadline,guard):
        if time.monotonic()>=deadline:raise TimeoutError('input deadline')
        if guard() is not True:raise RuntimeError('input scope guard failed')
        if time.monotonic()>=deadline:raise TimeoutError('input deadline')
    @staticmethod
    def _status(h):
        if h.proc is None:return None
        if h.proc.returncode is not None:return h.proc.returncode
        if signal.getsignal(signal.SIGCHLD)!=signal.SIG_DFL or h.pidfd is None:raise RuntimeError('helper identity unavailable')
        try:result=os.waitid(os.P_PIDFD,h.pidfd,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        except ChildProcessError:raise RuntimeError('helper reaped externally') from None
        return None if result is None else h.proc.poll()
    def _open(self,config,deadline,guard):
        self._check(deadline,guard)
        parent,child=socket.socketpair();self.sockets.extend((parent,child))
        helper=OwnedHelper([sys.executable,str(WORKER),str(child.fileno())],registry=self.helpers,pass_fds=(child.fileno(),))
        child.close();self._check(deadline,guard)
        data=(json.dumps(config,separators=(',',':'),allow_nan=False)+'\n').encode('ascii')
        if len(data)>8192:raise ValueError('input configuration too large')
        parent.settimeout(max(.001,min(1,deadline-time.monotonic())))
        parent.sendall(data);parent.setblocking(False)
        self._check(deadline,guard);helper.release();self._check(deadline,guard)
        return helper,parent
    def _message(self,h,sock,deadline,guard):
        raw=bytearray()
        while not raw.endswith(b'\n'):
            self._check(deadline,guard)
            if self._status(h) is not None:
                ready,_,_=select.select([sock],[],[],0)
                if not ready:raise RuntimeError('input helper exited before receipt')
            ready,_,_=select.select([sock],[],[],min(.02,max(0,deadline-time.monotonic())))
            if not ready:continue
            part=sock.recv(1)
            if not part:raise RuntimeError('input helper closed before receipt')
            raw.extend(part)
            if len(raw)>256:raise ValueError('input receipt too large')
        self._check(deadline,guard)
        value=json.loads(raw.decode('ascii'))
        if type(value) is not dict:raise ValueError('invalid input receipt')
        return value
    def _finish(self,h,deadline,guard):
        while self._status(h) is None:
            self._check(deadline,guard)
            select.select([h.pidfd],[],[],min(.02,max(0,deadline-time.monotonic())))
        code=h.stop();self._check(deadline,guard)
        if code!=0:raise RuntimeError('input helper failed')
    def _emergency_release(self,s):
        if self.keycode is None:raise KeyReleaseUnconfirmed('keycode unknown')
        deadline=time.monotonic()+5
        guard=lambda:scope.verify(s,require_x4=False)
        self._check(deadline,guard)
        h,ipc=self._open({'scope':s,'mode':'release','code':self.keycode,'duration':0,'deadline':deadline},deadline,guard)
        try:
            if self._message(h,ipc,deadline,guard)!={'event':'RELEASED'}:raise RuntimeError('release receipt mismatch')
            self._finish(h,deadline,guard);self.up_confirmed=True
        finally:ipc.close()
    def run(self,s,*,duration,deadline,guard):
        if self.used:raise RuntimeError('pulse already consumed')
        self.used=True
        if type(duration) not in (int,float) or not .05<=duration<=.5:raise ValueError('invalid pulse duration')
        if type(deadline) not in (int,float) or not time.monotonic()<deadline<=time.monotonic()+15:raise ValueError('invalid deadline')
        if type(s) is not dict or s.get('owner_pid')!=os.getpid():raise ValueError('scope must belong to this supervisor')
        def full_guard():return scope.verify(s) is True and guard() is True
        h=ipc=None
        try:
            self._check(deadline,full_guard)
            h,ipc=self._open({'scope':s,'mode':'pulse','code':None,'duration':duration,'deadline':deadline},deadline,full_guard)
            ready=self._message(h,ipc,deadline,full_guard)
            if set(ready)!={'event','keycode'} or ready['event']!='READY' or type(ready['keycode']) is not int or not 8<=ready['keycode']<=255:raise ValueError('invalid READY')
            self.keycode=ready['keycode'];self._check(deadline,full_guard)
            self.possible_down=True
            if ipc.send(b'G')!=1:raise RuntimeError('pulse authorization unconfirmed')
            if self._message(h,ipc,deadline,full_guard)!={'event':'DOWN'}:raise RuntimeError('missing key down')
            if self._message(h,ipc,deadline,full_guard)!={'event':'UP'}:raise RuntimeError('missing key up')
            self.up_confirmed=True
            if self._message(h,ipc,deadline,full_guard)!={'event':'DONE'}:raise RuntimeError('missing final focus check')
            self._finish(h,deadline,full_guard)
            return {'key':'a','duration_requested':duration,'server_key_up_observed':True,'x4_input_received_proven':False}
        finally:
            # A STOP or SIGTERM requests cleanup; a kill or broken worker makes
            # the independent release process mandatory before lock release.
            if ipc is not None:
                try:ipc.send(b'S')
                except (OSError,ValueError):pass
            stop_error=None
            if h is not None:
                try:h.stop(grace=.5)
                except BaseException as error:stop_error=error
            if ipc is not None:
                try:ipc.close()
                except OSError:pass
            if stop_error is not None:raise KeyReleaseUnconfirmed('input helper reap unconfirmed') from stop_error
            if self.possible_down and not self.up_confirmed:
                try:self._emergency_release(s)
                except BaseException as error:raise KeyReleaseUnconfirmed('key release unconfirmed; retain lock') from error
            if self.up_confirmed:
                try:scope.verify(s,require_x4=False)
                except BaseException as error:raise KeyReleaseUnconfirmed('private display identity changed after release') from error
    def cleanup_before_owned_processes(self):
        errors=[]
        for s in self.sockets:
            try:s.close()
            except BaseException as error:errors.append(error)
        for h in reversed(self.helpers):
            try:h.stop()
            except BaseException as error:errors.append(error)
        if errors or (self.possible_down and not self.up_confirmed):raise KeyReleaseUnconfirmed('input cleanup unconfirmed')
        return True
