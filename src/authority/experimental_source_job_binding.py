"""Bind one opted-in X4 source UDP peer before a supervisor permits resume.

No socket or process is created here. The validator is an explicit caller
assertion; ownership, process lifecycle, and same-user isolation remain external.
"""
import math
import re
import select
import socket
import threading
import time

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_MAX=768
from .experimental_source_job_bridge import _SOCKET_OWNERS as _OWNED, _SOCKET_LOCK as _LOCK


class ExperimentalSourceJobBinding:
    """One loopback source socket, HELLO/BOUND/ATTACHED and one handoff.

    By default the caller must keep the source X4 paused until bind and handoff
    succeed. The explicit running_diagnostic mode requires the caller to fence
    the running world and its owned client through the entire handoff.
    `validate_peer` must independently check the sampled peer
    against the exact owned X4 PID/start-time and socket inode. The HELLO and
    local UDP are correlation only, not process authentication or encryption.
    """
    def __init__(self, sock, *, enabled=False, lease, attempt, epoch, generation,
                 guard, validate_peer, timeout=30, running_diagnostic=False):
        if (enabled is not True or type(sock) is not socket.socket or sock.family!=socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            sock.getsockname()[0]!='127.0.0.1' or not sock.getsockname()[1] or
            any(type(x) is not str or not _TOKEN.fullmatch(x) for x in (lease,attempt,epoch,generation)) or
            len({lease,attempt,epoch,generation})!=4 or not callable(guard) or not callable(validate_peer) or
            type(running_diagnostic) is not bool or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or
            not 0<timeout<=(120 if running_diagnostic else 300)):
            raise ValueError('enabled bound loopback source socket and context required')
        try:sock.getpeername()
        except OSError:pass
        else:raise ValueError('source socket must initially be unconnected')
        with _LOCK:
            if sock in _OWNED:raise ValueError('source socket already reserved')
            sock.setblocking(False);_OWNED[sock]=True
        self._sock=sock;self._guard=guard;self._validate_peer=validate_peer;self._timeout=float(timeout)
        self._owner=threading.get_ident();self._phase='new';self._peer=None
        suffix='|'+epoch+'|'+generation
        self._hello=('S|'+lease+'|'+attempt+'|HELLO'+suffix).encode('ascii')
        self._bound=('P|'+lease+'|'+attempt+'|BOUND'+suffix).encode('ascii')
        self._attached=('S|'+lease+'|'+attempt+'|ATTACHED'+suffix).encode('ascii')

    @property
    def state(self):return self._phase

    def _fail(self):
        self._phase='failed'
        try:self._sock.close()
        except OSError:pass

    def _check(self,deadline,phase):
        if threading.get_ident()!=self._owner or self._phase!=phase or time.monotonic()>=deadline:
            raise RuntimeError('source binding unavailable')
        result=self._guard()
        if result is not True or threading.get_ident()!=self._owner or self._phase!=phase or time.monotonic()>=deadline:
            raise RuntimeError('source guard or deadline failed')

    def _peer_check(self,peer,deadline,phase):
        self._check(deadline,phase)
        valid=self._validate_peer(peer)
        self._check(deadline,phase)
        if valid is not True:raise RuntimeError('source UDP peer ownership unconfirmed')

    def _quiet(self,deadline,phase):
        self._check(deadline,phase)
        readable,_,bad=select.select([self._sock],[],[self._sock],0)
        if readable or bad:raise RuntimeError('unexpected source packet while binding')
        self._check(deadline,phase)

    def bind(self):
        if self._phase=='handed_off':raise RuntimeError('source socket already handed off')
        if threading.get_ident()!=self._owner or self._phase!='new':
            self._fail();raise RuntimeError('source bind requires fresh owner')
        self._phase='binding';deadline=time.monotonic()+self._timeout
        try:
            while True:
                self._check(deadline,'binding')
                readable,_,bad=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
                self._check(deadline,'binding')
                if bad:raise RuntimeError('source socket error')
                if readable:break
            data,peer=self._sock.recvfrom(_MAX+1)
            self._check(deadline,'binding')
            if data!=self._hello or peer[0]!='127.0.0.1' or not peer[1]:raise ValueError('foreign source HELLO')
            self._peer_check(peer,deadline,'binding')
            self._sock.connect(peer);self._peer=peer
            self._quiet(deadline,'binding');self._peer_check(peer,deadline,'binding')
            if self._sock.send(self._bound)!=len(self._bound):raise RuntimeError('source BOUND dispatch failed')
            self._peer_check(peer,deadline,'binding')
            while True:
                self._check(deadline,'binding')
                readable,_,bad=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
                self._check(deadline,'binding')
                if bad:raise RuntimeError('source socket error')
                if readable:break
            data=self._sock.recv(_MAX+1)
            self._peer_check(peer,deadline,'binding')
            if data!=self._attached:raise ValueError('foreign source ATTACHED')
            self._quiet(deadline,'binding');self._peer_check(peer,deadline,'binding')
            self._phase='bound';return True
        except BaseException:
            self._fail();raise

    def handoff(self):
        if self._phase=='handed_off':raise RuntimeError('source socket already handed off')
        if threading.get_ident()!=self._owner or self._phase!='bound':
            self._fail();raise RuntimeError('source binding not ready')
        self._phase='handoff';deadline=time.monotonic()+self._timeout
        try:
            self._peer_check(self._peer,deadline,'handoff');self._quiet(deadline,'handoff')
            if self._sock.getpeername()!=self._peer:raise RuntimeError('source UDP peer changed')
            self._peer_check(self._peer,deadline,'handoff')
            with _LOCK:_OWNED.pop(self._sock,None)
            self._phase='handed_off';return self._sock
        except BaseException:
            self._fail();raise

    def close(self):
        if threading.get_ident()!=self._owner or self._phase not in ('new','bound'):
            raise RuntimeError('source binding cannot close in this state')
        self._phase='closed'
        with _LOCK:_OWNED.pop(self._sock,None)
        self._sock.close()
