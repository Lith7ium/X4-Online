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
from authority_source_job_bind import bind_source, bind_running_source
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


def bind_source_motion(sock, motion, *, process, lease, attempt, epoch, generation, guard, timeout=30, validate_sample=None,
                       saved_baseline=None, saved_guard=None, latest=False, select_recipients=None, saved_lifetime_guard=None, stop_enabled=False):
    """Bind one source X4 peer, then retain PID/inode checks on every pull.

    Caller proves the source belongs to its owned session and enforces the
    required game state before allowing pulls. Failure requires global fencing.
    """
    if (type(latest) is not bool or type(stop_enabled) is not bool or (latest and not callable(select_recipients)) or
        (saved_lifetime_guard is not None and (not latest or saved_guard is None or not callable(saved_lifetime_guard))) or
        (latest and saved_guard is not None and not callable(saved_lifetime_guard))):
        raise ValueError('invalid latest source guard or interest selector')
    context,peer=_guards(sock,process,guard)
    bound=bind_source(sock,process=process,lease=lease,attempt=attempt,epoch=epoch,
                      generation=generation,guard=context,timeout=timeout)
    if bound is not sock:raise RuntimeError('source motion socket handoff mismatch')
    return ExperimentalSourceMotionIPC(sock,motion,enabled=True,lease=lease,attempt=attempt,
                    epoch=epoch,generation=generation,guard=context,validate_peer=peer,timeout=timeout,validate_sample=validate_sample,
                    saved_baseline=saved_baseline,saved_guard=saved_guard,latest=latest,select_recipients=select_recipients,
                    saved_lifetime_guard=saved_lifetime_guard,stop_enabled=stop_enabled)


def bind_running_source_motion(sock, motion, *, process, lease, attempt, epoch, generation,
                               world, client_guard, timeout=30, validate_sample=None,
                               saved_baseline=None, saved_guard=None, select_recipients=None,candidate_indices=None,
                               bind_timeout=None):
    """Opt-in single diagnostic source; no assertion of cross-X4 identity.

    `bind_timeout`, when supplied, is a per-stage limit: the binding helper
    starts a fresh deadline for bind and again for handoff. The caller must
    separately enforce its overall diagnostic and process deadlines.
    """
    if not callable(client_guard) or not callable(select_recipients):
        sock.close();raise ValueError('running client guard and interest selector required')
    try:
        if motion._delivery._host._world is not world:
            raise ValueError('motion owner belongs to another world')
        initial_session=world.session
        members=tuple(initial_session.players)
    except BaseException:
        sock.close();raise
    def running():
        s=world.session
        return (motion._delivery._host._world is world and s is initial_session and s.state=='running' and s.pending is None and len(members)==1 and
                tuple(s.players)==members and tuple(s.ready_players)==members and client_guard() is True and
                motion._delivery._host._world is world and world.session is initial_session and s.state=='running' and s.pending is None and
                tuple(s.players)==members and tuple(s.ready_players)==members)
    try:
        context,peer=_guards(sock,process,running)
        bind_running_source(sock,process=process,lease=lease,attempt=attempt,epoch=epoch,
                            generation=generation,world=world,client_guard=client_guard,
                            timeout=timeout if bind_timeout is None else bind_timeout)
        if context() is not True or peer(sock.getpeername()) is not True:
            raise RuntimeError('running source context changed after handoff')
        return ExperimentalSourceMotionIPC(sock,motion,enabled=True,lease=lease,attempt=attempt,
            epoch=epoch,generation=generation,guard=context,validate_peer=peer,timeout=timeout,
            validate_sample=validate_sample,saved_baseline=saved_baseline,saved_guard=saved_guard,
            select_recipients=select_recipients,stop_enabled=True,candidate_indices=candidate_indices)
    except BaseException:
        sock.close();raise
