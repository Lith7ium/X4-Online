"""Bounded source-X4 UDP to admitted TCP job bridge; no sockets opened on import.

The caller owns one connected loopback UDP socket and all X4/session lifetimes.
The source gate protocol is experimental; no X4 adapter is installed here.
"""
import math
import re
import select
import socket
import threading
import time
import weakref

from .experimental_tcp_job_delivery import ExperimentalTCPJobDelivery, job_event

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_INT=re.compile(r'[1-9][0-9]{0,15}\Z')
_PEER=re.compile(r'peer_[1-9][0-9]{0,15}\Z')
_MAX_PACKET=4096
_SOCKET_OWNERS=weakref.WeakKeyDictionary()
_SOCKET_LOCK=threading.Lock()


class ExperimentalSourceJobBridge:
    """One source event at a time; uncertain delivery permanently fences host.

    `run_one` owns both the UDP read and host TCP delivery synchronously.
    No callback from TCP sends a source receipt; source receipts are sent only
    after all network exchanges complete, their reader lease is released and
    membership/liveness is rechecked. Source-gate state and actual MD Acked
    remain separate remote assertions.
    """
    def __init__(self, delivery, sock, *, enabled=False, lease, attempt, epoch, generation, guard, timeout=30):
        if (enabled is not True or type(delivery) is not ExperimentalTCPJobDelivery or
            type(sock) is not socket.socket or sock.family!=socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            sock.getsockname()[0]!='127.0.0.1' or sock.getpeername()[0]!='127.0.0.1' or
            any(type(x) is not str or not _TOKEN.fullmatch(x) for x in (lease,attempt,epoch,generation)) or
            len({lease,attempt,epoch,generation})!=4 or not callable(guard) or
            type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=300):
            raise ValueError('invalid enabled local source bridge')
        delivery._host._check()
        with _SOCKET_LOCK:
            if sock in _SOCKET_OWNERS:raise ValueError('source socket already bound to a bridge')
            sock.setblocking(False);_SOCKET_OWNERS[sock]=True
        self._delivery=delivery;self._sock=sock;self._lease=lease;self._attempt=attempt
        self._epoch=epoch;self._generation=generation;self._guard=guard;self._timeout=float(timeout)
        self._state='idle';self._owner=threading.get_ident();self._last=0;self._last_members=None

    @property
    def state(self):return self._state

    def _check(self, deadline):
        if threading.get_ident()!=self._owner or self._state in ('failed','closed') or time.monotonic()>=deadline:
            raise RuntimeError('source bridge unavailable')
        state=self._state
        host=self._delivery._host;host._check();host._control._reader_free()
        lease=object();host._busy=True;host._control._reader_lease=lease
        try:
            valid=self._guard()
        finally:
            changed=host._control._reader_lease is not lease or host._busy is not True
            if host._control._reader_lease is lease:host._control._reader_lease=None
            host._busy=False
            if changed:
                host._failed=True
                raise RuntimeError('source guard changed exclusive socket ownership')
        if (time.monotonic()>=deadline or valid is not True or
                self._state!=state or time.monotonic()>=deadline):
            raise RuntimeError('source context or deadline failed')

    def _membership(self, expected, deadline):
        self._check(deadline)
        if not self._delivery._host._control.ready_for_resume():raise RuntimeError('participant socket not quiet')
        members=self._delivery.membership()
        if expected is not None and members!=expected:raise RuntimeError('membership changed')
        self._check(deadline)
        return members

    def _recv(self, deadline):
        while True:
            self._check(deadline)
            readable,_,bad=select.select([self._sock],[],[self._sock],min(.1,max(0,deadline-time.monotonic())))
            self._check(deadline)
            if bad:raise RuntimeError('source socket error')
            if readable:
                data=self._sock.recv(_MAX_PACKET+1)
                if not data or len(data)>_MAX_PACKET:raise ValueError('invalid source packet size')
                try:parts=data.decode('ascii').split('|')
                except UnicodeError:raise ValueError('invalid source packet') from None
                if parts[:3]!=['S',self._lease,self._attempt]:raise ValueError('foreign source context')
                return parts[3:]

    def _send(self, body, deadline):
        self._check(deadline)
        raw='|'.join(('P',self._lease,self._attempt,*body)).encode('ascii')
        if len(raw)>_MAX_PACKET or self._sock.send(raw)!=len(raw):raise RuntimeError('source send unconfirmed')
        self._check(deadline)

    def _quiet(self, deadline):
        self._check(deadline)
        readable,_,bad=select.select([self._sock],[],[self._sock],0)
        if readable or bad:raise RuntimeError('unexpected queued source packet')
        self._check(deadline)

    def run_one(self, *, allow_finished=False):
        if type(allow_finished) is not bool:raise ValueError('invalid completion option')
        if threading.get_ident()!=self._owner or self._state!='idle':
            self._state='failed';raise RuntimeError('source bridge reentrant or unavailable')
        deadline=time.monotonic()+self._timeout;self._state='candidate'
        try:
            body=self._recv(deadline)
            if body and body[0]=='FINISHED':
                if (not allow_finished or len(body)!=4 or body[1]!=self._epoch or
                    body[2]!=self._generation or body[3]!=str(self._last)):
                    raise ValueError('invalid source completion')
                members=self._membership(self._last_members,deadline)
                if not members:raise RuntimeError('no admitted participant at source completion')
                self._quiet(deadline);self._membership(members,deadline)
                self._state='finished'
                return None
            if len(body)!=11 or body[0]!='CANDIDATE':raise ValueError('expected source candidate')
            _,epoch,generation,seq,index,macro,faction,sector,x,y,z=body
            if epoch!=self._epoch or generation!=self._generation or not _INT.fullmatch(seq) or not _INT.fullmatch(index):
                raise ValueError('foreign source event')
            try:coords=[float(v) for v in (x,y,z)]
            except ValueError:raise ValueError('invalid source coordinates') from None
            event=job_event({'epoch':epoch,'generation':generation,'sequence':int(seq),'index':int(index),
                             'descriptor':{'macro':macro,'faction':faction,'sector_macro':sector,
                                           'x':coords[0],'y':coords[1],'z':coords[2]}})
            if event['sequence']!=self._last+1:raise ValueError('source sequence gap')
            members=self._membership(None,deadline)
            if not members or len(members)>16 or any(not _PEER.fullmatch(p['id']) or not _TOKEN.fullmatch(p['incarnation']) for p in members):
                raise ValueError('invalid participants')
            identity=[epoch,generation,seq,index]
            self._state='bind'
            self._send(['BIND',*identity,str(len(members)),*(v for p in members for v in (p['id'],p['incarnation']))],deadline)
            if self._recv(deadline)!=['READY',*identity]:raise ValueError('source gate not ready')
            if self._delivery._timeout>=deadline-time.monotonic():raise TimeoutError('insufficient delivery budget')
            self._membership(members,deadline)
            receipts=[];self._state='tcp'
            def collect(peer,received):
                if self._state!='tcp' or received!=event or peer!=members[len(receipts)]:return False
                receipts.append(peer);return True
            if self._delivery.deliver(event,members,collect) is not True or tuple(receipts)!=members:
                raise RuntimeError('client receipts incomplete')
            self._membership(members,deadline)
            self._state='source'
            for i,peer in enumerate(receipts):
                self._membership(members,deadline)
                self._quiet(deadline)
                self._send(['RECEIPT',*identity,peer['id'],peer['incarnation']],deadline)
                expected='SOURCE_ACKED' if i==len(receipts)-1 else 'PARTIAL'
                if self._recv(deadline)!=[expected,*identity,peer['id'],peer['incarnation']]:
                    raise ValueError('source gate receipt mismatch')
                self._membership(members,deadline)
                self._quiet(deadline)
            self._state='rearm'
            self._send(['REARM',*identity],deadline)
            if self._recv(deadline)!=['REARMED',*identity]:raise ValueError('source rearm mismatch')
            self._membership(members,deadline)
            self._last=event['sequence'];self._last_members=members;self._state='idle'
            return {'event':event,'members':members,'source_ack_observed':True}
        except BaseException:
            self._state='failed';self._delivery._failed=True;self._delivery._host._failed=True
            try:self._sock.close()
            except OSError:pass
            raise

    def close(self):
        if threading.get_ident()!=self._owner or self._state not in ('idle','finished'):raise RuntimeError('cannot close active source bridge')
        self._state='closed'
        with _SOCKET_LOCK:_SOCKET_OWNERS.pop(self._sock,None)
        self._sock.close()
