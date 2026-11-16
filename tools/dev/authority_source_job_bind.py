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


def bind_running_source(sock, *, process, lease, attempt, epoch, generation,
                        world, client_guard, timeout=30):
    """Private diagnostic only: fence running world and both owned processes.

    The caller's client_guard must check the owned server and admitted client,
    their original PIDs/start times and all protected session inputs. This is
    sampled ownership, not proof against a future state change. Any failure
    closes the socket; the caller must fence the whole session.
    """
    if type(process) is not dict or not callable(client_guard):
        sock.close(); raise ValueError('owned client guard required')
    try:
        initial_session=world.session
        members=tuple(initial_session.players)
    except BaseException:
        sock.close();raise
    def running():
        s=world.session
        if (s is not initial_session or s.state!='running' or s.pending is not None or len(members)!=1 or
                tuple(s.players)!=members or tuple(s.ready_players)!=members):
            return False
        if client_guard() is not True:return False
        return (world.session is initial_session and s.state=='running' and s.pending is None and
                tuple(s.players)==members and tuple(s.ready_players)==members)
    try:
        identity=dict(process)
        check_process(identity)
        destination=sock.getsockname()
        def context():
            check_process(identity)
            if running() is not True:return False
            check_process(identity)
            return sock.getsockname()==destination
        def peer(address):
            if context() is not True:return False
            return socket_owner(address,destination,identity) is True and context() is True
        if context() is not True:raise RuntimeError('running source context unavailable')
        binding=ExperimentalSourceJobBinding(sock,enabled=True,lease=lease,attempt=attempt,
            epoch=epoch,generation=generation,guard=context,validate_peer=peer,
            timeout=timeout,running_diagnostic=True)
        binding.bind()
        if context() is not True:raise RuntimeError('running source context changed')
        bound=binding.handoff()
        if bound is not sock or context() is not True or peer(sock.getpeername()) is not True:
            raise RuntimeError('running source handoff context changed')
        return sock
    except BaseException:
        sock.close();raise


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
