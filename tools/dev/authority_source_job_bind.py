"""Bind a paused, isolated Linux source's UDP socket; starts no process."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.experimental_source_job_binding import ExperimentalSourceJobBinding
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


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
