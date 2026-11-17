"""Arm a private fixture source only after checking its local X4 socket owner.

The caller exclusively owns the unconnected socket through the subsequent
binding handoff. A failure closes it; no datagram or game action is retried.
"""
import re
import select
import time

from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


def arm_fixture_source(sock, *, process, lease, attempt, epoch, generation,
                       guard, running, timeout=20):
    tokens = (lease, attempt, epoch, generation)
    if (type(process) is not dict or any(type(v) is not str or not re.fullmatch(r'[0-9a-f]{32}', v) for v in tokens)
            or len(set(tokens)) != len(tokens) or not callable(guard) or not callable(running)
            or type(timeout) not in (int, float) or not 0 < timeout <= 120):
        raise ValueError('invalid fixture source arm context')
    identity = dict(process)
    destination = sock.getsockname()
    expected = ('READY|' + '|'.join(tokens)).encode('ascii')
    response = ('ARM|' + '|'.join(tokens)).encode('ascii')
    deadline = time.monotonic() + timeout

    def within_deadline():
        if time.monotonic() >= deadline:
            raise TimeoutError('fixture source arm deadline expired')

    def valid(peer):
        within_deadline()
        check_process(identity)
        within_deadline()
        if guard() is not True or running() is not True or sock.getsockname() != destination:
            return False
        within_deadline()
        if socket_owner(peer, destination, identity) is not True:
            return False
        within_deadline()
        check_process(identity)
        accepted = guard() is True and running() is True and sock.getsockname() == destination
        within_deadline()
        return accepted

    try:
        while True:
            check_process(identity)
            if guard() is not True or running() is not True or sock.getsockname() != destination:
                raise RuntimeError('fixture source context lost while waiting')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('fixture source did not become ready')
            if select.select([sock], [], [], min(remaining, 0.1))[0]:
                within_deadline()
                break
        packet, peer = sock.recvfrom(769)
        within_deadline()
        if packet != expected or not valid(peer):
            raise RuntimeError('fixture source READY rejected')
        if select.select([sock], [], [], 0)[0]:
            raise RuntimeError('unexpected queued fixture source packet')
        within_deadline()
        sent = sock.sendto(response, peer)
        within_deadline()
        if sent != len(response) or not valid(peer):
            raise RuntimeError('fixture source ARM could not be confirmed')
        return peer
    except BaseException:
        sock.close()
        raise
