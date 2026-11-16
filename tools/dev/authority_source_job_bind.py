"""Bind a paused, isolated Linux source's UDP socket; starts no process."""
from pathlib import Path
import sys
import weakref
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.experimental_source_job_binding import ExperimentalSourceJobBinding
from authority.experimental_source_job_bridge import _SOCKET_OWNERS, _SOCKET_LOCK
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process

_AUTHORIZE_STATE=weakref.WeakKeyDictionary()


def bind_source(sock, *, process, lease, attempt, epoch, generation, guard, timeout=30):
    """Check sampled PID/start/exe and UDP inode before handing off the socket.

    The caller must independently establish the process as the owned X4 and
    keep it paused through this handoff; `guard` fences that external context.
    """
    if type(process) is not dict:raise ValueError('process identity required')
    identity=dict(process);check_process(identity)
    destination=sock.getsockname()
    def context():
        check_process(identity)
        if guard() is not True:return False
        check_process(identity)
        return sock.getsockname()==destination
    def peer(peer):
        if not context():return False
        valid=socket_owner(peer,destination,identity)
        return valid is True and context()
    binding=ExperimentalSourceJobBinding(sock,enabled=True,lease=lease,attempt=attempt,epoch=epoch,
        generation=generation,guard=context,validate_peer=peer,timeout=timeout)
    binding.bind()
    return binding.handoff()


def authorize_source(sock, *, process, lease, attempt, epoch, generation, guard, timeout=30):
    """Send GO on a bound peer and await GO_READY before the supervisor resumes.

    This function never resumes X4. On any uncertainty the socket is closed;
    the supervisor must also fence the source process and all affected clients.
    """
    import math
    import re
    import select
    import socket
    import time
    fields=(lease,attempt,epoch,generation)
    if (type(sock) is not socket.socket or sock.family!=socket.AF_INET or
        sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
        any(type(v) is not str or not re.fullmatch(r'[0-9a-f]{32}',v) for v in fields) or
        len(set(fields))!=4 or type(process) is not dict or not callable(guard) or
        type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=300):
        raise ValueError('invalid source authorization context')
    identity=dict(process);destination=sock.getsockname();peer=sock.getpeername()
    if destination[0]!='127.0.0.1' or peer[0]!='127.0.0.1' or not destination[1] or not peer[1]:
        raise ValueError('connected loopback source socket required')
    with _SOCKET_LOCK:
        previous=_AUTHORIZE_STATE.get(sock)
        if previous is not None:
            if previous['phase']=='active':previous['conflict']=True
            raise RuntimeError('source socket authorization already used')
        if sock in _SOCKET_OWNERS:raise RuntimeError('source socket already owned')
        state={'phase':'active','conflict':False};_AUTHORIZE_STATE[sock]=state;_SOCKET_OWNERS[sock]=True
    deadline=time.monotonic()+timeout
    def check():
        if state['phase']!='active' or state['conflict']:raise RuntimeError('source GO authorization reentered')
        if time.monotonic()>=deadline:raise TimeoutError('source GO deadline')
        check_process(identity)
        if (guard() is not True or sock.getpeername()!=peer or sock.getsockname()!=destination or
            socket_owner(peer,destination,identity) is not True):raise RuntimeError('source GO context changed')
        check_process(identity)
        if state['phase']!='active' or state['conflict']:raise RuntimeError('source GO authorization reentered')
        if time.monotonic()>=deadline:raise TimeoutError('source GO deadline')
    def quiet():
        check();ready,_,bad=select.select([sock],[],[sock],0)
        if ready or bad:raise RuntimeError('unexpected source packet before/after GO')
        check()
    try:
        sock.setblocking(False);quiet()
        payload=('P|'+lease+'|'+attempt+'|GO|'+epoch+'|'+generation).encode('ascii')
        if sock.send(payload)!=len(payload):raise RuntimeError('source GO dispatch failed')
        check()
        while True:
            ready,_,bad=select.select([sock],[],[sock],min(.1,max(0,deadline-time.monotonic())))
            check()
            if bad:raise RuntimeError('source GO socket error')
            if ready:break
        data=sock.recv(769)
        expected=('S|'+lease+'|'+attempt+'|GO_READY|'+epoch+'|'+generation).encode('ascii')
        if data!=expected:raise ValueError('foreign source GO_READY')
        quiet()
        with _SOCKET_LOCK:
            if state['phase']!='active' or state['conflict']:raise RuntimeError('source GO authorization reentered')
            state['phase']='complete';_SOCKET_OWNERS.pop(sock,None)
        return True
    except BaseException:
        with _SOCKET_LOCK:
            state['phase']='failed';_SOCKET_OWNERS.pop(sock,None)
        sock.close();raise
