"""Explicit running-client diagnostic binding; no game or listener starts.

Call on the owning participant thread after confirming a fresh test grant. The
supervisor owns process/profile locks and must fence all sides on uncertainty.
The caller must prohibit any other access to this socket, including the gap
between handshake handoff and pull-adapter reservation; that transfer is not
atomic. The checks here sample context and cannot prevent later changes.
"""
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.experimental_running_client_authority_binding import ExperimentalRunningClientAuthorityBinding
from authority.experimental_client_authority_motion_ipc import ExperimentalClientAuthorityMotionIPC
from authority.experimental_source_job_bridge import _SOCKET_LOCK, _SOCKET_OWNERS
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


def bind_client_authority(sock,*,process,lease,attempt,epoch,generation,incarnation,token,session_epoch,
                          guard,running,grant,timeout=20,include_orientation=False,
                          fixture_slot=None,fixture_sector=None,expected_peer=None):
    if (type(process) is not dict or type(include_orientation) is not bool or not all(callable(f) for f in (guard,running,grant)) or
        any(type(x) is not str or not re.fullmatch(r'[0-9a-f]{32}',x) for x in (lease,attempt,epoch,generation,incarnation,token)) or
        len({lease,attempt,epoch,generation,incarnation,token})!=6 or type(session_epoch) is not str or
        not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',session_epoch)):
        raise ValueError('invalid running client authority context')
    if expected_peer is not None and (
        type(expected_peer) is not tuple or len(expected_peer)!=2 or expected_peer[0]!='127.0.0.1' or
        type(expected_peer[1]) is not int or not 1<=expected_peer[1]<=65535):
        raise ValueError('invalid expected client authority peer')
    if fixture_slot is None:
        if fixture_sector is not None:raise ValueError('fixture sector requires a player slot')
        index=1318
    else:
        if (type(fixture_slot) is not int or fixture_slot not in (1,2) or include_orientation is not True or
            type(fixture_sector) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,128}',fixture_sector)):
            raise ValueError('invalid fixture player authority context')
        index=fixture_slot+2
    identity=dict(process);destination=sock.getsockname();check_process(identity)
    def context():
        check_process(identity)
        if guard() is not True:return False
        check_process(identity)
        return sock.getsockname()==destination
    def granted():return grant(epoch,generation,index,token,incarnation,session_epoch) is True
    def peer(address):
        if expected_peer is not None and address!=expected_peer:return False
        if not context() or running() is not True or not granted():return False
        ok=socket_owner(address,destination,identity)
        return ok is True and context() and running() is True and granted() and running() is True
    binding=None
    try:
        binding=ExperimentalRunningClientAuthorityBinding(sock,enabled=True,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
            guard=context,validate_peer=peer,running=running,grant=granted,timeout=timeout)
        binding.bind()
        if binding.handoff() is not sock:raise RuntimeError('client authority handoff differs')
        return ExperimentalClientAuthorityMotionIPC(sock,enabled=True,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
            incarnation=incarnation,guard=lambda:context() and running() is True,validate_peer=peer,
            grant=lambda e,g,i,n:e==epoch and g==generation and i==incarnation and n==index and granted(),timeout=timeout,
            include_orientation=include_orientation,fixture_slot=fixture_slot,fixture_sector=fixture_sector)
    except BaseException:
        if binding is not None:
            if binding.state!='handed_off':sock.close()
            else:
                with _SOCKET_LOCK:
                    if sock not in _SOCKET_OWNERS:sock.close()
        raise
