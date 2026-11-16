"""Pull one X4 source motion sample over owned loopback UDP into admitted TCP.

The caller binds/validates the source socket using its PID/inode guard before
construction, confirms registry lifetimes separately, and owns all processes,
profile locks and failure fencing. This bridge does not start X4 or a listener.
"""
import copy
import math
import re
import select
import socket
import threading
import time
from .experimental_source_job_bridge import _SOCKET_OWNERS, _SOCKET_LOCK
from .experimental_tcp_motion import ExperimentalTCPMotion, motion_value, motion_digest

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_NUMBER=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
_MAX_PACKET=768
_MAX=9007199254740991

class ExperimentalSourceMotionIPC:
    """One request at a time; no next pull until TCP recipients confirm."""
    def __init__(self,sock,motion,*,enabled=False,lease,attempt,epoch,generation,guard,validate_peer,timeout=30,validate_sample=None):
        if (enabled is not True or type(sock) is not socket.socket or sock.family!=socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            sock.getsockname()[0]!='127.0.0.1' or not sock.getsockname()[1] or
            type(motion) is not ExperimentalTCPMotion or
            any(type(x) is not str or not _TOKEN.fullmatch(x) for x in (lease,attempt,epoch,generation)) or
            len({lease,attempt,epoch,generation})!=4 or not callable(guard) or not callable(validate_peer) or
            (validate_sample is not None and not callable(validate_sample)) or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=300 or
            timeout<=motion._delivery._timeout):
            raise ValueError('invalid source motion IPC')
        peer=sock.getpeername()
        if peer[0]!='127.0.0.1' or not peer[1]:raise ValueError('connected source loopback peer required')
        if getattr(motion,'_source_owner',None) is not None:raise ValueError('motion owner already has a source')
        with _SOCKET_LOCK:
            if sock in _SOCKET_OWNERS:raise ValueError('source UDP socket already owned')
            sock.setblocking(False);_SOCKET_OWNERS[sock]=True
        self._sock=sock;self._peer=peer;self._local=sock.getsockname();self._motion=motion
        self._lease=lease;self._attempt=attempt;self._epoch=epoch;self._generation=generation
        self._guard=guard;self._validate=validate_peer;self._validate_sample=validate_sample;self._timeout=float(timeout)
        self._state='ready';self._owner=threading.get_ident();self._next=0;self._indices=set();self._scheduler_owner=None;self._scheduler_lease=None
        self._last_pull=None
        motion._source_owner=self
    @property
    def state(self):return self._state
    def _fail(self):
        self._state='failed';self._motion._failed=True
        self._motion._delivery._failed=True;self._motion._delivery._host._failed=True
        try:self._sock.close()
        except OSError:pass
    def _check(self,deadline,phase):
        if (self._state!=phase or self._motion._failed or self._motion._delivery._failed or
            self._motion._delivery._host._failed or threading.get_ident()!=self._owner or time.monotonic()>=deadline):
            raise RuntimeError('source motion state or deadline failed')
        good=self._guard()
        if (good is not True or self._state!=phase or self._motion._failed or self._motion._delivery._failed or
            self._motion._delivery._host._failed or threading.get_ident()!=self._owner or
            time.monotonic()>=deadline or self._sock.getsockname()!=self._local or self._sock.getpeername()!=self._peer):
            raise RuntimeError('source motion guard failed')
        good=self._validate(self._peer)
        if (good is not True or self._state!=phase or self._motion._failed or self._motion._delivery._failed or
            self._motion._delivery._host._failed or threading.get_ident()!=self._owner or time.monotonic()>=deadline):
            raise RuntimeError('source motion X4 peer ownership changed')
    def _quiet(self,deadline,phase):
        self._check(deadline,phase);r,_,e=select.select([self._sock],[],[self._sock],0)
        if r or e:raise RuntimeError('unexpected queued source motion packet')
        self._check(deadline,phase)
    def _reserved(self,owner):
        if self._scheduler_owner is not None and (owner is None or owner is not self._scheduler_lease):
            self._fail();raise RuntimeError('source motion bridge is reserved by its scheduler')
    def _motion_call(self,fn,*args,**kwargs):
        lease=object();self._motion._source_lease=lease
        try:return fn(*args,_source=lease,**kwargs)
        finally:self._motion._source_lease=None
    def bind_confirmed(self,index,*,_scheduler=None):
        """Caller asserts a source event was confirmed by the real job owner."""
        self._reserved(_scheduler)
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('source motion registration unavailable')
        self._state='registering';deadline=time.monotonic()+self._timeout
        try:
            self._check(deadline,'registering')
            self._motion_call(self._motion.track,self._epoch,self._generation,index)
            self._check(deadline,'registering');self._indices.add(index);self._state='ready';return True
        except BaseException:self._fail();raise
    def pull(self,*,_scheduler=None):
        self._reserved(_scheduler)
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('source motion reentrant or unavailable')
        self._state='pulling';deadline=time.monotonic()+self._timeout
        try:
            # Respect the maximum per-track TCP send frequency even if the X4
            # sampler returns the same track on two consecutive pulls.
            while self._last_pull is not None and time.monotonic()-self._last_pull<self._motion._min_interval:
                self._check(deadline,'pulling')
                select.select([],[],[],max(0,min(.01,self._motion._min_interval-(time.monotonic()-self._last_pull))))
            self._quiet(deadline,'pulling')
            if self._next>=_MAX:raise RuntimeError('source motion request capacity')
            self._next+=1;request=str(self._next)
            packet='|'.join(['P',self._lease,self._attempt,'PULL',self._epoch,self._generation,request]).encode('ascii')
            if self._sock.send(packet)!=len(packet):raise RuntimeError('source motion pull failed')
            while True:
                self._check(deadline,'pulling')
                r,_,e=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
                self._check(deadline,'pulling')
                if e:raise RuntimeError('source motion socket error')
                if r:break
            data=self._sock.recv(_MAX_PACKET+1)
            if not data or len(data)>_MAX_PACKET:raise ValueError('invalid source motion response')
            try:parts=data.decode('ascii').split('|')
            except UnicodeError:raise ValueError('invalid source motion encoding') from None
            prefix=['S',self._lease,self._attempt]
            if parts==prefix+['NO_SAMPLE',self._epoch,self._generation,request]:
                self._quiet(deadline,'pulling');self._last_pull=time.monotonic();self._state='ready';return None
            if len(parts)!=17 or parts[:7]!=prefix+['SAMPLE',self._epoch,self._generation,request]:
                raise ValueError('foreign source motion response')
            index,sequence=parts[7:9]
            if not re.fullmatch(r'[1-9][0-9]*',index) or not re.fullmatch(r'[1-9][0-9]*',sequence):
                raise ValueError('invalid motion identity')
            if int(index) not in self._indices:raise ValueError('unconfirmed source motion index')
            numbers=parts[10:14];velocity=parts[14:17]
            fields=numbers+([] if velocity==['-','-','-'] else velocity)
            if any(len(item)>32 or not _NUMBER.fullmatch(item) for item in fields):
                raise ValueError('invalid source motion numeric syntax')
            try:
                t,x,y,z=map(float,numbers)
                v=None if velocity==['-','-','-'] else dict(zip(('x','y','z'),map(float,velocity)))
            except ValueError:raise ValueError('invalid source motion number') from None
            value=motion_value({'version':1,'epoch':self._epoch,'generation':self._generation,
                'index':int(index),'sequence':int(sequence),'sector_macro':parts[9],
                'source_time':t,'x':x,'y':y,'z':z,'velocity':v})
            if self._validate_sample is not None:
                candidate=copy.deepcopy(value);self._check(deadline,'pulling')
                accepted=self._validate_sample(candidate)
                self._check(deadline,'pulling')
                if accepted is not True or motion_digest(candidate)!=motion_digest(value):
                    raise ValueError('source motion pre-send validation failed')
            self._quiet(deadline,'pulling')
            if self._motion_call(self._motion.send,value,guard=lambda:self._check(deadline,'pulling') or True) is not True:
                raise RuntimeError('motion TCP not confirmed')
            self._quiet(deadline,'pulling');self._last_pull=time.monotonic();self._state='ready';return value
        except BaseException:self._fail();raise
    def close(self,*,_scheduler=None):
        self._reserved(_scheduler)
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('source motion cannot close')
        self._state='closed'
        with _SOCKET_LOCK:_SOCKET_OWNERS.pop(self._sock,None)
        self._sock.close()
