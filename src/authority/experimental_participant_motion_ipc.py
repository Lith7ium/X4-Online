"""Opt-in participant TCP -> local X4 motion-binding IPC.

An X4 onUpdate owner must answer only after its correlated asynchronous MD/FFI
binding returns successfully. A separately enabled one-shot request can ask
the X4 owner to apply the last bound sample and report a later local readback.
The caller owns the process, profile lock and failure fencing.
"""
import math
import re
import secrets
import select
import socket
import threading
import time
from .experimental_participant_job_ipc import _OWNERS, _LOCK
from .experimental_tcp_motion import motion_value, motion_digest

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_MAX_PACKET=768

class ExperimentalParticipantMotionIPC:
    """One exclusive loopback UDP socket, bound to one sampled X4 peer.

    Supply as the participant client's synchronous ``apply_motion`` callback.
    The separate X4 update owner performs MD/FFI work asynchronously while
    this callback waits. Its deadline must be strictly shorter than TCP's.
    """
    def __init__(self,sock,*,enabled=False,lease,attempt,epoch,generation,guard,validate_peer,timeout=20,allow_apply=False,observe_limit=None):
        if (enabled is not True or type(sock) is not socket.socket or sock.family!=socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            sock.getsockname()[0]!='127.0.0.1' or not sock.getsockname()[1] or
            any(type(x) is not str or not _TOKEN.fullmatch(x) for x in (lease,attempt,epoch,generation)) or
            len({lease,attempt,epoch,generation})!=4 or type(allow_apply) is not bool or
            (observe_limit is not None and (type(observe_limit) is not int or not 2<=observe_limit<=8 or allow_apply)) or
            not callable(guard) or not callable(validate_peer) or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=300):
            raise ValueError('invalid participant motion IPC context')
        try:sock.getpeername()
        except OSError:pass
        else:raise ValueError('unconnected UDP socket required')
        with _LOCK:
            if sock in _OWNERS:raise ValueError('UDP socket already owned')
            sock.setblocking(False);_OWNERS[sock]=True
        self._sock=sock;self._lease=lease;self._attempt=attempt;self._epoch=epoch;self._generation=generation
        self._guard=guard;self._validate=validate_peer;self._timeout=float(timeout)
        self._owner=threading.get_ident();self._state='new';self._peer=None
        self._prefix=secrets.token_hex(8);self._next=0
        self._allow_apply=allow_apply;self._observe_limit=observe_limit;self._observed=0;self._bound=None;self._apply_attempted=False
        self._preflight_ready=None;self._preflight_seen=set()
    @property
    def state(self):return self._state
    def _fail(self):
        self._state='failed'
        try:self._sock.close()
        except OSError:pass
    def _check(self,deadline,phase):
        if self._state!=phase or threading.get_ident()!=self._owner or time.monotonic()>=deadline:
            raise RuntimeError('motion IPC state or deadline failed')
        good=self._guard()
        if good is not True or self._state!=phase or threading.get_ident()!=self._owner or time.monotonic()>=deadline:
            raise RuntimeError('motion IPC guard failed')
        if self._peer is not None:
            good=self._validate(self._peer)
            if good is not True or self._state!=phase or threading.get_ident()!=self._owner or time.monotonic()>=deadline:
                raise RuntimeError('motion X4 peer ownership changed')
    def _recv(self,deadline,phase,unconnected=False):
        while True:
            self._check(deadline,phase)
            ready,_,bad=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
            self._check(deadline,phase)
            if bad:raise RuntimeError('motion IPC socket failure')
            if ready:
                if unconnected:data,peer=self._sock.recvfrom(_MAX_PACKET+1)
                else:data,peer=self._sock.recv(_MAX_PACKET+1),self._peer
                if not data or len(data)>_MAX_PACKET:raise ValueError('invalid motion IPC packet')
                self._check(deadline,phase);return data,peer
    def _quiet(self,deadline,phase):
        self._check(deadline,phase);r,_,e=select.select([self._sock],[],[self._sock],0)
        if r or e:raise RuntimeError('unexpected queued motion IPC response')
        self._check(deadline,phase)
    def wait_ready(self):
        if self._state!='new' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('invalid motion IPC ready state')
        self._state='binding';deadline=time.monotonic()+self._timeout
        try:
            data,peer=self._recv(deadline,'binding',True)
            if data!=f'R|{self._lease}|{self._attempt}|READY|{self._epoch}|{self._generation}'.encode('ascii') or peer[0]!='127.0.0.1' or not peer[1]:
                raise ValueError('foreign motion READY')
            self._check(deadline,'binding');good=self._validate(peer);self._check(deadline,'binding')
            if good is not True:raise RuntimeError('motion peer ownership unconfirmed')
            self._sock.connect(peer);self._peer=peer;self._quiet(deadline,'binding');self._state='ready';return True
        except BaseException:self._fail();raise
    def __call__(self,raw,despawn):
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('motion IPC reentrant or unavailable')
        self._state='applying';deadline=time.monotonic()+self._timeout
        try:
            if despawn is not False:raise ValueError('X4 despawn binding unavailable')
            value=motion_value(raw)
            if value['epoch']!=self._epoch or value['generation']!=self._generation:
                raise ValueError('foreign motion identity')
            if self._next>=0xffffffffffffffff:raise RuntimeError('motion request capacity')
            self._next+=1;request=self._prefix+format(self._next,'016x');digest=motion_digest(value)
            fields=[request,value['epoch'],value['generation'],str(value['index']),str(value['sequence']),value['sector_macro'],digest]
            velocity=value['velocity']
            vector=['-','-','-'] if velocity is None else [format(velocity[k],'.17g') for k in ('x','y','z')]
            numeric=[format(value[k],'.17g') for k in ('source_time','x','y','z')]
            payload='|'.join(['M',self._lease,self._attempt,'BIND',*fields,*numeric,*vector]).encode('ascii')
            if len(payload)>_MAX_PACKET:raise ValueError('motion IPC packet too large')
            self._quiet(deadline,'applying')
            if self._sock.send(payload)!=len(payload):raise RuntimeError('motion IPC send failed')
            self._check(deadline,'applying');data,_=self._recv(deadline,'applying')
            expected='|'.join(['R',self._lease,self._attempt,'BOUND',*fields]).encode('ascii')
            if data!=expected:raise ValueError('motion IPC binding response mismatch')
            self._quiet(deadline,'applying')
            self._bound=(value['epoch'],value['generation'],value['index'],value['sequence'],digest)
            self._preflight_ready=None
            self._state='ready';return True
        except BaseException:self._fail();raise
    def preflight(self,raw):
        """Inspect the last bound sample without applying it; return NEAR or READY.

        READY is a provisional local observation, not clearance or a guarantee
        that the later guarded setter will still succeed. No request is retried.
        """
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('motion IPC reentrant or unavailable')
        self._state='preflighting';deadline=time.monotonic()+self._timeout
        try:
            if (not (self._allow_apply or self._observe_limit is not None) or self._apply_attempted or
                self._bound is None or (self._observe_limit is not None and self._observed>=self._observe_limit)):
                raise RuntimeError('motion preflight unavailable')
            value=motion_value(raw);digest=motion_digest(value)
            identity=(value['epoch'],value['generation'],value['index'],value['sequence'],digest)
            if identity!=self._bound:raise ValueError('motion preflight differs from last bound sample')
            key=identity[:4]
            if key in self._preflight_seen or len(self._preflight_seen)>=100000:
                raise ValueError('replayed or full motion preflight')
            if self._next>=0xffffffffffffffff:raise RuntimeError('motion request capacity')
            self._preflight_seen.add(key);self._preflight_ready=None
            self._next+=1;request=self._prefix+format(self._next,'016x')
            fields=[request,value['epoch'],value['generation'],str(value['index']),str(value['sequence']),digest]
            payload='|'.join(['M',self._lease,self._attempt,'PREFLIGHT',*fields]).encode('ascii')
            self._quiet(deadline,'preflighting')
            if self._sock.send(payload)!=len(payload):raise RuntimeError('motion preflight send failed')
            self._check(deadline,'preflighting');data,_=self._recv(deadline,'preflighting')
            prefix='|'.join(['R',self._lease,self._attempt,'PREFLIGHTED',*fields]).encode('ascii')
            if data==prefix+b'|NEAR':result='NEAR'
            elif data==prefix+b'|READY':result='READY'
            else:raise ValueError('motion preflight response mismatch')
            self._quiet(deadline,'preflighting')
            if result=='READY':self._preflight_ready=identity
            self._state='ready';return result
        except BaseException:self._fail();raise
    def apply_once(self,raw):
        """Ask for one local pose application of the last successfully bound sample.

        A successful response is the owner's correlated readback assertion. The
        call cannot reverse an uncertain game-side write on error or timeout.
        """
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('motion IPC reentrant or unavailable')
        self._state='writing';deadline=time.monotonic()+self._timeout
        try:
            if not self._allow_apply or self._apply_attempted or self._bound is None:
                raise RuntimeError('motion apply unavailable')
            self._apply_attempted=True
            value=motion_value(raw);digest=motion_digest(value)
            identity=(value['epoch'],value['generation'],value['index'],value['sequence'],digest)
            if identity!=self._bound or identity!=self._preflight_ready:
                raise ValueError('motion apply lacks current READY preflight')
            self._preflight_ready=None
            if self._next>=0xffffffffffffffff:raise RuntimeError('motion request capacity')
            self._next+=1;request=self._prefix+format(self._next,'016x')
            fields=[request,value['epoch'],value['generation'],str(value['index']),str(value['sequence']),digest]
            payload='|'.join(['M',self._lease,self._attempt,'APPLY',*fields]).encode('ascii')
            self._quiet(deadline,'writing')
            if self._sock.send(payload)!=len(payload):raise RuntimeError('motion apply send failed')
            self._check(deadline,'writing');data,_=self._recv(deadline,'writing')
            expected='|'.join(['R',self._lease,self._attempt,'APPLIED',*fields]).encode('ascii')
            if data!=expected:raise ValueError('motion apply response mismatch')
            self._quiet(deadline,'writing');self._state='ready';return True
        except BaseException:self._fail();raise
    def observe(self,raw):
        """Request one correlated immediate measurement after a guarded write.

        The reply is a point observation, not proof of continuing agreement.
        Error or timeout leaves any game-side write uncertain; never retry.
        """
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('motion IPC reentrant or unavailable')
        self._state='observing';deadline=time.monotonic()+self._timeout
        try:
            if self._observe_limit is None or self._observed>=self._observe_limit or self._bound is None:
                raise RuntimeError('motion observe unavailable')
            value=motion_value(raw);digest=motion_digest(value)
            identity=(value['epoch'],value['generation'],value['index'],value['sequence'],digest)
            if identity!=self._bound or identity!=self._preflight_ready:
                raise ValueError('motion observe lacks current READY preflight')
            self._preflight_ready=None
            if self._next>=0xffffffffffffffff:raise RuntimeError('motion request capacity')
            self._next+=1;request=self._prefix+format(self._next,'016x')
            fields=[request,value['epoch'],value['generation'],str(value['index']),str(value['sequence']),digest]
            payload='|'.join(['M',self._lease,self._attempt,'OBSERVE',*fields]).encode('ascii')
            self._quiet(deadline,'observing')
            if self._sock.send(payload)!=len(payload):raise RuntimeError('motion observe send failed')
            self._check(deadline,'observing');data,_=self._recv(deadline,'observing')
            expected='|'.join(['R',self._lease,self._attempt,'OBSERVED',*fields]).encode('ascii')
            if data!=expected:raise ValueError('motion observe response mismatch')
            self._quiet(deadline,'observing');self._observed+=1;self._state='ready';return True
        except BaseException:self._fail();raise
    def close(self):
        if threading.get_ident()!=self._owner or self._state not in ('new','ready'):
            self._fail();raise RuntimeError('motion IPC cannot close')
        self._state='closed'
        with _LOCK:_OWNERS.pop(self._sock,None)
        self._sock.close()
