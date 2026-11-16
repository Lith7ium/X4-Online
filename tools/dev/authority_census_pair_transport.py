"""Single-use pidfd/gate-owned helper and job TCP exchange; no X4 start."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import sys
import time

import authority_descriptor_loopback as stream
import authority_job_descriptor_loopback as job
from authority_helper_lifecycle import OwnedHelper

ROOT=Path(__file__).resolve().parents[2]


class OwnedJobTransport:
    """Caller must confirm this helper's cleanup before releasing X4/lock."""
    def __init__(self):
        self.helpers=[];self.sockets=[];self.used=False;self.closed=False

    def _status(self,helper):
        proc=helper.proc
        if proc is None:return None
        if proc.returncode is not None:return proc.returncode
        if signal.getsignal(signal.SIGCHLD)!=signal.SIG_DFL or helper.pidfd is None:
            raise RuntimeError('helper identity unconfirmed')
        try:ready=os.waitid(os.P_PIDFD,helper.pidfd,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        except ChildProcessError:raise RuntimeError('helper reaped externally') from None
        return None if ready is None else proc.poll()

    def exchange(self,descriptor,expected_attempt,expected_epoch,expected_job_sequence,witness_check,deadline,guard):
        if self.used or self.closed:raise RuntimeError('transport already consumed')
        self.used=True
        desc=job._descriptor(descriptor)
        if (desc['attempt'],desc['epoch'],desc['job_sequence'])!=(expected_attempt,expected_epoch,expected_job_sequence):
            raise ValueError('transport context differs')
        stream._check(deadline,guard)
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);self.sockets.append(listener)
        listener.bind(('127.0.0.1',0));listener.listen(1)
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('connection deadline')
        listener.settimeout(min(2,remaining))
        sender=socket.create_connection(listener.getsockname(),timeout=min(2,remaining));self.sockets.append(sender)
        receiver,_=listener.accept();self.sockets.append(receiver)
        stream._check(deadline,guard)
        ipc_parent,ipc_child=socket.socketpair();self.sockets.extend((ipc_parent,ipc_child))
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_job_descriptor_sender_worker.py'),
                            str(sender.fileno()),str(ipc_child.fileno())],registry=self.helpers,
                           pass_fds=(sender.fileno(),ipc_child.fileno()))
        sender.close();ipc_child.close();listener.close()
        stream._check(deadline,guard)
        raw=json.dumps({'descriptor':desc,'deadline':deadline},allow_nan=False,separators=(',',':')).encode('ascii')
        if len(raw)>4096:raise ValueError('private config too large')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('private config deadline')
        ipc_parent.settimeout(min(2,remaining));ipc_parent.sendall(raw);ipc_parent.shutdown(socket.SHUT_WR);ipc_parent.close()
        stream._check(deadline,guard);helper.release();stream._check(deadline,guard)
        received=job.receive_descriptor(receiver,expected_attempt,expected_epoch,expected_job_sequence,
                                        witness_check,deadline,guard)
        if received!=desc:raise ValueError('descriptor changed in transit')
        while self._status(helper) is None:
            stream._check(deadline,guard)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('helper deadline')
            select.select([helper.pidfd],[],[],min(.2,remaining))
        if self._status(helper)!=0:raise RuntimeError('sender ACK verification failed')
        stream._check(deadline,guard)
        return received

    def cleanup_before_owned_processes(self):
        if self.closed:return True
        errors=[]
        for sock in self.sockets:
            try:sock.close()
            except BaseException as error:errors.append(error)
        for helper in reversed(self.helpers):
            try:helper.stop()
            except BaseException as error:errors.append(error)
        if errors:raise RuntimeError('helper cleanup unconfirmed') from errors[0]
        self.closed=True
        return True
