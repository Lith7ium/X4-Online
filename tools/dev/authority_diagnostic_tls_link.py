"""Private, pre-correlated TLS links for one local recovered-X4 diagnostic."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import socket
import ssl
import sys
import time

from authority_helper_lifecycle import OwnedHelper

HELPER = Path(__file__).resolve().with_name('authority_diagnostic_tls_helper.py')


def _listener():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(4)
    return listener


def _connected_pair():
    listener = _listener()
    outgoing = incoming = None
    try:
        outgoing = socket.create_connection(listener.getsockname(), timeout=3)
        incoming, peer = listener.accept()
        if peer != outgoing.getsockname() or incoming.getpeername() != outgoing.getsockname():
            raise RuntimeError('unexpected local connection')
        return outgoing, incoming
    except BaseException:
        if outgoing is not None:
            outgoing.close()
        if incoming is not None:
            incoming.close()
        raise
    finally:
        listener.close()


def _verify_pairs(pairs):
    descriptors, endpoints = set(), set()
    for left, right in pairs:
        if (left.fileno() in descriptors or right.fileno() in descriptors or
                left.fileno() == right.fileno() or left.family != socket.AF_INET or
                right.family != socket.AF_INET or left.getsockname() != right.getpeername() or
                right.getsockname() != left.getpeername() or
                left.getsockname()[0] != '127.0.0.1' or right.getsockname()[0] != '127.0.0.1'):
            raise RuntimeError('diagnostic TLS socket correlation failed')
        descriptors.update((left.fileno(), right.fileno()))
        pair_endpoints = frozenset((left.getsockname(), right.getsockname()))
        if pair_endpoints in endpoints:
            raise RuntimeError('diagnostic TLS socket reused')
        endpoints.add(pair_endpoints)


def _process_start_ticks(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text('ascii').rsplit(')', 1)[1].split()
        return int(fields[19])
    except (OSError, ValueError, IndexError) as error:
        raise RuntimeError('diagnostic TLS process identity unavailable') from error


class DiagnosticTLSLink:
    """Own gateways, file listeners and a reserved non-listening control port.

    The caller owns the returned client and server sockets. All intermediate
    sockets are closed in the parent immediately after helper FD transfer.
    """
    def __init__(self, participant):
        self.participant = participant
        self.sockets = []
        self.helpers = []
        self.start_ticks = {}
        self.file_port = None
        self.closed = False
        self.departing = False
        self.ipc = []
        if not hasattr(participant, 'guard_resources'):
            participant.guard_resources = []
        participant.guard_resources.append(self)

    def _track(self, sock):
        self.sockets.append(sock)
        return sock

    def _spawn(self, sockets, configuration):
        parent, child = socket.socketpair(type=socket.SOCK_SEQPACKET)
        self._track(parent)
        self._track(child)
        descriptors = [child.fileno(), *(sock.fileno() for sock in sockets)]
        helper = OwnedHelper([sys.executable, str(HELPER), *(str(fd) for fd in descriptors)],
                             registry=self.helpers, pass_fds=tuple(descriptors))
        self.start_ticks[helper] = _process_start_ticks(helper.proc.pid)
        helper.release()
        child.close()
        parent.sendall(json.dumps(configuration, separators=(',', ':')).encode('ascii'))
        return helper, parent

    def check(self):
        if self.closed or len(self.helpers) != 2:
            raise RuntimeError('diagnostic TLS gateway unavailable')
        for helper in self.helpers:
            if helper.proc is None or helper.pidfd is None or helper.proc.poll() is not None:
                raise RuntimeError('diagnostic TLS gateway exited')
            # As in OwnedHelper.stop(), pin the descriptor before inspecting
            # fdinfo so a recycled descriptor cannot redirect the check.
            checked_fd = os.dup(helper.pidfd)
            try:
                info = os.fstat(checked_fd)
                if (info.st_dev, info.st_ino) != helper._pidfd_identity:
                    raise RuntimeError('diagnostic TLS pidfd changed')
                with open('/proc/self/fdinfo/' + str(checked_fd), encoding='ascii') as descriptor_info:
                    pids = [line.split(':', 1)[1].strip() for line in descriptor_info if line.startswith('Pid:')]
                # -1 is permitted during cleanup of an exited process, never
                # while the diagnostic considers its gateway live.
                if (pids != [str(helper.proc.pid)] or
                        _process_start_ticks(helper.proc.pid) != self.start_ticks.get(helper) or
                        helper.proc.poll() is not None):
                    raise RuntimeError('diagnostic TLS process identity changed')
            finally:
                os.close(checked_fd)
        for ipc in self.ipc:
            readable, _, exceptional = select.select([ipc], [], [ipc], 0)
            if exceptional:
                raise RuntimeError('diagnostic TLS IPC changed')
            if readable:
                if not self.departing or ipc.recv(1) != b'D':
                    raise RuntimeError('diagnostic TLS relay ended unexpectedly')
        return True

    def expect_departure(self):
        self.check()
        self.departing = True

    def start(self, certificate, private_key, file_port, deadline):
        pairs = []
        for _ in range(3):
            pair = _connected_pair()
            pairs.append(tuple(self._track(sock) for sock in pair))
        _verify_pairs(pairs)
        client, client_gateway = pairs[0]
        client_tls, server_tls = pairs[1]
        server_gateway, server = pairs[2]
        server_listener = self._track(_listener())
        unused_listener = self._track(_listener())
        file_listener = self._track(_listener())
        reserved_control = self._track(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        reserved_control.bind(('127.0.0.1', 0))
        self.file_port = file_listener.getsockname()[1]
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(Path(certificate).read_text('ascii'))).hexdigest()
        shared_key = secrets.token_bytes(32).hex()
        server_config = dict(role='server', shared_key=shared_key,
            certificate=str(certificate), private_key=str(private_key),
            unused_port=reserved_control.getsockname()[1], file_port=file_port)
        client_config = dict(role='client', shared_key=shared_key,
            server_port=server_listener.getsockname()[1], fingerprint=fingerprint)
        _, server_ipc = self._spawn([server_gateway, server_tls, server_listener], server_config)
        _, client_ipc = self._spawn([client_gateway, client_tls, unused_listener, file_listener], client_config)
        for sock in (client_gateway, client_tls, server_tls, server_gateway,
                     server_listener, unused_listener, file_listener):
            sock.close()
        while True:
            self.check()
            remaining = min(10, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError('diagnostic TLS startup timed out')
            ready, _, exceptional = select.select([server_ipc, client_ipc], [], [server_ipc, client_ipc], remaining)
            if exceptional:
                raise RuntimeError('diagnostic TLS IPC failed')
            for ipc in ready:
                if ipc.recv(1) != b'R':
                    raise RuntimeError('diagnostic TLS startup failed')
            if len(ready) == 2:
                break
            if ready:
                waiting = client_ipc if ready[0] is server_ipc else server_ipc
                remaining = min(10, deadline - time.monotonic())
                ready, _, _ = select.select([waiting], [], [], max(0, remaining))
                if not ready or waiting.recv(1) != b'R':
                    raise RuntimeError('diagnostic TLS startup incomplete')
                break
        self.ipc = [server_ipc, client_ipc]
        self.check()
        self.sockets.remove(client)
        self.sockets.remove(server)
        return client, server

    def _cleanup(self):
        if self.closed:
            return
        errors = []
        for helper in reversed(self.helpers):
            try:
                helper.stop()
            except BaseException as error:
                errors.append(error)
        for sock in reversed(self.sockets):
            try:
                sock.close()
            except OSError as error:
                errors.append(error)
        if errors:
            raise RuntimeError('diagnostic TLS cleanup unconfirmed') from errors[0]
        self.closed = True
