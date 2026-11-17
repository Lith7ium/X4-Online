"""Read one explicitly granted client-X4 motion track over owned local UDP.

The caller completes the existing source-motion binding handshake first and
owns the client process, grant, PID/socket validation and failure fencing. This
diagnostic neither changes X4 nor grants authority, sends acknowledgements,
or asserts that the local actor is identical to a server actor.
"""
import math
import re
import select
import socket
import threading
import time

from .experimental_source_job_bridge import _SOCKET_LOCK, _SOCKET_OWNERS
from .experimental_tcp_motion import motion_value

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_NUMBER=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
_MAX=9007199254740991
_PACKET=768
_INDEX=1318
_BASELINE=10054
_SECTOR='cluster_115_sector001_macro'


class ExperimentalClientAuthorityMotionIPC:
    """Exclusive synchronous request owner, fenced after every uncertainty."""
    def __init__(self,sock,*,enabled=False,lease,attempt,epoch,generation,incarnation,
                 guard,validate_peer,grant,timeout=20,include_orientation=False):
        tokens=(lease,attempt,epoch,generation,incarnation)
        if (enabled is not True or type(sock) is not socket.socket or sock.family!=socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            sock.getsockname()[0]!='127.0.0.1' or not sock.getsockname()[1] or
            any(type(v) is not str or not _TOKEN.fullmatch(v) for v in tokens) or len(set(tokens))!=len(tokens) or
            not all(callable(f) for f in (guard,validate_peer,grant)) or type(include_orientation) is not bool or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120):
            raise ValueError('invalid client authority motion context')
        peer=sock.getpeername()
        if peer[0]!='127.0.0.1' or not peer[1]:raise ValueError('connected loopback peer required')
        with _SOCKET_LOCK:
            if sock in _SOCKET_OWNERS:raise ValueError('UDP socket already owned')
            sock.setblocking(False);_SOCKET_OWNERS[sock]=True
        self._sock=sock;self._peer=peer;self._local=sock.getsockname()
        self._lease=lease;self._attempt=attempt;self._epoch=epoch;self._generation=generation;self._incarnation=incarnation
        self._guard=guard;self._validate=validate_peer;self._grant=grant;self._timeout=float(timeout)
        self._include_orientation=include_orientation
        self._owner=threading.get_ident();self._state='new';self._next=0;self._sequence=0;self._last_time=None
    @property
    def state(self):return self._state
    def _fail(self):
        self._state='failed'
        try:self._sock.close()
        except OSError:pass
    def _check(self, deadline, phase):
        original_socket = self._sock
        original_guard = self._guard
        original_peer_validator = self._validate
        original_grant = self._grant
        original_context = (self._peer, self._local, self._lease, self._attempt, self._epoch,
                            self._generation, self._incarnation, self._timeout, self._owner,
                            self._next, self._sequence, self._last_time, self._include_orientation)

        def context_unchanged():
            current_context = (self._peer, self._local, self._lease, self._attempt, self._epoch,
                               self._generation, self._incarnation, self._timeout, self._owner,
                               self._next, self._sequence, self._last_time, self._include_orientation)
            return (self._sock is original_socket and self._guard is original_guard and
                    self._validate is original_peer_validator and self._grant is original_grant and
                    current_context == original_context and
                    all(type(current) is type(original) for current, original in zip(current_context, original_context)) and
                    self._state == phase and threading.get_ident() == self._owner and
                    time.monotonic() < deadline and self._sock.getsockname() == self._local and
                    self._sock.getpeername() == self._peer)

        if not context_unchanged():
            raise RuntimeError('client motion state or deadline changed')
        if self._guard() is not True or not context_unchanged():
            raise RuntimeError('client process guard failed')
        if self._validate(self._peer) is not True or not context_unchanged():
            raise RuntimeError('client UDP peer changed')
        if self._grant(self._epoch, self._generation, self._incarnation, _INDEX) is not True or not context_unchanged():
            raise RuntimeError('client test grant unavailable')
        if self._guard() is not True or not context_unchanged():
            raise RuntimeError('client process guard changed')
        if self._validate(self._peer) is not True or not context_unchanged():
            raise RuntimeError('client UDP peer changed')
        if self._grant(self._epoch, self._generation, self._incarnation, _INDEX) is not True or not context_unchanged():
            raise RuntimeError('client test grant changed')

    def _quiet(self, deadline, phase):
        self._check(deadline, phase)
        readable, _, exceptional = select.select([self._sock], [], [self._sock], 0)
        if readable or exceptional:
            raise RuntimeError('unexpected queued client motion packet')
        self._check(deadline, phase)

    def _request(self,kind,fields,deadline,phase):
        self._quiet(deadline,phase)
        if self._next>=_MAX:raise RuntimeError('client motion request capacity')
        self._next+=1;request=str(self._next)
        payload='|'.join(['P',self._lease,self._attempt,kind,self._epoch,self._generation,request,*fields]).encode('ascii')
        if self._sock.send(payload)!=len(payload):raise RuntimeError('client motion dispatch failed')
        while True:
            self._check(deadline,phase)
            readable,_,bad=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
            self._check(deadline,phase)
            if bad:raise RuntimeError('client motion socket error')
            if readable:break
        raw=self._sock.recv(_PACKET+1)
        if not raw or len(raw)>_PACKET:raise ValueError('invalid client motion packet')
        self._check(deadline,phase)
        try:parts=raw.decode('ascii').split('|')
        except UnicodeError:raise ValueError('invalid client motion encoding') from None
        return request,parts
    def register_saved(self):
        if self._state!='new' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('client motion registration unavailable')
        self._state='registering';deadline=time.monotonic()+self._timeout
        try:
            request,parts=self._request('REGISTER_SAVED',[str(_INDEX),str(_BASELINE)],deadline,'registering')
            if parts!=['S',self._lease,self._attempt,'SAVED_REGISTERED',self._epoch,self._generation,request,str(_INDEX),str(_BASELINE)]:
                raise ValueError('client motion registration mismatch')
            self._quiet(deadline,'registering');self._state='ready';return True
        except BaseException:self._fail();raise
    def pull(self):
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('client motion pull unavailable')
        self._state='pulling';deadline=time.monotonic()+self._timeout
        try:
            request,parts=self._request('PULL',[],deadline,'pulling')
            prefix=['S',self._lease,self._attempt]
            if parts==prefix+['NO_SAMPLE',self._epoch,self._generation,request]:
                self._quiet(deadline,'pulling');self._state='ready';return None
            kind='SAMPLE2' if self._include_orientation else 'SAMPLE'
            if len(parts)!=(23 if self._include_orientation else 17) or parts[:7]!=prefix+[kind,self._epoch,self._generation,request]:
                raise ValueError('client motion response mismatch')
            if parts[7]!=str(_INDEX) or not re.fullmatch(r'[1-9][0-9]{0,15}',parts[8]):
                raise ValueError('client motion identity invalid')
            numbers=parts[10:14]
            orientation=parts[14:17] if self._include_orientation else []
            vel=parts[17:20] if self._include_orientation else parts[14:17]
            angular=parts[20:23] if self._include_orientation else []
            fields=numbers+orientation+([] if vel==['-','-','-'] else vel)+([] if angular==['-','-','-'] else angular)
            if any(len(v)>32 or not _NUMBER.fullmatch(v) for v in fields):raise ValueError('client motion number invalid')
            t,x,y,z=map(float,numbers);rate=None if vel==['-','-','-'] else dict(zip(('x','y','z'),map(float,vel)))
            sample={'version':2 if self._include_orientation else 1,'epoch':self._epoch,'generation':self._generation,'index':_INDEX,
                'sequence':int(parts[8]),'sector_macro':parts[9],'source_time':t,'x':x,'y':y,'z':z,'velocity':rate}
            if self._include_orientation:
                sample['orientation']=dict(zip(('yaw','pitch','roll'),map(float,orientation)))
                sample['angular_rate']=None if angular==['-','-','-'] else dict(zip(('yaw','pitch','roll'),map(float,angular)))
            value=motion_value(sample)
            if (value['sector_macro']!=_SECTOR or value['sequence']!=self._sequence+1 or
                (self._last_time is not None and value['source_time']<=self._last_time) or
                (self._sequence==0 and value['velocity'] is not None)):
                raise ValueError('client motion stale or foreign sample')
            self._quiet(deadline,'pulling');self._sequence=value['sequence'];self._last_time=value['source_time']
            self._state='ready';return value
        except BaseException:self._fail();raise
    def close(self):
        if threading.get_ident()!=self._owner or self._state not in ('new','ready'):
            self._fail();raise RuntimeError('client motion cannot close')
        self._state='closed'
        with _SOCKET_LOCK:_SOCKET_OWNERS.pop(self._sock,None)
        self._sock.close()
