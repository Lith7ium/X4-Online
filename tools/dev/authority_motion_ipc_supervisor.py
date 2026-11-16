"""Private Linux PID/socket binding for experimental local motion IPC.

No process, socket, listener or X4 instance is started here. The outer
supervisor must own the supplied processes, maintain profile locks, fence all
sides on any uncertainty, and confirm cleanup. A /proc check is a sampled
ownership assertion, not an atomic authentication or future-liveness guarantee.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority_source_job_bind import bind_source
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


def _guards(sock, process, guard):
    if type(process) is not dict or not callable(guard):raise ValueError('owned process and guard required')
    identity=dict(process);destination=sock.getsockname();check_process(identity)
    def context():
        check_process(identity)
        if guard() is not True:return False
        check_process(identity)
        return sock.getsockname()==destination
    def peer(address):
        if not context():return False
        valid=socket_owner(address,destination,identity)
        return valid is True and context()
    return context,peer


def bind_participant_motion(sock, *, process, lease, attempt, epoch, generation, guard, timeout=20):
    """Call on the participant TCP-reader thread; wait for PID-pinned READY."""
    context,peer=_guards(sock,process,guard)
    bridge=ExperimentalParticipantMotionIPC(sock,enabled=True,lease=lease,attempt=attempt,epoch=epoch,
                    generation=generation,guard=context,validate_peer=peer,timeout=timeout)
    bridge.wait_ready();return bridge


def bind_source_motion(sock, motion, *, process, lease, attempt, epoch, generation, guard, timeout=30):
    """Bind one source X4 peer, then retain PID/inode checks on every pull.

    Caller proves the source belongs to its owned session and enforces the
    required game state before allowing pulls. Failure requires global fencing.
    """
    context,peer=_guards(sock,process,guard)
    bound=bind_source(sock,process=process,lease=lease,attempt=attempt,epoch=epoch,
                      generation=generation,guard=context,timeout=timeout)
    if bound is not sock:raise RuntimeError('source motion socket handoff mismatch')
    return ExperimentalSourceMotionIPC(sock,motion,enabled=True,lease=lease,attempt=attempt,
                    epoch=epoch,generation=generation,guard=context,validate_peer=peer,timeout=timeout)
